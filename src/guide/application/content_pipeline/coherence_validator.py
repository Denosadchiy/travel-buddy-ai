"""
CoherenceValidator — Stage 2 of the Content Pipeline.

Validates all draft content blocks for a zone using LLM-based scoring:
  - Transitions (transition / zone_transition): pairwise triplet validation
    [A_tail + transition_text + B_head] → coherence_score 1.0–5.0
    Auto-retry up to 3 times; after 3 failures → needs_manual_review
  - Standalone (main / bonus / recap): single-block validation
    No auto-retry — low-scoring blocks go straight to needs_manual_review

Thresholds:
  transition / zone_transition: 4.0
  main / bonus / recap:         3.5

Safety:
  - asyncio.Semaphore limits concurrent LLM calls
  - Idempotent: already-validated blocks are skipped
  - Progress written to guide_content_jobs.progress_json
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from src.config import settings as _default_settings
from src.guide.application.content_pipeline.prompt_templates import (
    COHERENCE_VALIDATION_PROMPT,
    STANDALONE_VALIDATION_PROMPT,
    WALK_VALIDATION_PROMPT,
)
from src.guide.application.content_pipeline.utils import _bearing_to_description, _head, _tail

if TYPE_CHECKING:
    from src.guide.application.content_pipeline.repository import ContentPipelineRepository
    from src.infrastructure.llm_client import LLMClient

logger = logging.getLogger(__name__)

# Blocks in these statuses are already processed — skip
_SKIP_STATUSES = {"validated", "needs_manual_review", "reviewed", "synthesized"}

# Coherence threshold per content_type
COHERENCE_THRESHOLDS: dict[str, float] = {
    "transition": 4.0,
    "zone_transition": 4.0,
    "main": 3.5,
    "bonus": 3.5,
    "recap": 3.5,
}

# Content types that get pairwise (triplet) validation
_PAIRWISE_TYPES = {"transition", "zone_transition"}


class CoherenceValidator:
    """LLM-based coherence validator for Stage 2 of the Content Pipeline."""

    def __init__(
        self,
        repo: "ContentPipelineRepository",
        llm_client: "LLMClient",
        app_settings=None,
    ) -> None:
        self._repo = repo
        self._llm = llm_client
        self._settings = app_settings or _default_settings
        self._semaphore = asyncio.Semaphore(
            getattr(self._settings, "guide_content_max_parallel_llm", 15)
        )

    # -------------------------------------------------------------------------
    # Public entry point
    # -------------------------------------------------------------------------

    async def validate_zone(
        self,
        zone_id: UUID,
        language: Optional[str] = None,
        include_walk_validation: bool = False,
        job_id: Optional[UUID] = None,
    ) -> dict:
        """
        Validate all draft blocks for a zone.

        Returns stats: {validated, needs_review, retried, errors}.
        """
        logger.info(
            "CoherenceValidator: starting zone %s (language=%s walk=%s)",
            zone_id, language, include_walk_validation,
        )

        all_draft = await self._repo.get_draft_blocks_for_validation(
            zone_id, language=language
        )

        pairwise_blocks = [b for b in all_draft if b.content_type in _PAIRWISE_TYPES]
        standalone_blocks = [b for b in all_draft if b.content_type not in _PAIRWISE_TYPES]

        stats = {"validated": 0, "needs_review": 0, "retried": 0, "errors": 0}

        # Pairwise validation (transitions)
        tasks = [
            self._validate_pairwise(block, stats)
            for block in pairwise_blocks
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

        # Standalone validation (main / bonus / recap)
        tasks = [
            self._validate_standalone(block, stats)
            for block in standalone_blocks
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

        # Optional walk validation
        if include_walk_validation and (pairwise_blocks or standalone_blocks):
            try:
                await self._validate_walks(zone_id, language, job_id)
            except Exception as exc:
                logger.warning("Walk validation failed: %s", exc)

        if job_id is not None:
            await self._repo.update_job_progress(job_id, {
                "phase": "coherence_validation",
                **stats,
                "total_draft": len(all_draft),
            })

        logger.info(
            "CoherenceValidator: done zone %s — %s",
            zone_id, stats,
        )
        return stats

    # -------------------------------------------------------------------------
    # Pairwise (triplet) validation — transitions
    # -------------------------------------------------------------------------

    async def _validate_pairwise(
        self,
        block,
        stats: dict,
        retry_count: int = 0,
    ) -> None:
        if block.generation_status in _SKIP_STATUSES:
            return

        async with self._semaphore:
            try:
                score_data = await self._score_transition(block)
            except Exception as exc:
                logger.error("Pairwise validation failed block %s: %s", block.id, exc)
                stats["errors"] += 1
                return

        overall = float(score_data.get("overall_score", 0.0))
        threshold = COHERENCE_THRESHOLDS.get(block.content_type, 4.0)

        await self._repo.update_block_validation(
            block.id,
            coherence_score=overall,
            generation_status="draft",  # will be updated below
        )

        if overall >= threshold:
            await self._repo.update_block_validation(block.id, overall, "validated")
            stats["validated"] += 1

        elif retry_count < 3:
            # Regenerate with hint and re-validate
            suggested_fix = score_data.get("suggested_fix", "")
            stats["retried"] += 1
            try:
                await self._regenerate_transition_with_hint(block, suggested_fix)
                # Reload block (text_script changed in DB)
                updated = await self._repo.get_block_by_id(block.id)
                if updated:
                    await self._validate_pairwise(updated, stats, retry_count=retry_count + 1)
            except Exception as exc:
                logger.error("Retry %d failed for block %s: %s", retry_count + 1, block.id, exc)
                await self._repo.update_block_validation(
                    block.id, overall, "needs_manual_review",
                    review_notes=f"Retry {retry_count + 1} failed: {exc}",
                )
                stats["needs_review"] += 1
        else:
            # 3 retries exhausted
            issue = score_data.get("issues", "")
            await self._repo.update_block_validation(
                block.id, overall, "needs_manual_review",
                review_notes=(
                    f"Auto-validation failed after 3 retries. "
                    f"Last score: {overall:.1f}. Issue: {issue}"
                ),
            )
            stats["needs_review"] += 1

    async def _score_transition(self, block) -> dict:
        """Call LLM with pairwise prompt; return parsed score dict."""
        edge = None
        if block.edge_id:
            edge = await self._repo.get_edge_by_id(block.edge_id)

        voice = await self._repo.get_voice_by_id(block.voice_id)
        style_group = voice.style_group if voice else "friendly"

        # Gather triplet: tail of A + transition + head of B
        narrative_a = ""
        narrative_b = ""
        if edge:
            narrative_a = await self._repo.get_main_text_for_point(
                edge.from_point_id, block.voice_id, block.language, block.detail_level
            ) or ""
            narrative_b = await self._repo.get_main_text_for_point(
                edge.to_point_id, block.voice_id, block.language, block.detail_level
            ) or ""

        bearing_desc = "unknown direction"
        if edge and edge.bearing_deg is not None:
            bearing_desc = _bearing_to_description(edge.bearing_deg)

        prompt = COHERENCE_VALIDATION_PROMPT.format(
            narrative_a_tail=_tail(narrative_a, sentences=2),
            transition_text=block.text_script,
            narrative_b_head=_head(narrative_b, sentences=2),
            style_group=style_group,
            language=block.language,
            bearing_description=bearing_desc,
        )

        result = await self._llm.generate_structured(prompt, max_tokens=300)
        return result

    async def _regenerate_transition_with_hint(self, block, suggested_fix: str) -> None:
        """Regenerate transition text_script with a validator hint appended to the prompt."""
        from src.guide.application.content_pipeline.prompt_templates import TRANSITION_PROMPT
        from src.guide.application.content_pipeline.utils import _head, _tail

        edge = None
        if block.edge_id:
            edge = await self._repo.get_edge_by_id(block.edge_id)

        voice = await self._repo.get_voice_by_id(block.voice_id)
        if voice is None or edge is None:
            raise RuntimeError(f"Cannot regenerate block {block.id}: missing edge or voice")

        from src.guide.application.content_pipeline.prompt_templates import VOICE_PERSONAS, WORD_COUNTS, LANGUAGE_NAMES
        persona = VOICE_PERSONAS.get(voice.style_group, {}).get(block.language, "")
        lang_name = LANGUAGE_NAMES.get(block.language, block.language)

        from_text = await self._repo.get_main_text_for_point(
            edge.from_point_id, block.voice_id, block.language, "standard"
        ) or ""
        to_text = await self._repo.get_main_text_for_point(
            edge.to_point_id, block.voice_id, block.language, "standard"
        ) or ""

        # Load point names
        from src.guide.domain.models import GuidePoint
        from sqlalchemy import select
        from_point_result = await self._repo._db.get(GuidePoint, edge.from_point_id)
        to_point_result = await self._repo._db.get(GuidePoint, edge.to_point_id)
        from_name = (from_point_result.name if from_point_result else "") or "point A"
        to_name = (to_point_result.name if to_point_result else "") or "point B"

        prompt = TRANSITION_PROMPT.format(
            persona_description=persona,
            from_point_name=from_name,
            from_themes="",
            to_point_name=to_name,
            from_narrative_tail=_tail(from_text, 2),
            to_narrative_head=_head(to_text, 2),
            language_name=lang_name,
            style_description=voice.style_group,
        )
        if suggested_fix and suggested_fix != "none":
            prompt += f"\n\nImprovement hint from quality review: {suggested_fix}"

        raw = await self._llm.generate_structured(prompt, max_tokens=500)
        variants = (raw.get("variants") or [])
        new_text = ""
        if variants:
            # Use the variant matching block.variant_index, or first available
            idx = min(block.variant_index, len(variants) - 1)
            new_text = (variants[idx] or {}).get("text_script", "")
        if not new_text:
            raise RuntimeError("LLM returned empty text_script in regeneration")

        await self._repo.update_block_text(block.id, new_text, generation_status="draft")

    # -------------------------------------------------------------------------
    # Standalone validation — main / bonus / recap
    # -------------------------------------------------------------------------

    async def _validate_standalone(self, block, stats: dict) -> None:
        if block.generation_status in _SKIP_STATUSES:
            return

        async with self._semaphore:
            try:
                score_data = await self._score_standalone(block)
            except Exception as exc:
                logger.error("Standalone validation failed block %s: %s", block.id, exc)
                stats["errors"] += 1
                return

        overall = float(score_data.get("overall_score", 0.0))
        threshold = COHERENCE_THRESHOLDS.get(block.content_type, 3.5)

        if overall >= threshold:
            await self._repo.update_block_validation(block.id, overall, "validated")
            stats["validated"] += 1
        else:
            issue = score_data.get("issues", "")
            await self._repo.update_block_validation(
                block.id, overall, "needs_manual_review",
                review_notes=f"Standalone validation score {overall:.1f} < {threshold}. Issue: {issue}",
            )
            stats["needs_review"] += 1

    async def _score_standalone(self, block) -> dict:
        voice = await self._repo.get_voice_by_id(block.voice_id)
        style_group = voice.style_group if voice else "friendly"

        # Get point name for context
        from src.guide.domain.models import GuidePoint
        point = await self._repo._db.get(GuidePoint, block.point_id)
        point_name = (point.name if point else None) or str(block.point_id)

        prompt = STANDALONE_VALIDATION_PROMPT.format(
            content_type=block.content_type,
            point_name=point_name,
            text_script=block.text_script,
            style_group=style_group,
            language=block.language,
        )
        result = await self._llm.generate_structured(prompt, max_tokens=250)
        return result

    # -------------------------------------------------------------------------
    # Walk validation (optional)
    # -------------------------------------------------------------------------

    async def _validate_walks(
        self,
        zone_id: UUID,
        language: Optional[str],
        job_id: Optional[UUID],
        num_walks: int = 3,
        walk_length: int = 5,
    ) -> None:
        """
        Generate random walks through the zone graph, assemble narrative chains,
        and score overall coherence. Flag problem points for manual review.
        """
        points = await self._repo.get_active_points_in_zone(zone_id)
        edges = await self._repo.get_edges_in_zone(zone_id)
        voices = await self._repo.get_active_voices()

        if not points or not edges or not voices:
            return

        adj: dict[UUID, list[UUID]] = {p.id: [] for p in points}
        for e in edges:
            adj[e.from_point_id].append(e.to_point_id)

        point_map = {p.id: p for p in points}
        voice = voices[0]
        lang = language or "en"
        style_group = voice.style_group

        point_name_to_id = {p.name: p.id for p in points if p.name}

        for _ in range(num_walks):
            path = self._random_walk(list(adj.keys()), adj, walk_length)
            if len(path) < 2:
                continue

            # Build chain
            chain_parts: list[str] = []
            for i, pid in enumerate(path):
                pt = point_map.get(pid)
                pt_name = (pt.name if pt else None) or str(pid)
                main_text = await self._repo.get_content_text(
                    pid, voice.id, lang, "main", "standard"
                ) or ""
                chain_parts.append(f"[{i+1}. {pt_name}]\n{main_text[:400]}")
                if i < len(path) - 1:
                    # Try to find a transition
                    trans_blocks = await self._repo.get_draft_blocks_for_validation(
                        zone_id, language=lang, content_type="transition"
                    )
                    trans = next(
                        (b for b in trans_blocks
                         if b.point_id == pid and b.edge_id is not None
                         and b.generation_status in ("validated", "reviewed")),
                        None,
                    )
                    if trans:
                        chain_parts.append(f"[\u2192 transition]\n{trans.text_script}")

            full_chain = "\n\n".join(chain_parts)
            prompt = WALK_VALIDATION_PROMPT.format(
                chain=full_chain[:4000],
                style_group=style_group,
                language=lang,
            )

            try:
                async with self._semaphore:
                    result = await self._llm.generate_structured(prompt, max_tokens=400)
            except Exception as exc:
                logger.warning("Walk validation LLM call failed: %s", exc)
                continue

            overall = float(result.get("overall_score", 5.0))
            if overall < 3.5:
                problem_names = result.get("problem_points") or []
                issue = result.get("main_issue", "")
                for pname in problem_names:
                    pid = point_name_to_id.get(pname)
                    if pid:
                        # Flag all draft/validated blocks for this point for review
                        draft_blocks = await self._repo.get_draft_blocks_for_validation(
                            zone_id, language=lang
                        )
                        for b in draft_blocks:
                            if b.point_id == pid and b.generation_status in ("draft", "validated"):
                                await self._repo.update_block_validation(
                                    b.id,
                                    coherence_score=b.coherence_score or overall,
                                    generation_status="needs_manual_review",
                                    review_notes=f"Walk validation: {issue}",
                                )
                logger.info(
                    "Walk validation: score %.1f < 3.5, flagged %d problem points",
                    overall, len(problem_names),
                )

    @staticmethod
    def _random_walk(
        point_ids: list[UUID],
        adj: dict[UUID, list[UUID]],
        length: int,
    ) -> list[UUID]:
        """Return a connected random walk of at most `length` nodes."""
        if not point_ids:
            return []
        start = random.choice(point_ids)
        path = [start]
        visited = {start}
        for _ in range(length - 1):
            neighbors = [n for n in adj.get(path[-1], []) if n not in visited]
            if not neighbors:
                break
            nxt = random.choice(neighbors)
            path.append(nxt)
            visited.add(nxt)
        return path
