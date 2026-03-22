"""
Internationalization (i18n) module for Travel Buddy API.

This module provides:
- Language detection and context management
- Translation loading and lookup
- Middleware for FastAPI
"""

from src.i18n.locale import (
    SupportedLanguage,
    LocaleContext,
    LocaleResolution,
    t,
    get_llm_language_instruction,
    load_translations,
    lookup_translation,
    resolve_language,
)
from src.i18n.budget import TranslationBudgetSnapshot, get_translation_budget_guard
from src.i18n.storage import (
    TranslationStatus,
    ResolvedTranslation,
    build_locale_fallback_chain,
    make_source_hash,
    normalize_locale,
    translation_storage_service,
)
from src.i18n.queue import (
    TranslationJobStatus,
    EnqueueResult,
    TranslationQueueStats,
    normalize_supported_locale,
    translation_queue_service,
)
from src.i18n.runtime import RuntimeTranslationResult, resolve_or_enqueue_translation
from src.i18n.worker import translation_queue_worker
from src.i18n.quality import (
    apply_glossary_overrides,
    get_tier_keys,
    is_status_ready_for_tier_a,
    is_tier_a_key,
    is_valid_status_transition,
    requires_manual_review_for_key,
)
from src.i18n.rollout import (
    LocaleRolloutState,
    get_enabled_rollout_locales,
    get_rollout_matrix,
    is_locale_rollout_enabled,
    normalize_rollout_locale,
)
from src.i18n.observability import (
    BudgetAlertState,
    CounterMetric,
    I18nMetricsSnapshot,
    LocaleFallbackRate,
    MissingKeyHit,
    ScreenFallbackHit,
    get_budget_alert_state,
    get_i18n_observability,
)
from src.i18n.middleware import LocaleMiddleware

__all__ = [
    "SupportedLanguage",
    "LocaleContext",
    "LocaleResolution",
    "t",
    "get_llm_language_instruction",
    "load_translations",
    "lookup_translation",
    "resolve_language",
    "TranslationBudgetSnapshot",
    "get_translation_budget_guard",
    "TranslationStatus",
    "ResolvedTranslation",
    "build_locale_fallback_chain",
    "make_source_hash",
    "normalize_locale",
    "translation_storage_service",
    "TranslationJobStatus",
    "EnqueueResult",
    "TranslationQueueStats",
    "normalize_supported_locale",
    "translation_queue_service",
    "RuntimeTranslationResult",
    "resolve_or_enqueue_translation",
    "translation_queue_worker",
    "apply_glossary_overrides",
    "get_tier_keys",
    "is_status_ready_for_tier_a",
    "is_tier_a_key",
    "is_valid_status_transition",
    "requires_manual_review_for_key",
    "LocaleRolloutState",
    "get_enabled_rollout_locales",
    "get_rollout_matrix",
    "is_locale_rollout_enabled",
    "normalize_rollout_locale",
    "BudgetAlertState",
    "CounterMetric",
    "I18nMetricsSnapshot",
    "LocaleFallbackRate",
    "MissingKeyHit",
    "ScreenFallbackHit",
    "get_budget_alert_state",
    "get_i18n_observability",
    "LocaleMiddleware",
]
