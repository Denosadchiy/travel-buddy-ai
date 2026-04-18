"""
ElevenLabs TTS client — batch synthesis and WebSocket streaming.

Production code uses httpx + websockets directly. MCP is a dev tool only.
Selected model: eleven_multilingual_v2 (batch, EN+RU quality)
              eleven_turbo_v2_5    (streaming Q&A, low latency EN+RU)
"""
import asyncio
import base64
import json
import logging
from typing import AsyncIterator

import httpx
import websockets

from src.config import settings

logger = logging.getLogger(__name__)

_SENTENCE_ENDINGS = frozenset(".!?")


class ElevenLabsClient:
    """Thin HTTP/WebSocket client for ElevenLabs TTS API."""

    def __init__(self) -> None:
        self._base_url = settings.elevenlabs_base_url.rstrip("/")
        self._api_key = settings.elevenlabs_api_key
        self._model_id = settings.elevenlabs_model_id
        self._streaming_model_id = settings.elevenlabs_streaming_model_id
        self._timeout = settings.elevenlabs_timeout_seconds

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def synthesize_batch(
        self,
        text: str,
        voice_id: str,
        output_format: str = "mp3_44100_128",
    ) -> bytes:
        """POST /v1/text-to-speech/{voice_id} → raw MP3 bytes.

        Retries up to 3 times with exponential backoff on 429/5xx.
        """
        url = f"{self._base_url}/v1/text-to-speech/{voice_id}"
        payload = {
            "text": text,
            "model_id": self._model_id,
            "output_format": output_format,
        }
        headers = self._auth_headers({"Accept": "audio/mpeg"})

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            for attempt in range(3):
                try:
                    resp = await client.post(url, json=payload, headers=headers)
                    if resp.status_code in (429, 500, 502, 503, 504):
                        wait = 2 ** attempt
                        logger.warning(
                            "ElevenLabs synthesize_batch HTTP %d, retry %d/%d in %ds",
                            resp.status_code, attempt + 1, 3, wait,
                        )
                        await asyncio.sleep(wait)
                        continue
                    resp.raise_for_status()
                    return resp.content
                except httpx.TimeoutException:
                    if attempt == 2:
                        raise
                    await asyncio.sleep(2 ** attempt)
            resp.raise_for_status()  # propagate last error
            return b""  # unreachable

    async def synthesize_stream(
        self,
        text_stream: AsyncIterator[str],
        voice_id: str,
    ) -> AsyncIterator[bytes]:
        """WebSocket /v1/text-to-speech/{voice_id}/stream-input → audio chunk iterator.

        Buffers input text until a sentence boundary (. ! ? followed by space/EOF)
        before flushing to ElevenLabs, reducing audio latency for the first chunk.
        """
        ws_url = (
            f"wss://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream-input"
            f"?model_id={self._streaming_model_id}&output_format=mp3_44100_128"
            f"&xi-api-key={self._api_key}"
        )
        extra_headers = {"xi-api-key": self._api_key}

        async with websockets.connect(ws_url, additional_headers=extra_headers) as ws:
            # BOS: initial context with voice settings
            await ws.send(json.dumps({
                "text": " ",
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
                "generation_config": {"chunk_length_schedule": [50]},
            }))

            # Producer: send buffered text chunks
            async def _send_text() -> None:
                buffer = ""
                async for chunk in text_stream:
                    buffer += chunk
                    # Flush at sentence boundaries
                    flush_idx = -1
                    for i, ch in enumerate(buffer):
                        if ch in _SENTENCE_ENDINGS and i + 1 < len(buffer) and buffer[i + 1] == " ":
                            flush_idx = i + 1
                    if flush_idx >= 0:
                        await ws.send(json.dumps({
                            "text": buffer[: flush_idx + 1],
                            "try_trigger_generation": True,
                        }))
                        buffer = buffer[flush_idx + 1 :]
                # Flush remainder + EOS
                if buffer:
                    await ws.send(json.dumps({"text": buffer, "try_trigger_generation": True}))
                await ws.send(json.dumps({"text": ""}))  # EOS

            send_task = asyncio.create_task(_send_text())

            try:
                async for raw in ws:
                    msg = json.loads(raw)
                    if audio_b64 := msg.get("audio"):
                        yield base64.b64decode(audio_b64)
                    if msg.get("isFinal"):
                        break
            finally:
                send_task.cancel()
                try:
                    await send_task
                except asyncio.CancelledError:
                    pass

    async def get_voices(self) -> list[dict]:
        """GET /v1/voices → list of {voice_id, name, labels, preview_url}."""
        url = f"{self._base_url}/v1/voices"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(url, headers=self._auth_headers())
            resp.raise_for_status()
            voices = resp.json().get("voices", [])
            return [
                {
                    "voice_id": v["voice_id"],
                    "name": v["name"],
                    "labels": v.get("labels", {}),
                    "preview_url": v.get("preview_url"),
                }
                for v in voices
            ]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _auth_headers(self, extra: dict | None = None) -> dict:
        headers = {"xi-api-key": self._api_key, "Content-Type": "application/json"}
        if extra:
            headers.update(extra)
        return headers
