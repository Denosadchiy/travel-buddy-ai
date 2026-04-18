"""
Speech-to-Text clients for Live Guide Q&A pipeline.

Primary:  Deepgram Nova-2 (low latency, accurate EN/RU)
Fallback: OpenAI Whisper (via REST API)

Factory function get_stt_client() selects provider from settings.stt_provider.
"""
import logging
from abc import ABC, abstractmethod

import httpx

from src.config import settings

logger = logging.getLogger(__name__)


class STTClient(ABC):
    """Abstract base for speech-to-text providers."""

    @abstractmethod
    async def transcribe(
        self,
        audio_bytes: bytes,
        language: str,
        mime_type: str = "audio/mpeg",
    ) -> str:
        """Transcribe audio bytes → plain text transcript."""
        ...


class DeepgramSTTClient(STTClient):
    """Deepgram Nova-2 — primary STT provider."""

    _BASE_URL = "https://api.deepgram.com/v1/listen"

    def __init__(self, api_key: str, timeout: int = 30) -> None:
        self._api_key = api_key
        self._timeout = timeout

    async def transcribe(
        self,
        audio_bytes: bytes,
        language: str,
        mime_type: str = "audio/mpeg",
    ) -> str:
        params = {"model": "nova-2", "language": language}
        headers = {
            "Authorization": f"Token {self._api_key}",
            "Content-Type": mime_type,
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                self._BASE_URL,
                params=params,
                headers=headers,
                content=audio_bytes,
            )
            resp.raise_for_status()
            data = resp.json()
            try:
                return data["results"]["channels"][0]["alternatives"][0]["transcript"]
            except (KeyError, IndexError) as exc:
                logger.error("Deepgram unexpected response structure: %s", data)
                raise ValueError("Failed to parse Deepgram transcript") from exc


class WhisperSTTClient(STTClient):
    """OpenAI Whisper — fallback STT provider."""

    _BASE_URL = "https://api.openai.com/v1/audio/transcriptions"

    def __init__(self, api_key: str, timeout: int = 60) -> None:
        self._api_key = api_key
        self._timeout = timeout

    async def transcribe(
        self,
        audio_bytes: bytes,
        language: str,
        mime_type: str = "audio/mpeg",
    ) -> str:
        ext = mime_type.split("/")[-1].replace("mpeg", "mp3")
        headers = {"Authorization": f"Bearer {self._api_key}"}
        files = {"file": (f"audio.{ext}", audio_bytes, mime_type)}
        data = {"model": "whisper-1", "language": language[:2]}  # ISO 639-1
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                self._BASE_URL,
                headers=headers,
                files=files,
                data=data,
            )
            resp.raise_for_status()
            return resp.json().get("text", "")


def get_stt_client() -> STTClient:
    """Factory: returns STT client based on settings.stt_provider."""
    provider = settings.stt_provider
    if provider == "deepgram":
        return DeepgramSTTClient(
            api_key=settings.deepgram_api_key,
            timeout=settings.stt_timeout_seconds,
        )
    if provider == "whisper":
        return WhisperSTTClient(
            api_key=settings.openai_api_key,
            timeout=settings.stt_timeout_seconds,
        )
    raise ValueError(f"Unknown STT provider: {provider!r}. Use 'deepgram' or 'whisper'.")
