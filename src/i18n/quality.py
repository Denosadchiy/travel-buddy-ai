"""
Quality workflow rules for localization lifecycle and glossary enforcement.
"""

from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path

from src.config import settings
from src.i18n.locale import SupportedLanguage


QUALITY_DIR = Path(__file__).resolve().parent
KEY_TIERS_PATH = QUALITY_DIR / "key_tiers.json"
GLOSSARY_PATH = QUALITY_DIR / "glossary.json"

VALID_TIERS = {"tier_a", "tier_b", "tier_c"}
TIER_A_READY_STATUSES = {"reviewed", "approved"}

# Status lifecycle for quality workflow (no downgrade path).
ALLOWED_STATUS_TRANSITIONS = {
    "draft": {"draft", "mt", "reviewed", "approved"},
    "mt": {"mt", "reviewed"},
    "reviewed": {"reviewed", "approved"},
    "approved": {"approved"},
}


def _normalize_locale_for_quality(locale: str) -> str:
    resolved = SupportedLanguage.try_from_code(locale)
    if resolved is not None:
        return resolved.value
    return (locale or "").strip().replace("_", "-").lower()


def _normalize_key_for_quality(key: str) -> str:
    return (key or "").strip()


@lru_cache(maxsize=1)
def load_key_tiers() -> dict[str, set[str]]:
    if not KEY_TIERS_PATH.exists():
        return {tier: set() for tier in VALID_TIERS}

    try:
        payload = json.loads(KEY_TIERS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {tier: set() for tier in VALID_TIERS}

    tiers: dict[str, set[str]] = {}
    for tier in VALID_TIERS:
        values = payload.get(tier, [])
        if isinstance(values, list):
            tiers[tier] = {
                _normalize_key_for_quality(item)
                for item in values
                if isinstance(item, str) and _normalize_key_for_quality(item)
            }
        else:
            tiers[tier] = set()
    return tiers


def get_tier_keys(tier: str) -> set[str]:
    normalized_tier = (tier or "").strip().lower()
    if normalized_tier not in VALID_TIERS:
        return set()
    return set(load_key_tiers().get(normalized_tier, set()))


def is_tier_a_key(key: str) -> bool:
    translation_key = _normalize_key_for_quality(key)
    if not translation_key:
        return False
    return translation_key in load_key_tiers().get("tier_a", set())


def requires_manual_review_for_key(key: str) -> bool:
    if not settings.i18n_tier_a_require_manual_review:
        return False
    return is_tier_a_key(key)


def is_status_ready_for_tier_a(status: str) -> bool:
    return (status or "").strip().lower() in TIER_A_READY_STATUSES


def is_valid_status_transition(current_status: str, target_status: str) -> bool:
    current = (current_status or "").strip().lower()
    target = (target_status or "").strip().lower()
    allowed = ALLOWED_STATUS_TRANSITIONS.get(current)
    if allowed is None:
        return False
    return target in allowed


@lru_cache(maxsize=1)
def load_glossary_overrides() -> dict[str, dict[str, str]]:
    if not GLOSSARY_PATH.exists():
        return {}

    try:
        payload = json.loads(GLOSSARY_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}

    if not isinstance(payload, dict):
        return {}

    normalized: dict[str, dict[str, str]] = {}
    for raw_locale, raw_map in payload.items():
        if not isinstance(raw_locale, str) or not isinstance(raw_map, dict):
            continue
        locale = _normalize_locale_for_quality(raw_locale)
        replacements: dict[str, str] = {}
        for source, target in raw_map.items():
            if (
                isinstance(source, str)
                and isinstance(target, str)
                and source.strip()
                and target.strip()
            ):
                replacements[source] = target
        if replacements:
            normalized[locale] = replacements
    return normalized


def apply_glossary_overrides(text: str, target_locale: str) -> str:
    if not settings.i18n_glossary_overrides_enabled:
        return text

    value = text or ""
    if not value:
        return value

    glossary = load_glossary_overrides()
    locale = _normalize_locale_for_quality(target_locale)

    replacements: dict[str, str] = {}
    replacements.update(glossary.get("default", {}))
    replacements.update(glossary.get(locale, {}))

    for source, target in replacements.items():
        if source in value:
            value = value.replace(source, target)
    return value
