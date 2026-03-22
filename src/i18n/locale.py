"""
Language detection and localization utilities.

Provides:
- SupportedLanguage enum with all supported languages
- LocaleContext for request-scoped language storage
- t() function for translation lookup
- LLM language instruction generation
"""

from enum import Enum
from typing import Optional, Any
from functools import lru_cache
from pathlib import Path
from contextvars import ContextVar
from dataclasses import dataclass
import json
import logging

logger = logging.getLogger(__name__)

# Context variable for request-scoped language
_current_language: ContextVar[Optional["SupportedLanguage"]] = ContextVar(
    "current_language", default=None
)


class SupportedLanguage(str, Enum):
    """Supported languages for the application."""

    ENGLISH = "en"
    RUSSIAN = "ru"
    CHINESE = "zh"
    FRENCH = "fr"
    SPANISH = "es"
    ARABIC = "ar"
    GERMAN = "de"

    @classmethod
    def from_code(
        cls,
        code: str,
        fallback: Optional["SupportedLanguage"] = None,
    ) -> "SupportedLanguage":
        """
        Parse language code from various formats.

        Handles:
        - Simple codes: en, ru, zh
        - Regional variants: en-US, zh-Hans, zh-CN
        - Accept-Language quality: en;q=0.9

        Args:
            code: Language code string

        Returns:
            Matching SupportedLanguage or fallback language
        """
        resolved = cls.try_from_code(code)
        if resolved is not None:
            return resolved
        return fallback or cls.ENGLISH

    @classmethod
    def try_from_code(cls, code: str) -> Optional["SupportedLanguage"]:
        """
        Try to parse a language code.

        Returns:
            Matching SupportedLanguage, or None if not supported.
        """
        if not code:
            return None

        # Remove quality value if present (e.g., "en;q=0.9" -> "en")
        normalized = code.split(";")[0].strip().lower()
        if not normalized:
            return None

        # Check exact match first
        for lang in cls:
            if lang.value == normalized:
                return lang

        # Handle Chinese variants
        if normalized.startswith("zh"):
            return cls.CHINESE

        # Extract base language code (e.g., "en-US" -> "en")
        base_code = normalized.split("-")[0]

        for lang in cls:
            if lang.value == base_code:
                return lang

        return None

    @property
    def display_name(self) -> str:
        """Human-readable name in English (for LLM prompts)."""
        names = {
            self.ENGLISH: "English",
            self.RUSSIAN: "Russian",
            self.CHINESE: "Simplified Chinese",
            self.FRENCH: "French",
            self.SPANISH: "Spanish",
            self.ARABIC: "Arabic",
            self.GERMAN: "German",
        }
        return names.get(self, "English")

    @property
    def native_name(self) -> str:
        """Name in the language itself."""
        names = {
            self.ENGLISH: "English",
            self.RUSSIAN: "Русский",
            self.CHINESE: "简体中文",
            self.FRENCH: "Français",
            self.SPANISH: "Español",
            self.ARABIC: "العربية",
            self.GERMAN: "Deutsch",
        }
        return names.get(self, "English")

    @property
    def is_rtl(self) -> bool:
        """Whether this language uses right-to-left text direction."""
        return self == self.ARABIC


class LocaleContext:
    """
    Thread-safe context for the current request's language.

    Uses Python's contextvars to maintain request-scoped state
    in async environments.
    """

    @classmethod
    def get(cls) -> SupportedLanguage:
        """Get current language for this request/context."""
        lang = _current_language.get()
        return lang if lang is not None else SupportedLanguage.ENGLISH

    @classmethod
    def set(cls, language: SupportedLanguage) -> None:
        """Set language for this request/context."""
        _current_language.set(language)

    @classmethod
    def reset(cls) -> None:
        """Reset to default (English)."""
        _current_language.set(None)


@dataclass(frozen=True)
class LocaleResolution:
    """Resolved locale metadata for a request."""

    language: SupportedLanguage
    source: str
    is_fallback: bool
    raw_value: Optional[str] = None


def _parse_accept_language_candidates(header_value: str) -> list[str]:
    """
    Parse Accept-Language and return codes ordered by q-value.
    """
    weighted: list[tuple[float, int, str]] = []
    for index, part in enumerate(header_value.split(",")):
        token = part.strip()
        if not token:
            continue

        code = token
        q = 1.0

        if ";" in token:
            code, *params = token.split(";")
            code = code.strip()
            for param in params:
                param = param.strip()
                if param.startswith("q="):
                    try:
                        q = float(param.split("=", 1)[1])
                    except ValueError:
                        q = 0.0
                    break

        if not code or code == "*":
            continue

        weighted.append((q, index, code))

    weighted.sort(key=lambda item: (-item[0], item[1]))
    return [code for _, _, code in weighted]


def resolve_language(
    *,
    fallback_language: SupportedLanguage,
    profile_locale: Optional[str] = None,
    query_locale: Optional[str] = None,
    explicit_locale: Optional[str] = None,
    accept_language: Optional[str] = None,
) -> LocaleResolution:
    """
    Resolve request language with explicit precedence.

    Priority:
    1. profile_locale
    2. query_locale
    3. explicit_locale (X-Language)
    4. Accept-Language
    5. fallback_language
    """
    if profile_locale:
        resolved = SupportedLanguage.try_from_code(profile_locale)
        if resolved is not None:
            return LocaleResolution(
                language=resolved,
                source="profile",
                is_fallback=False,
                raw_value=profile_locale,
            )

    if query_locale:
        resolved = SupportedLanguage.try_from_code(query_locale)
        if resolved is not None:
            return LocaleResolution(
                language=resolved,
                source="query",
                is_fallback=False,
                raw_value=query_locale,
            )

    if explicit_locale:
        resolved = SupportedLanguage.try_from_code(explicit_locale)
        if resolved is not None:
            return LocaleResolution(
                language=resolved,
                source="header",
                is_fallback=False,
                raw_value=explicit_locale,
            )

    if accept_language:
        for candidate in _parse_accept_language_candidates(accept_language):
            resolved = SupportedLanguage.try_from_code(candidate)
            if resolved is not None:
                return LocaleResolution(
                    language=resolved,
                    source="accept-language",
                    is_fallback=False,
                    raw_value=candidate,
                )

    return LocaleResolution(
        language=fallback_language,
        source="fallback",
        is_fallback=True,
        raw_value=fallback_language.value,
    )


@lru_cache(maxsize=10)
def load_translations(language: SupportedLanguage) -> dict:
    """
    Load translation file for a language.

    Uses LRU cache to avoid repeated file reads.

    Args:
        language: The language to load translations for

    Returns:
        Dictionary of translation keys to values
    """
    translations_dir = Path(__file__).parent / "translations"
    file_path = translations_dir / f"{language.value}.json"

    if not file_path.exists():
        logger.warning(f"Translation file not found: {file_path}, falling back to English")
        file_path = translations_dir / "en.json"

    if not file_path.exists():
        logger.error("English translation file not found!")
        return {}

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in translation file {file_path}: {e}")
        return {}


def t(key: str, **kwargs: Any) -> str:
    """
    Get translated string for current locale.

    Supports:
    - Nested keys with dot notation: "errors.trip_not_found"
    - String interpolation: t("errors.trip_not_found", trip_id=123)
    - Fallback to English if key not found in current language
    - Fallback to key itself if not found anywhere

    Args:
        key: Translation key (dot-separated for nested access)
        **kwargs: Values to interpolate into the string

    Returns:
        Translated and interpolated string

    Example:
        >>> t("errors.trip_not_found", trip_id="abc-123")
        "Trip with ID abc-123 not found"
    """
    language = LocaleContext.get()
    translations = load_translations(language)

    # Navigate nested keys
    value = _get_nested(translations, key)

    # Fallback to English if not found
    if value is None and language != SupportedLanguage.ENGLISH:
        english_translations = load_translations(SupportedLanguage.ENGLISH)
        value = _get_nested(english_translations, key)

    # Fallback to key itself
    if value is None:
        logger.warning(f"Translation not found for key: {key}")
        return key

    # Interpolate values
    if kwargs:
        try:
            return value.format(**kwargs)
        except KeyError as e:
            logger.warning(f"Missing interpolation key {e} for translation: {key}")
            return value

    return value


def _get_nested(data: dict, key: str) -> Optional[str]:
    """
    Get value from nested dictionary using dot notation.

    Args:
        data: Dictionary to search
        key: Dot-separated key path (e.g., "errors.trip_not_found")

    Returns:
        String value if found, None otherwise
    """
    parts = key.split(".")
    current = data

    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None

    return current if isinstance(current, str) else None


def lookup_translation(language: SupportedLanguage, key: str) -> Optional[str]:
    """
    Lookup raw translation value for a specific language and key.
    """
    translations = load_translations(language)
    return _get_nested(translations, key)


def get_llm_language_instruction(language: Optional[SupportedLanguage] = None) -> str:
    """
    Generate instruction for LLM to respond in specific language.

    This instruction should be appended to LLM system prompts to ensure
    the model responds in the user's preferred language.

    Args:
        language: Target language (defaults to current context)

    Returns:
        Instruction string to append to LLM prompt
    """
    lang = language or LocaleContext.get()

    return f"\n\nIMPORTANT: You MUST respond in {lang.display_name}. All user-facing text in your response must be in {lang.display_name}."


def get_google_places_language(language: Optional[SupportedLanguage] = None) -> str:
    """
    Get language code for Google Places API.

    Args:
        language: Target language (defaults to current context)

    Returns:
        Language code compatible with Google Places API
    """
    lang = language or LocaleContext.get()

    # Google Places uses slightly different codes for some languages
    google_codes = {
        SupportedLanguage.CHINESE: "zh-CN",  # Simplified Chinese
        SupportedLanguage.ARABIC: "ar",
    }

    return google_codes.get(lang, lang.value)
