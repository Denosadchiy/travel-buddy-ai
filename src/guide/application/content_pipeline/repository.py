"""
ContentPipelineRepository — thin CRUD layer for the content pipeline.

Reads: guide_points, guide_edges, guide_zones, guide_voices, guide_knowledge_cards
Writes: guide_content_blocks (upsert), guide_content_jobs (create / update)

Partial UNIQUE indexes on guide_content_blocks (from migration 009):
  - idx_guide_content_uq_no_edge   WHERE edge_id IS NULL
  - idx_guide_content_uq_with_edge WHERE edge_id IS NOT NULL
The upsert_content_block() method picks the right constraint dynamically.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.guide.domain.models import (
    GuideContentBlock,
    GuideContentJob,
    GuideEdge,
    GuideKnowledgeCard,
    GuidePoint,
    GuideVoice,
    GuideZone,
)


class ContentPipelineRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # -------------------------------------------------------------------------
    # Zones / points / edges / voices
    # -------------------------------------------------------------------------

    async def get_zone_with_metadata(self, zone_id: UUID) -> GuideZone:
        """Load zone with city eagerly loaded (prompt builder accesses zone.city.name)."""
        stmt = (
            select(GuideZone)
            .options(selectinload(GuideZone.city))
            .where(GuideZone.id == zone_id)
        )
        result = await self._db.execute(stmt)
        zone = result.scalar_one_or_none()
        if zone is None:
            raise ValueError(f"Zone {zone_id} not found")
        return zone

    async def get_active_points_in_zone(self, zone_id: UUID) -> list[GuidePoint]:
        """Return approved and active guide_points for a zone."""
        stmt = (
            select(GuidePoint)
            .where(
                GuidePoint.zone_id == zone_id,
                GuidePoint.is_active.is_(True),
                GuidePoint.is_approved.is_(True),
            )
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_edges_in_zone(self, zone_id: UUID) -> list[GuideEdge]:
        """Return all edges whose from_point belongs to this zone."""
        stmt = (
            select(GuideEdge)
            .join(GuidePoint, GuideEdge.from_point_id == GuidePoint.id)
            .where(GuidePoint.zone_id == zone_id)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_knowledge_card(self, point_id: UUID) -> Optional[GuideKnowledgeCard]:
        stmt = select(GuideKnowledgeCard).where(GuideKnowledgeCard.point_id == point_id)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_knowledge_cards_for_points(
        self, point_ids: list[UUID]
    ) -> dict[UUID, GuideKnowledgeCard]:
        """Bulk load to avoid N+1 queries."""
        if not point_ids:
            return {}
        stmt = select(GuideKnowledgeCard).where(
            GuideKnowledgeCard.point_id.in_(point_ids)
        )
        result = await self._db.execute(stmt)
        return {card.point_id: card for card in result.scalars().all()}

    async def get_active_voices(self) -> list[GuideVoice]:
        stmt = select(GuideVoice).where(GuideVoice.is_active.is_(True))
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_voices_by_ids(self, voice_ids: list[UUID]) -> list[GuideVoice]:
        stmt = select(GuideVoice).where(GuideVoice.id.in_(voice_ids))
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    # -------------------------------------------------------------------------
    # guide_content_jobs
    # -------------------------------------------------------------------------

    async def create_content_job(
        self,
        zone_id: UUID,
        job_type: str = "generate_drafts",
        voice_id: Optional[UUID] = None,
        language: Optional[str] = None,
    ) -> GuideContentJob:
        job = GuideContentJob(
            id=uuid.uuid4(),
            zone_id=zone_id,
            job_type=job_type,
            status="running",
            voice_id=voice_id,
            language=language,
            progress_json={},
        )
        self._db.add(job)
        await self._db.flush()
        return job

    async def update_job_progress(self, job_id: UUID, progress_json: dict) -> None:
        job = await self._db.get(GuideContentJob, job_id)
        if job is not None:
            job.progress_json = progress_json
            await self._db.flush()

    async def mark_job_complete(self, job_id: UUID, final_progress: dict) -> None:
        job = await self._db.get(GuideContentJob, job_id)
        if job is not None:
            job.status = "complete"
            job.progress_json = final_progress
            job.completed_at = datetime.now(timezone.utc)
            await self._db.flush()

    async def mark_job_failed(self, job_id: UUID, error_message: str) -> None:
        job = await self._db.get(GuideContentJob, job_id)
        if job is not None:
            job.status = "failed"
            job.error_message = error_message
            job.completed_at = datetime.now(timezone.utc)
            await self._db.flush()

    # -------------------------------------------------------------------------
    # guide_content_blocks
    # -------------------------------------------------------------------------

    async def upsert_content_block(self, block: GuideContentBlock) -> None:
        """
        Insert or update a content block, selecting the correct partial UNIQUE index.

        - edge_id IS NULL  → idx_guide_content_uq_no_edge
        - edge_id NOT NULL → idx_guide_content_uq_with_edge
        """
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        values: dict = {
            "id": block.id or uuid.uuid4(),
            "point_id": block.point_id,
            "zone_id": block.zone_id,
            "voice_id": block.voice_id,
            "language": block.language,
            "detail_level": block.detail_level,
            "content_type": block.content_type,
            "variant_index": block.variant_index,
            "text_script": block.text_script,
            "generation_status": block.generation_status,
            "generated_at": block.generated_at,
            "created_at": block.created_at or datetime.now(timezone.utc),
        }
        if block.edge_id is not None:
            values["edge_id"] = block.edge_id

        update_set: dict = {
            "text_script": block.text_script,
            "generation_status": block.generation_status,
            "generated_at": block.generated_at,
        }

        if block.edge_id is None:
            stmt = pg_insert(GuideContentBlock).values(**values)
            stmt = stmt.on_conflict_do_update(
                index_elements=[
                    "point_id", "voice_id", "language", "detail_level",
                    "content_type", "variant_index",
                ],
                index_where=GuideContentBlock.edge_id.is_(None),
                set_=update_set,
            )
        else:
            stmt = pg_insert(GuideContentBlock).values(**values)
            stmt = stmt.on_conflict_do_update(
                index_elements=[
                    "point_id", "voice_id", "language", "detail_level",
                    "content_type", "edge_id", "variant_index",
                ],
                index_where=GuideContentBlock.edge_id.isnot(None),
                set_=update_set,
            )

        await self._db.execute(stmt)

    async def get_existing_block(
        self,
        point_id: UUID,
        voice_id: UUID,
        language: str,
        detail_level: str,
        content_type: str,
        edge_id: Optional[UUID],
        variant_index: int,
    ) -> Optional[GuideContentBlock]:
        """Fetch existing block for idempotency checks."""
        stmt = select(GuideContentBlock).where(
            GuideContentBlock.point_id == point_id,
            GuideContentBlock.voice_id == voice_id,
            GuideContentBlock.language == language,
            GuideContentBlock.detail_level == detail_level,
            GuideContentBlock.content_type == content_type,
            GuideContentBlock.variant_index == variant_index,
        )
        if edge_id is None:
            stmt = stmt.where(GuideContentBlock.edge_id.is_(None))
        else:
            stmt = stmt.where(GuideContentBlock.edge_id == edge_id)

        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_content_text(
        self,
        point_id: UUID,
        voice_id: UUID,
        language: str,
        content_type: str,
        detail_level: str = "standard",
    ) -> Optional[str]:
        """Fetch text_script of an existing block (e.g. to pass main text into bonus prompt)."""
        stmt = select(GuideContentBlock.text_script).where(
            GuideContentBlock.point_id == point_id,
            GuideContentBlock.voice_id == voice_id,
            GuideContentBlock.language == language,
            GuideContentBlock.detail_level == detail_level,
            GuideContentBlock.content_type == content_type,
            GuideContentBlock.edge_id.is_(None),
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def count_blocks_by_status(self, zone_id: UUID) -> dict[str, int]:
        """Return counts per generation_status for a zone (for progress tracking)."""
        stmt = (
            select(
                GuideContentBlock.generation_status,
                func.count().label("cnt"),
            )
            .where(GuideContentBlock.zone_id == zone_id)
            .group_by(GuideContentBlock.generation_status)
        )
        result = await self._db.execute(stmt)
        return {row.generation_status: row.cnt for row in result}

    # -------------------------------------------------------------------------
    # Stage 2: Coherence Validation
    # -------------------------------------------------------------------------

    async def get_draft_blocks_for_validation(
        self,
        zone_id: UUID,
        language: Optional[str] = None,
        content_type: Optional[str] = None,
    ) -> list[GuideContentBlock]:
        """Return all draft blocks for a zone, optionally filtered by language/content_type."""
        stmt = select(GuideContentBlock).where(
            GuideContentBlock.zone_id == zone_id,
            GuideContentBlock.generation_status == "draft",
        )
        if language is not None:
            stmt = stmt.where(GuideContentBlock.language == language)
        if content_type is not None:
            stmt = stmt.where(GuideContentBlock.content_type == content_type)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_main_text_for_point(
        self,
        point_id: UUID,
        voice_id: UUID,
        language: str,
        detail_level: str = "standard",
    ) -> Optional[str]:
        """Fetch main narrative text for a point (used to build triplet for transition validation)."""
        return await self.get_content_text(point_id, voice_id, language, "main", detail_level)

    async def update_block_validation(
        self,
        block_id: UUID,
        coherence_score: float,
        generation_status: str,
        review_notes: Optional[str] = None,
    ) -> None:
        """Set coherence_score and generation_status after LLM validation."""
        from datetime import datetime, timezone
        block = await self._db.get(GuideContentBlock, block_id)
        if block is None:
            return
        block.coherence_score = coherence_score
        block.generation_status = generation_status
        if review_notes is not None:
            block.review_notes = review_notes
        await self._db.flush()

    async def update_block_text(
        self,
        block_id: UUID,
        text_script: str,
        generation_status: str = "draft",
    ) -> None:
        """Update text_script after regeneration (retry with hint)."""
        from datetime import datetime, timezone
        block = await self._db.get(GuideContentBlock, block_id)
        if block is None:
            return
        block.text_script = text_script
        block.generation_status = generation_status
        block.generated_at = datetime.now(timezone.utc)
        await self._db.flush()

    async def get_block_by_id(self, block_id: UUID) -> Optional[GuideContentBlock]:
        return await self._db.get(GuideContentBlock, block_id)

    async def get_edge_by_id(self, edge_id: UUID):
        from src.guide.domain.models import GuideEdge
        return await self._db.get(GuideEdge, edge_id)

    async def get_voice_by_id(self, voice_id: UUID) -> Optional[GuideVoice]:
        return await self._db.get(GuideVoice, voice_id)

    # -------------------------------------------------------------------------
    # Stage 3: Manual Review
    # -------------------------------------------------------------------------

    async def get_review_queue(
        self,
        zone_id: UUID,
        status: str = "needs_manual_review",
        language: Optional[str] = None,
        content_type: Optional[str] = None,
        voice_id: Optional[UUID] = None,
        min_score: Optional[float] = None,
        max_score: Optional[float] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[tuple]:
        """
        Return blocks for review as raw rows with point_name, voice_name, point_type.
        Priority: content_type rank → point_type rank → coherence_score ASC NULLS LAST.
        """
        from sqlalchemy import case as sa_case, text, asc, nulls_last
        from src.guide.domain.models import GuidePoint

        content_priority = sa_case(
            (GuideContentBlock.content_type == "main", 1),
            (GuideContentBlock.content_type == "zone_transition", 2),
            (GuideContentBlock.content_type == "transition", 3),
            (GuideContentBlock.content_type == "bonus", 4),
            else_=5,
        )
        point_priority = sa_case(
            (GuidePoint.point_type == "poi", 1),
            else_=2,
        )

        stmt = (
            select(
                GuideContentBlock,
                GuidePoint.name.label("point_name"),
                GuidePoint.point_type.label("point_type"),
                GuideVoice.name.label("voice_name"),
            )
            .join(GuidePoint, GuideContentBlock.point_id == GuidePoint.id)
            .join(GuideVoice, GuideContentBlock.voice_id == GuideVoice.id)
            .where(
                GuideContentBlock.zone_id == zone_id,
                GuideContentBlock.generation_status == status,
            )
        )
        if language is not None:
            stmt = stmt.where(GuideContentBlock.language == language)
        if content_type is not None:
            stmt = stmt.where(GuideContentBlock.content_type == content_type)
        if voice_id is not None:
            stmt = stmt.where(GuideContentBlock.voice_id == voice_id)
        if min_score is not None:
            stmt = stmt.where(GuideContentBlock.coherence_score >= min_score)
        if max_score is not None:
            stmt = stmt.where(GuideContentBlock.coherence_score <= max_score)

        stmt = stmt.order_by(
            content_priority,
            point_priority,
            GuideContentBlock.coherence_score.asc().nulls_last(),
        ).limit(limit).offset(offset)

        result = await self._db.execute(stmt)
        return list(result.all())

    async def count_review_queue(
        self,
        zone_id: UUID,
        status: str = "needs_manual_review",
        language: Optional[str] = None,
        content_type: Optional[str] = None,
        voice_id: Optional[UUID] = None,
        min_score: Optional[float] = None,
        max_score: Optional[float] = None,
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(GuideContentBlock)
            .where(
                GuideContentBlock.zone_id == zone_id,
                GuideContentBlock.generation_status == status,
            )
        )
        if language is not None:
            stmt = stmt.where(GuideContentBlock.language == language)
        if content_type is not None:
            stmt = stmt.where(GuideContentBlock.content_type == content_type)
        if voice_id is not None:
            stmt = stmt.where(GuideContentBlock.voice_id == voice_id)
        if min_score is not None:
            stmt = stmt.where(GuideContentBlock.coherence_score >= min_score)
        if max_score is not None:
            stmt = stmt.where(GuideContentBlock.coherence_score <= max_score)
        result = await self._db.execute(stmt)
        return result.scalar_one()

    async def approve_block(self, block_id: UUID, reviewer: str) -> None:
        from datetime import datetime, timezone
        block = await self._db.get(GuideContentBlock, block_id)
        if block is None:
            return
        block.generation_status = "reviewed"
        block.reviewed_by = reviewer
        block.reviewed_at = datetime.now(timezone.utc)
        await self._db.flush()

    async def edit_block(self, block_id: UUID, new_text: str, reviewer: str) -> None:
        from datetime import datetime, timezone
        block = await self._db.get(GuideContentBlock, block_id)
        if block is None:
            return
        block.text_script = new_text
        block.generation_status = "reviewed"
        block.reviewed_by = reviewer
        block.reviewed_at = datetime.now(timezone.utc)
        await self._db.flush()

    async def set_block_pending(self, block_id: UUID, review_notes: Optional[str] = None) -> None:
        """Set block to pending for re-generation, with optional reviewer instruction."""
        block = await self._db.get(GuideContentBlock, block_id)
        if block is None:
            return
        block.generation_status = "pending"
        if review_notes is not None:
            block.review_notes = review_notes
        await self._db.flush()

    async def batch_approve(
        self,
        zone_id: UUID,
        min_score: float,
        language: Optional[str] = None,
        content_types: Optional[list[str]] = None,
    ) -> int:
        """
        Mass-approve blocks with coherence_score >= min_score.
        Returns count of rows updated.
        """
        from datetime import datetime, timezone
        from sqlalchemy import update

        stmt = (
            select(GuideContentBlock.id)
            .where(
                GuideContentBlock.zone_id == zone_id,
                GuideContentBlock.generation_status == "needs_manual_review",
                GuideContentBlock.coherence_score >= min_score,
            )
        )
        if language is not None:
            stmt = stmt.where(GuideContentBlock.language == language)
        if content_types is not None:
            stmt = stmt.where(GuideContentBlock.content_type.in_(content_types))

        id_result = await self._db.execute(stmt)
        ids = [row[0] for row in id_result]
        if not ids:
            return 0

        now = datetime.now(timezone.utc)
        update_stmt = (
            update(GuideContentBlock)
            .where(GuideContentBlock.id.in_(ids))
            .values(
                generation_status="reviewed",
                reviewed_by="batch_approve",
                reviewed_at=now,
            )
        )
        await self._db.execute(update_stmt)
        await self._db.flush()
        return len(ids)

    # -------------------------------------------------------------------------
    # Stage 4: Audio Synthesis
    # -------------------------------------------------------------------------

    async def get_reviewed_blocks(
        self,
        zone_id: UUID,
        voice_ids: Optional[list[UUID]] = None,
        include_synthesized: bool = False,
    ) -> list[GuideContentBlock]:
        """Return reviewed blocks ready for TTS synthesis."""
        statuses = ["reviewed"]
        if include_synthesized:
            statuses.append("synthesized")
        stmt = select(GuideContentBlock).where(
            GuideContentBlock.zone_id == zone_id,
            GuideContentBlock.generation_status.in_(statuses),
        )
        if voice_ids:
            stmt = stmt.where(GuideContentBlock.voice_id.in_(voice_ids))
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def bulk_update_status(self, block_ids: list[UUID], new_status: str) -> None:
        """Mass-update generation_status for a list of block IDs."""
        if not block_ids:
            return
        from sqlalchemy import update
        stmt = (
            update(GuideContentBlock)
            .where(GuideContentBlock.id.in_(block_ids))
            .values(generation_status=new_status)
        )
        await self._db.execute(stmt)
        await self._db.flush()

    async def update_block_audio(
        self,
        block_id: UUID,
        audio_url: str,
        duration_s: float,
        status: str = "synthesized",
    ) -> None:
        """Set audio_url, audio_duration_seconds, synthesized_at after TTS."""
        from datetime import datetime, timezone
        block = await self._db.get(GuideContentBlock, block_id)
        if block is None:
            return
        block.audio_url = audio_url
        block.audio_duration_seconds = duration_s
        block.generation_status = status
        block.synthesized_at = datetime.now(timezone.utc)
        await self._db.flush()

    async def mark_block_failed(self, block_id: UUID) -> None:
        block = await self._db.get(GuideContentBlock, block_id)
        if block is not None:
            block.generation_status = "failed"
            await self._db.flush()

    # -------------------------------------------------------------------------
    # Content status dashboard
    # -------------------------------------------------------------------------

    async def get_zone_content_status(self, zone_id: UUID) -> dict:
        """
        Aggregate content block counts by status and by voice.
        Returns dict suitable for ContentStatusResponse.
        """
        # Total and per-status counts
        status_stmt = (
            select(
                GuideContentBlock.generation_status,
                func.count().label("cnt"),
            )
            .where(GuideContentBlock.zone_id == zone_id)
            .group_by(GuideContentBlock.generation_status)
        )
        status_result = await self._db.execute(status_stmt)
        by_status = {row.generation_status: row.cnt for row in status_result}

        total = sum(by_status.values())
        ready = by_status.get("synthesized", 0)
        pending = sum(v for k, v in by_status.items() if k in ("pending", "draft", "validated", "needs_manual_review", "reviewed", "synthesizing"))
        failed = by_status.get("failed", 0)

        # Per-voice stats
        voice_stmt = (
            select(
                GuideVoice.id,
                GuideVoice.name,
                GuideVoice.style_group,
                GuideVoice.language,
                func.count().label("total"),
                func.sum(
                    case((GuideContentBlock.generation_status == "synthesized", 1), else_=0)
                ).label("synthesized_cnt"),
            )
            .join(GuideVoice, GuideContentBlock.voice_id == GuideVoice.id)
            .where(GuideContentBlock.zone_id == zone_id)
            .group_by(GuideVoice.id, GuideVoice.name, GuideVoice.style_group, GuideVoice.language)
        )
        voice_result = await self._db.execute(voice_stmt)
        voices = []
        for row in voice_result:
            pct = round((row.synthesized_cnt / row.total * 100), 1) if row.total > 0 else 0.0
            voices.append({
                "voice_id": row.id,
                "name": row.name,
                "style_group": row.style_group,
                "language": row.language,
                "ready_pct": pct,
            })

        return {
            "total_blocks": total,
            "ready": ready,
            "pending": pending,
            "failed": failed,
            "voices": voices,
        }

    async def get_content_jobs(
        self,
        zone_id: Optional[UUID] = None,
        job_type: Optional[str] = None,
        limit: int = 20,
    ) -> list:
        from src.guide.domain.models import GuideContentJob
        stmt = select(GuideContentJob).order_by(GuideContentJob.created_at.desc()).limit(limit)
        if zone_id is not None:
            stmt = stmt.where(GuideContentJob.zone_id == zone_id)
        if job_type is not None:
            stmt = stmt.where(GuideContentJob.job_type == job_type)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_content_job(self, job_id: UUID):
        from src.guide.domain.models import GuideContentJob
        return await self._db.get(GuideContentJob, job_id)
