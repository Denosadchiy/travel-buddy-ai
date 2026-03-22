"""
Machine translation provider adapters for i18n pipeline.
"""

from __future__ import annotations

from html import unescape
from typing import Optional, Protocol

import httpx

from src.config import settings


class MachineTranslationProvider(Protocol):
    async def translate_text(
        self,
        *,
        text: str,
        source_locale: str,
        target_locale: str,
    ) -> str:
        """Translate text from source locale to target locale."""


class EchoTranslationProvider:
    """
    Zero-cost provider for test environments.

    Returns source text unchanged. Useful to validate queue/worker flow
    without external API spend.
    """

    async def translate_text(
        self,
        *,
        text: str,
        source_locale: str,
        target_locale: str,
    ) -> str:
        _ = source_locale
        _ = target_locale
        return text


class GoogleTranslationProvider:
    """
    Google Cloud Translation API v2 adapter.
    """

    _url = "https://translation.googleapis.com/language/translate/v2"

    async def translate_text(
        self,
        *,
        text: str,
        source_locale: str,
        target_locale: str,
    ) -> str:
        if not settings.google_translate_api_key:
            raise RuntimeError("GOOGLE_TRANSLATE_API_KEY is not configured")

        payload = {
            "q": text,
            "source": source_locale,
            "target": target_locale,
            "format": "text",
        }

        async with httpx.AsyncClient(
            timeout=settings.i18n_translation_timeout_seconds
        ) as client:
            response = await client.post(
                self._url,
                params={"key": settings.google_translate_api_key},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        translations = data.get("data", {}).get("translations", [])
        if not translations:
            raise RuntimeError("Google Translation API returned empty response")

        translated = unescape(translations[0].get("translatedText", "")).strip()
        if not translated:
            raise RuntimeError("Google Translation API returned blank translation")
        return translated


_translation_provider: Optional[MachineTranslationProvider] = None


def get_machine_translation_provider() -> MachineTranslationProvider:
    """Get singleton machine translation provider by settings."""
    global _translation_provider
    if _translation_provider is not None:
        return _translation_provider

    provider = settings.i18n_translation_provider.strip().lower()
    if provider == "google":
        _translation_provider = GoogleTranslationProvider()
    else:
        _translation_provider = EchoTranslationProvider()
    return _translation_provider

