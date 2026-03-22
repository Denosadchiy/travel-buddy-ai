"""
Per-locale rollout feature flags for i18n runtime.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.config import settings
from src.i18n.locale import SupportedLanguage


def normalize_rollout_locale(locale: str) -> str:
    resolved = SupportedLanguage.try_from_code(locale)
    if resolved is not None:
        return resolved.value
    return (locale or "").strip().replace("_", "-").lower()


def get_enabled_rollout_locales() -> set[str]:
    enabled = {
        normalize_rollout_locale(locale)
        for locale in settings.i18n_rollout_enabled_locales_list
    }
    enabled.add(normalize_rollout_locale(settings.i18n_source_language))
    enabled.add(normalize_rollout_locale(settings.i18n_fallback_language))
    return {locale for locale in enabled if locale}


def is_locale_rollout_enabled(locale: str) -> bool:
    if not settings.i18n_rollout_enforced:
        return True
    normalized_locale = normalize_rollout_locale(locale)
    return normalized_locale in get_enabled_rollout_locales()


@dataclass(frozen=True)
class LocaleRolloutState:
    locale: str
    enabled: bool


def get_rollout_matrix() -> list[LocaleRolloutState]:
    enabled = get_enabled_rollout_locales()
    result: list[LocaleRolloutState] = []
    for locale in settings.i18n_supported_languages_list:
        normalized = normalize_rollout_locale(locale)
        flag = True if not settings.i18n_rollout_enforced else normalized in enabled
        result.append(LocaleRolloutState(locale=normalized, enabled=flag))
    return result

