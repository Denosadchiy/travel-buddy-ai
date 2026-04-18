"""
ReviewService — Stage 3 of the Content Pipeline.

Business logic for manual content review. Does NOT contain HTTP handling
(that lives in admin_router.py).

Operations:
  - get_review_queue()    — paginated list sorted by priority + coherence score
  - approve_block()       — mark reviewed
  - edit_block()          — update text + mark reviewed
  - regenerate_block()    — re-queue for LLM (status → pending)
  - preview_tts()         — quick ElevenLabs synthesis → S3 preview/ → presigned URL
  - batch_approve()       — mass-approve blocks above a coherence_score threshold

Priority order (from CONTENT_PIPELINE.md §6.1):
  content_type: main=1, zone_transition=2, transition=3, bonus=4, recap=5
  point_type: poi=1, connector=2
  Within same priority: coherence_score ASC NULLS LAST (most problematic first)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from src.config import settings as _default_settings

if TYPE_CHECKING:
    from src.guide.application.content_pipeline.repository import ContentPipelineRepository
    from src.guide.infrastructure.elevenlabs_client import ElevenLabsClient
    from src.guide.infrastructure.s3_client import GuideS3Client
    from src.infrastructure.llm_client import LLMClient

logger = logging.getLogger(__name__)


class ReviewService:
    """Manual review orchestration for Stage 3 of the Content Pipeline."""

    def __init__(
        self,
        repo: "ContentPipelineRepository",
        llm_client: "LLMClient",
        elevenlabs_client: "ElevenLabsClient",
        s3_client: "GuideS3Client",
        app_settings=None,
    ) -> None:
        self._repo = repo
        self._llm = llm_client
        self._tts = elevenlabs_client
        self._s3 = s3_client
        self._settings = app_settings or _default_settings

    # -------------------------------------------------------------------------
    # Queue
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
    ) -> tuple[list[dict], int]:
        """
        Return (blocks, total_count) for the review queue.

        Each block dict has all ContentBlockReviewView fields + point_name / voice_name.
        """
        rows = await self._repo.get_review_queue(
            zone_id=zone_id,
            status=status,
            language=language,
            content_type=content_type,
            voice_id=voice_id,
            min_score=min_score,
            max_score=max_score,
            limit=limit,
            offset=offset,
        )
        total = await self._repo.count_review_queue(
            zone_id=zone_id,
            status=status,
            language=language,
            content_type=content_type,
            voice_id=voice_id,
            min_score=min_score,
            max_score=max_score,
        )

        blocks = []
        for row in rows:
            block = row[0]
            point_name = row[1]
            point_type = row[2]
            voice_name = row[3]
            blocks.append({
                "id": block.id,
                "point_id": block.point_id,
                "point_name": point_name,
                "zone_id": block.zone_id,
                "voice_id": block.voice_id,
                "voice_name": voice_name,
                "language": block.language,
                "detail_level": block.detail_level,
                "content_type": block.content_type,
                "variant_index": block.variant_index,
                "text_script": block.text_script,
                "audio_url": block.audio_url,
                "audio_duration_seconds": block.audio_duration_seconds,
                "generation_status": block.generation_status,
                "coherence_score": block.coherence_score,
                "review_notes": block.review_notes,
                "reviewed_by": block.reviewed_by,
                "reviewed_at": block.reviewed_at,
                "created_at": block.created_at,
            })
        return blocks, total

    # -------------------------------------------------------------------------
    # Individual block actions
    # -------------------------------------------------------------------------

    async def approve_block(self, block_id: UUID, reviewer: str) -> None:
        """Set generation_status → reviewed, set reviewed_by / reviewed_at."""
        await self._repo.approve_block(block_id, reviewer)
        logger.info("Block %s approved by %s", block_id, reviewer)

    async def edit_block(self, block_id: UUID, new_text: str, reviewer: str) -> None:
        """Update text_script and mark as reviewed."""
        if not new_text or not new_text.strip():
            raise ValueError("new_text must not be empty")
        await self._repo.edit_block(block_id, new_text.strip(), reviewer)
        logger.info("Block %s edited by %s", block_id, reviewer)

    async def regenerate_block(
        self,
        block_id: UUID,
        instruction: Optional[str],
        reviewer: str,
    ) -> None:
        """
        Re-queue a block for LLM regeneration.

        Sets generation_status → pending so the DraftGenerator / validator will
        pick it up on the next run. If an instruction is provided, it is stored
        in review_notes to be included in the regeneration prompt.
        """
        block = await self._repo.get_block_by_id(block_id)
        if block is None:
            raise ValueError(f"Block {block_id} not found")

        await self._repo.set_block_pending(block_id, review_notes=instruction or None)
        logger.info("Block %s queued for regeneration by %s", block_id, reviewer)

        # Inline LLM regeneration (if instruction provided, include as hint)
        try:
            await self._inline_regenerate(block, instruction)
        except Exception as exc:
            logger.warning(
                "Inline regeneration failed for block %s: %s — block stays pending",
                block_id, exc,
            )

    async def _inline_regenerate(self, block, instruction: Optional[str]) -> None:
        """
        Perform an immediate LLM call to regenerate the block text,
        then set status back to 'draft' (will require re-validation).
        """
        from src.guide.application.content_pipeline.prompt_builders import _build_prompt_for_block
        try:
            prompt = await _build_prompt_for_block(block, self._repo)
        except NotImplementedError:
            # Fallback: just keep it pending
            return

        if instruction:
            prompt += f"\n\nRevision instruction from reviewer: {instruction}"

        raw = await self._llm.generate_structured(prompt, max_tokens=800)
        text = raw.get("text_script", "")
        if text and len(text.strip()) >= 20:
            await self._repo.update_block_text(block.id, text.strip(), generation_status="draft")

    # -------------------------------------------------------------------------
    # TTS Preview
    # -------------------------------------------------------------------------

    async def preview_tts(self, block_id: UUID) -> dict:
        """
        Synthesize a quick TTS preview for the block.

        Uploads to s3://bucket/guide/preview/{block_id}.mp3 and returns a
        presigned URL valid for 1 hour.
        """
        block = await self._repo.get_block_by_id(block_id)
        if block is None:
            raise ValueError(f"Block {block_id} not found")

        voice = await self._repo.get_voice_by_id(block.voice_id)
        if voice is None:
            raise ValueError(f"Voice {block.voice_id} not found for block {block_id}")

        audio_bytes = await self._tts.synthesize_batch(
            text=block.text_script,
            voice_id=voice.elevenlabs_voice_id,
        )

        key = self._s3.build_preview_key(str(block_id))
        await self._s3.upload_audio(key, audio_bytes)

        presigned_url = await self._s3.generate_presigned_url(key, expires_in=3600)

        # Estimate duration
        duration_s = _estimate_duration_seconds(block.text_script)

        return {
            "audio_url": presigned_url,
            "duration_s": duration_s,
            "expires_in_seconds": 3600,
        }

    # -------------------------------------------------------------------------
    # Batch approve
    # -------------------------------------------------------------------------

    async def batch_approve(
        self,
        zone_id: UUID,
        min_score: float,
        language: Optional[str] = None,
        content_types: Optional[list[str]] = None,
    ) -> dict:
        """
        Mass-approve all needs_manual_review blocks with coherence_score >= min_score.

        Returns {"approved_count": N, "skipped_count": M}.
        """
        total_in_queue = await self._repo.count_review_queue(
            zone_id=zone_id,
            status="needs_manual_review",
            language=language,
        )
        approved = await self._repo.batch_approve(
            zone_id=zone_id,
            min_score=min_score,
            language=language,
            content_types=content_types,
        )
        skipped = total_in_queue - approved
        logger.info(
            "Batch approve zone %s: approved=%d skipped=%d (min_score=%.1f)",
            zone_id, approved, skipped, min_score,
        )
        return {"approved_count": approved, "skipped_count": max(0, skipped)}


# -------------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------------

def _estimate_duration_seconds(text: str) -> float:
    """
    Rough TTS duration estimate: ~140 words per minute for English speech.
    Used as a fallback when actual audio is not yet available.
    """
    words = len(text.split())
    return round(words / 140 * 60, 1)


# -------------------------------------------------------------------------
# Prompt builder helper (best-effort)
# -------------------------------------------------------------------------

async def _build_prompt_for_block(block, repo) -> str:
    """
    Reconstruct the generation prompt for a block so that regeneration
    can include reviewer instructions.

    Only handles main/bonus/recap for simplicity (transitions use a
    more complex context assembly).
    """
    if block.content_type not in ("main", "bonus", "recap"):
        raise NotImplementedError(
            f"Inline prompt rebuild not supported for content_type={block.content_type}"
        )

    from src.guide.application.content_pipeline.prompt_builder import (
        build_main_prompt,
        build_bonus_prompt,
        build_recap_prompt,
    )

    voice = await repo.get_voice_by_id(block.voice_id)
    zone = await repo.get_zone_with_metadata(block.zone_id)

    from src.guide.domain.models import GuidePoint
    point = await repo._db.get(GuidePoint, block.point_id)
    card = await repo.get_knowledge_card(block.point_id)

    if block.content_type == "main":
        return build_main_prompt(point, card, zone, voice, block.language, block.detail_level, {})
    elif block.content_type == "bonus":
        main_text = await repo.get_content_text(
            block.point_id, block.voice_id, block.language, "main", block.detail_level
        ) or ""
        return build_bonus_prompt(point, card, zone, voice, block.language, block.detail_level, main_text)
    elif block.content_type == "recap":
        main_text = await repo.get_content_text(
            block.point_id, block.voice_id, block.language, "main", "standard"
        ) or ""
        return build_recap_prompt(point, voice, block.language, main_text)

    raise NotImplementedError
