"""
Runtime translation resolver: serve fallback immediately and enqueue MT job.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.i18n.locale import SupportedLanguage, lookup_translation
from src.i18n.observability import get_i18n_observability
from src.i18n.quality import (
    is_status_ready_for_tier_a,
    requires_manual_review_for_key,
)
from src.i18n.queue import normalize_supported_locale, translation_queue_service
from src.i18n.rollout import is_locale_rollout_enabled
from src.i18n.storage import make_source_hash, normalize_key, translation_storage_service


@dataclass(frozen=True)
class RuntimeTranslationResult:
    key: str
    requested_locale: str
    resolved_locale: str
    text: str
    is_fallback: bool
    queued: bool
    queue_reason: str
    source: str
    status: str
    rollout_enabled: bool


def _resolve_source_text(
    *,
    key: str,
    source_locale: str,
    fallback_locale: str,
) -> tuple[str, str]:
    source_lang = SupportedLanguage.try_from_code(source_locale)
    if source_lang is not None:
        source_text = lookup_translation(source_lang, key)
        if source_text is not None:
            return source_text, source_lang.value

    fallback_lang = SupportedLanguage.try_from_code(fallback_locale)
    if fallback_lang is not None:
        fallback_text = lookup_translation(fallback_lang, key)
        if fallback_text is not None:
            return fallback_text, fallback_lang.value

    return key, fallback_locale


async def resolve_or_enqueue_translation(
    db: AsyncSession,
    *,
    key: str,
    locale: str,
    fallback_language: Optional[str] = None,
    screen: Optional[str] = None,
) -> RuntimeTranslationResult:
    """
    Resolve translation from persistent storage or enqueue async translation job.

    Runtime contract:
    - Return localized value immediately when present.
    - If missing, return fallback text and queue background translation job.
    """
    translation_key = normalize_key(key)
    if not translation_key:
        raise ValueError("key must not be empty")

    requested_locale = normalize_supported_locale(locale)
    if not requested_locale:
        raise ValueError("locale must not be empty")

    fallback_locale = normalize_supported_locale(
        fallback_language or settings.i18n_fallback_language
    )
    source_locale = normalize_supported_locale(settings.i18n_source_language)
    rollout_enabled = is_locale_rollout_enabled(requested_locale)

    def _record(result: RuntimeTranslationResult) -> RuntimeTranslationResult:
        get_i18n_observability().record_runtime_result(
            key=translation_key,
            requested_locale=requested_locale,
            is_fallback=result.is_fallback,
            queue_reason=result.queue_reason,
            source=result.source,
            screen=screen,
        )
        return result

    if not rollout_enabled:
        fallback_text, fallback_text_locale = _resolve_source_text(
            key=translation_key,
            source_locale=source_locale,
            fallback_locale=fallback_locale,
        )
        return _record(
            RuntimeTranslationResult(
                key=translation_key,
                requested_locale=requested_locale,
                resolved_locale=fallback_text_locale,
                text=fallback_text,
                is_fallback=True,
                queued=False,
                queue_reason="rollout_disabled",
                source="fallback",
                status="rollout_disabled",
                rollout_enabled=False,
            )
        )

    resolved = await translation_storage_service.resolve_entry(
        db,
        key=translation_key,
        locale=requested_locale,
        fallback_language=fallback_locale,
    )
    if resolved is not None:
        if (
            requires_manual_review_for_key(translation_key)
            and not is_status_ready_for_tier_a(resolved.status)
        ):
            fallback_text, fallback_text_locale = _resolve_source_text(
                key=translation_key,
                source_locale=source_locale,
                fallback_locale=fallback_locale,
            )
            return _record(
                RuntimeTranslationResult(
                    key=translation_key,
                    requested_locale=requested_locale,
                    resolved_locale=fallback_text_locale,
                    text=fallback_text,
                    is_fallback=True,
                    queued=False,
                    queue_reason="tier_a_requires_manual_review",
                    source="fallback",
                    status=resolved.status,
                    rollout_enabled=True,
                )
            )

        return _record(
            RuntimeTranslationResult(
                key=translation_key,
                requested_locale=requested_locale,
                resolved_locale=resolved.resolved_locale,
                text=resolved.text,
                is_fallback=resolved.is_fallback,
                queued=False,
                queue_reason="storage_hit",
                source="storage",
                status=resolved.status,
                rollout_enabled=True,
            )
        )

    fallback_text, fallback_text_locale = _resolve_source_text(
        key=translation_key,
        source_locale=source_locale,
        fallback_locale=fallback_locale,
    )

    source_hash = make_source_hash(fallback_text)
    enqueue_result = await translation_queue_service.enqueue_missing_translation(
        db,
        key=translation_key,
        target_locale=requested_locale,
        source_text=fallback_text,
        source_locale=source_locale,
        source_hash=source_hash,
    )

    return _record(
        RuntimeTranslationResult(
            key=translation_key,
            requested_locale=requested_locale,
            resolved_locale=fallback_text_locale,
            text=fallback_text,
            is_fallback=True,
            queued=enqueue_result.queued,
            queue_reason=enqueue_result.reason,
            source="fallback",
            status="fallback",
            rollout_enabled=True,
        )
    )
