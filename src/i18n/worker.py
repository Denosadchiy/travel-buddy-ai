"""
Background worker for asynchronous translation queue processing.
"""

from __future__ import annotations

import asyncio
import logging

from src.config import settings
from src.i18n.budget import get_translation_budget_guard
from src.i18n.provider import get_machine_translation_provider
from src.i18n.quality import apply_glossary_overrides
from src.i18n.queue import translation_queue_service
from src.infrastructure.database import AsyncSessionLocal
from src.infrastructure.models import LocalizationJobModel

logger = logging.getLogger(__name__)


class TranslationQueueWorker:
    """Long-running async worker that processes queued translation jobs."""

    def __init__(self) -> None:
        self._stop_event = asyncio.Event()

    async def stop(self) -> None:
        self._stop_event.set()

    async def run_forever(self) -> None:
        logger.info("i18n translation worker started")
        while not self._stop_event.is_set():
            processed_job = False
            try:
                async with AsyncSessionLocal() as db:
                    job = await translation_queue_service.claim_next_job(db)
                    if job is None:
                        await db.commit()
                    else:
                        await self._process_job(db, job)
                        await db.commit()
                        processed_job = True
            except Exception:
                logger.exception("i18n worker loop failed")

            if processed_job:
                continue

            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=settings.i18n_translation_poll_interval_seconds,
                )
            except asyncio.TimeoutError:
                continue

        logger.info("i18n translation worker stopped")

    async def _process_job(self, db, job: LocalizationJobModel) -> None:
        char_count = len(job.source_text)
        allowed, reason = get_translation_budget_guard().reserve(char_count)
        if not allowed:
            await translation_queue_service.mark_blocked(
                db,
                job=job,
                reason=reason,
            )
            return

        translator = get_machine_translation_provider()
        try:
            translated_text = await translator.translate_text(
                text=job.source_text,
                source_locale=job.source_locale,
                target_locale=job.target_locale,
            )
            translated_text = translated_text.strip()
            if not translated_text:
                raise ValueError("provider returned empty translation")
            translated_text = apply_glossary_overrides(
                translated_text,
                job.target_locale,
            )
            await translation_queue_service.mark_done(
                db,
                job=job,
                translated_text=translated_text,
            )
        except Exception as exc:
            await translation_queue_service.mark_failed(
                db,
                job=job,
                error=str(exc),
            )


translation_queue_worker = TranslationQueueWorker()
