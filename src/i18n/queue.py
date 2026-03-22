"""
Persistent queue service for asynchronous translation jobs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.i18n.locale import SupportedLanguage
from src.i18n.storage import (
    TranslationStatus,
    make_source_hash,
    normalize_key,
    normalize_locale,
    translation_storage_service,
)
from src.infrastructure.models import LocalizationJobModel


class TranslationJobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class EnqueueResult:
    queued: bool
    reason: str
    job_id: Optional[str] = None
    status: Optional[str] = None


@dataclass(frozen=True)
class TranslationQueueStats:
    pending: int
    processing: int
    done: int
    failed: int
    blocked: int


def normalize_supported_locale(locale: str) -> str:
    """
    Normalize locale for queue/storage consistency.

    If locale maps to a supported base language, returns the base code.
    Otherwise returns normalized locale as-is.
    """
    resolved = SupportedLanguage.try_from_code(locale)
    if resolved is not None:
        return resolved.value
    return normalize_locale(locale)


class TranslationQueueService:
    """DB-backed queue operations for translation jobs."""

    @staticmethod
    async def enqueue_missing_translation(
        db: AsyncSession,
        *,
        key: str,
        target_locale: str,
        source_text: str,
        source_locale: Optional[str] = None,
        source_hash: Optional[str] = None,
        priority: int = 100,
        max_attempts: Optional[int] = None,
        force_requeue: bool = False,
    ) -> EnqueueResult:
        translation_key = normalize_key(key)
        normalized_target = normalize_supported_locale(target_locale)
        normalized_source = normalize_supported_locale(
            source_locale or settings.i18n_source_language
        )
        source_value = (source_text or "").strip()

        if not translation_key:
            return EnqueueResult(queued=False, reason="invalid_key")
        if not normalized_target:
            return EnqueueResult(queued=False, reason="invalid_target_locale")
        if not normalized_source:
            return EnqueueResult(queued=False, reason="invalid_source_locale")
        if not source_value:
            return EnqueueResult(queued=False, reason="empty_source_text")
        if normalized_target == normalized_source:
            return EnqueueResult(queued=False, reason="same_as_source_locale")

        translated = await translation_storage_service.get_entry(
            db,
            key=translation_key,
            locale=normalized_target,
        )
        if translated is not None:
            return EnqueueResult(
                queued=False,
                reason="already_translated",
                job_id=None,
                status=None,
            )

        effective_hash = source_hash or make_source_hash(source_value)
        result = await db.execute(
            select(LocalizationJobModel).where(
                LocalizationJobModel.translation_key == translation_key,
                LocalizationJobModel.target_locale == normalized_target,
                LocalizationJobModel.source_hash == effective_hash,
            )
        )
        existing = result.scalar_one_or_none()

        if existing is not None:
            if force_requeue:
                existing.source_text = source_value
                existing.source_locale = normalized_source
                existing.priority = priority
                existing.max_attempts = (
                    max_attempts if max_attempts is not None else existing.max_attempts
                )
                existing.attempt_count = 0
                existing.status = TranslationJobStatus.PENDING.value
                existing.last_error = None
                existing.started_at = None
                existing.processed_at = None
                existing.next_attempt_at = datetime.utcnow()
                await db.flush()
                return EnqueueResult(
                    queued=True,
                    reason="requeued",
                    job_id=str(existing.id),
                    status=existing.status,
                )

            return EnqueueResult(
                queued=False,
                reason=f"already_{existing.status}",
                job_id=str(existing.id),
                status=existing.status,
            )

        created = LocalizationJobModel(
            translation_key=translation_key,
            target_locale=normalized_target,
            source_locale=normalized_source,
            source_text=source_value,
            source_hash=effective_hash,
            status=TranslationJobStatus.PENDING.value,
            priority=priority,
            attempt_count=0,
            max_attempts=max_attempts or settings.i18n_translation_max_attempts,
            next_attempt_at=datetime.utcnow(),
        )
        db.add(created)
        await db.flush()
        return EnqueueResult(
            queued=True,
            reason="queued",
            job_id=str(created.id),
            status=created.status,
        )

    @staticmethod
    async def claim_next_job(db: AsyncSession) -> Optional[LocalizationJobModel]:
        """Claim one pending job atomically."""
        now = datetime.utcnow()
        result = await db.execute(
            select(LocalizationJobModel)
            .where(
                LocalizationJobModel.status == TranslationJobStatus.PENDING.value,
                LocalizationJobModel.next_attempt_at <= now,
            )
            .order_by(
                LocalizationJobModel.priority.asc(),
                LocalizationJobModel.created_at.asc(),
            )
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        job = result.scalar_one_or_none()
        if job is None:
            return None

        job.status = TranslationJobStatus.PROCESSING.value
        job.started_at = now
        job.last_error = None
        job.attempt_count += 1
        await db.flush()
        return job

    @staticmethod
    async def mark_done(
        db: AsyncSession,
        *,
        job: LocalizationJobModel,
        translated_text: str,
    ) -> None:
        await translation_storage_service.upsert_entry(
            db,
            key=job.translation_key,
            locale=job.target_locale,
            text=translated_text,
            status=TranslationStatus.MT,
            source_hash=job.source_hash,
            source_language=job.source_locale,
        )
        now = datetime.utcnow()
        job.status = TranslationJobStatus.DONE.value
        job.last_error = None
        job.processed_at = now
        job.next_attempt_at = now
        await db.flush()

    @staticmethod
    async def mark_blocked(
        db: AsyncSession,
        *,
        job: LocalizationJobModel,
        reason: str,
    ) -> None:
        now = datetime.utcnow()
        job.status = TranslationJobStatus.BLOCKED.value
        job.last_error = (reason or "blocked")[:2000]
        job.processed_at = now
        job.next_attempt_at = now
        await db.flush()

    @staticmethod
    async def mark_failed(
        db: AsyncSession,
        *,
        job: LocalizationJobModel,
        error: str,
    ) -> None:
        now = datetime.utcnow()
        if job.attempt_count >= job.max_attempts:
            job.status = TranslationJobStatus.FAILED.value
            job.processed_at = now
        else:
            delay = max(1, job.attempt_count) * settings.i18n_translation_retry_backoff_seconds
            job.status = TranslationJobStatus.PENDING.value
            job.next_attempt_at = now + timedelta(seconds=delay)
            job.processed_at = None
        job.last_error = (error or "translation_failed")[:2000]
        await db.flush()

    @staticmethod
    async def get_stats(db: AsyncSession) -> TranslationQueueStats:
        result = await db.execute(
            select(
                LocalizationJobModel.status,
                func.count(LocalizationJobModel.id),
            ).group_by(LocalizationJobModel.status)
        )
        counts = {status: count for status, count in result.all()}
        return TranslationQueueStats(
            pending=int(counts.get(TranslationJobStatus.PENDING.value, 0)),
            processing=int(counts.get(TranslationJobStatus.PROCESSING.value, 0)),
            done=int(counts.get(TranslationJobStatus.DONE.value, 0)),
            failed=int(counts.get(TranslationJobStatus.FAILED.value, 0)),
            blocked=int(counts.get(TranslationJobStatus.BLOCKED.value, 0)),
        )

    @staticmethod
    async def requeue_latest_job(
        db: AsyncSession,
        *,
        key: str,
        target_locale: str,
    ) -> EnqueueResult:
        """Force requeue the latest job for key+target locale."""
        translation_key = normalize_key(key)
        normalized_target = normalize_supported_locale(target_locale)
        if not translation_key:
            return EnqueueResult(queued=False, reason="invalid_key")
        if not normalized_target:
            return EnqueueResult(queued=False, reason="invalid_target_locale")

        result = await db.execute(
            select(LocalizationJobModel)
            .where(
                LocalizationJobModel.translation_key == translation_key,
                LocalizationJobModel.target_locale == normalized_target,
            )
            .order_by(LocalizationJobModel.created_at.desc())
            .limit(1)
        )
        job = result.scalar_one_or_none()
        if job is None:
            return EnqueueResult(queued=False, reason="job_not_found")
        if job.status in {
            TranslationJobStatus.PENDING.value,
            TranslationJobStatus.PROCESSING.value,
        }:
            return EnqueueResult(
                queued=False,
                reason=f"already_{job.status}",
                job_id=str(job.id),
                status=job.status,
            )

        job.status = TranslationJobStatus.PENDING.value
        job.attempt_count = 0
        job.last_error = None
        job.started_at = None
        job.processed_at = None
        job.next_attempt_at = datetime.utcnow()
        await db.flush()
        return EnqueueResult(
            queued=True,
            reason="requeued",
            job_id=str(job.id),
            status=job.status,
        )


translation_queue_service = TranslationQueueService()
