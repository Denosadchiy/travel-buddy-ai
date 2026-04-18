"""
Streaming Q&A Pipeline — Step 10.

Flow:
  audio bytes → STT → build LLM context → LLM → sentence buffer → TTS → SSE events

Latency target: < 2.5 s from upload to first audio chunk.

Key design decisions:
- LLM: no native streaming in IoNetLLMClient (uses OpenAI sync client via anyio thread).
  Fallback: call generate_text(), then split answer into sentences and yield one by one.
  This adds ~0 ms to total latency (text is already generated) but allows TTS to start
  on the first sentence while the response is already complete.
- TTS: ElevenLabsClient.synthesize_batch() per sentence for simplicity.
  First chunk: base64 inline in SSE (no S3 upload latency).
  Subsequent chunks: S3 upload → CDN URL.
- GPS/QA limits: checked synchronously from NavigationRepository at start.
- Fire-and-forget: save_qa_entry() is fired after yielding 'done'.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
import uuid
from typing import TYPE_CHECKING, AsyncIterator, Optional
from uuid import UUID

from src.config import Settings, settings as _default_settings

if TYPE_CHECKING:
    from src.guide.application.navigation_repository import NavigationRepository
    from src.guide.infrastructure.elevenlabs_client import ElevenLabsClient
    from src.guide.infrastructure.s3_client import GuideS3Client
    from src.guide.infrastructure.stt_client import STTClient
    from src.infrastructure.llm_client import LLMClient

logger = logging.getLogger(__name__)

# Minimum sentence length before synthesising separately (avoid tiny "Yes." clips)
_MIN_SENTENCE_CHARS = 20


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_complete_sentence(text: str) -> Optional[str]:
    """
    Return the first complete sentence from text, or None.

    A sentence ends at . ! ? followed by a space (or end of string for the
    last sentence). Minimum length: _MIN_SENTENCE_CHARS characters.
    """
    match = re.search(r'[.!?][\s]', text)
    if match and match.end() >= _MIN_SENTENCE_CHARS:
        return text[:match.end()]
    return None


def _split_into_sentences(text: str) -> list[str]:
    """Split a completed text block into sentences for TTS chunking."""
    parts = re.split(r'(?<=[.!?])\s+', text.strip())
    return [p.strip() for p in parts if p.strip()]


def _build_qa_prompt(
    location_context: str,
    main_knowledge: str,
    neighbor_names: str,
    qa_history: str,
    question: str,
    language: str,
    detail_level: str,
) -> str:
    return (
        f"You are an audio guide. The user is near: {location_context}.\n\n"
        f"About this place:\n{main_knowledge}\n\n"
        f"Nearby: {neighbor_names}\n\n"
        f"Previous Q&A this session:\n{qa_history}\n\n"
        f"User question: {question}\n\n"
        f"Answer in {language}, {detail_level} style. "
        f"Keep to 2-4 sentences (spoken audio, not text). "
        f"End with a natural bridge back to the tour narrative."
    )


# ---------------------------------------------------------------------------
# QAPipeline
# ---------------------------------------------------------------------------

class QAPipeline:
    """Orchestrates the full audio Q&A flow: STT → LLM → TTS → SSE events."""

    def __init__(
        self,
        stt_client: "STTClient",
        llm_client: "LLMClient",
        elevenlabs_client: "ElevenLabsClient",
        s3_client: "GuideS3Client",
        repo: "NavigationRepository",
        settings: Settings = _default_settings,
    ) -> None:
        self._stt = stt_client
        self._llm = llm_client
        self._tts = elevenlabs_client
        self._s3 = s3_client
        self._repo = repo
        self._settings = settings

    # -------------------------------------------------------------------------
    # Public generator
    # -------------------------------------------------------------------------

    async def process_question(
        self,
        session_id: UUID,
        audio_bytes: bytes,
        audio_mime: str,
        current_point_id: Optional[UUID],
    ) -> AsyncIterator[dict]:
        """
        Async generator yielding SSE event dicts:
          {"event": "transcript", "data": {...}}
          {"event": "answer_chunk", "data": {"text": "..."}}
          {"event": "audio_chunk", "data": {"base64": "...", "chunk_index": 0, "mime": "audio/mpeg"}}
          {"event": "audio_chunk", "data": {"url": "...", "chunk_index": N}}
          {"event": "done", "data": {"qa_entry_id": "uuid"}}
          {"event": "error", "data": {"code": "...", "message": "..."}}
        """
        # --- Load session info ---
        session = await self._repo.get_session(session_id)
        if session is None:
            yield {"event": "error", "data": {"code": "session_not_found", "message": "Session not found"}}
            return

        language = session.language or "en"
        detail_level = session.detail_level or "standard"
        voice_id = session.voice_id

        # --- Q&A rate limit ---
        if not await self._check_qa_limit(session):
            yield {"event": "error", "data": {"code": "qa_limit_reached", "message": "Q&A limit reached for this session"}}
            return

        # --- STT ---
        try:
            transcript = await self._stt.transcribe(audio_bytes, language=language, mime_type=audio_mime)
        except Exception as exc:
            logger.warning("STT failed for session %s: %s", session_id, exc)
            yield {"event": "error", "data": {"code": "stt_failed", "message": str(exc)}}
            return

        if not transcript or len(transcript.strip()) < 3:
            yield {"event": "error", "data": {"code": "stt_empty", "message": "Could not understand the question"}}
            return

        transcript = transcript.strip()[:self._settings.guide_qa_max_transcript_chars]
        yield {"event": "transcript", "data": {"text": transcript}}

        # --- LLM context ---
        prompt = await self._build_qa_context(session, current_point_id, transcript)

        # --- LLM call (non-streaming fallback) ---
        try:
            answer_text = await asyncio.wait_for(
                self._llm.generate_text(
                    prompt=prompt,
                    max_tokens=self._settings.guide_qa_max_answer_tokens,
                ),
                timeout=self._settings.guide_qa_llm_timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.warning("LLM timed out for Q&A session %s", session_id)
            yield {"event": "error", "data": {
                "code": "llm_timeout",
                "message": "Good question! Let me continue the tour.",
            }}
            return
        except Exception as exc:
            logger.warning("LLM failed for Q&A session %s: %s", session_id, exc)
            yield {"event": "error", "data": {"code": "llm_failed", "message": str(exc)}}
            return

        answer_text = answer_text.strip()

        # --- Yield text chunks ---
        sentences = _split_into_sentences(answer_text)
        for sentence in sentences:
            yield {"event": "answer_chunk", "data": {"text": sentence + " "}}

        # --- TTS: synthesize per sentence ---
        qa_entry_id = uuid.uuid4()
        voice = await self._repo.get_active_voices()
        # Find matching voice for elevenlabs_voice_id
        elevenlabs_voice_id = await self._get_elevenlabs_voice_id(voice_id)

        tts_failed = False
        for chunk_index, sentence in enumerate(sentences):
            if not sentence:
                continue
            try:
                audio_chunk = await self._tts.synthesize_batch(
                    text=sentence,
                    voice_id=elevenlabs_voice_id,
                )
            except Exception as exc:
                logger.warning("TTS failed chunk %d for session %s: %s", chunk_index, session_id, exc)
                tts_failed = True
                break

            if chunk_index == 0:
                # First chunk: base64 inline (no S3 latency)
                b64 = base64.b64encode(audio_chunk).decode()
                yield {
                    "event": "audio_chunk",
                    "data": {"base64": b64, "chunk_index": 0, "mime": "audio/mpeg"},
                }
            else:
                # Subsequent chunks: S3 upload → CDN URL
                try:
                    key = f"guide/qa/{session_id}/{qa_entry_id}/chunk_{chunk_index}.mp3"
                    cdn_url = await self._s3.upload_audio(key, audio_chunk)
                    yield {
                        "event": "audio_chunk",
                        "data": {"url": cdn_url, "chunk_index": chunk_index},
                    }
                except Exception as exc:
                    logger.warning("S3 upload failed chunk %d session %s: %s", chunk_index, session_id, exc)
                    # Continue — client still has previous chunks

        if tts_failed and all(s == sentences[0] for s in sentences[:1]):
            # TTS failed on first sentence — no audio at all, but text was sent
            logger.warning("TTS completely failed for session %s, text-only response sent", session_id)

        # --- Save Q&A (fire-and-forget) ---
        async def _save():
            try:
                from src.infrastructure.database import AsyncSessionLocal
                async with AsyncSessionLocal() as bg_db:
                    from src.guide.application.navigation_repository import NavigationRepository as _Repo
                    bg_repo = _Repo(bg_db)
                    await bg_repo.save_qa_entry(
                        session_id=session_id,
                        question_text=transcript,
                        answer_text=answer_text,
                        point_id=current_point_id,
                        qa_entry_id=qa_entry_id,
                    )
                    await bg_db.commit()
            except Exception as exc:
                logger.warning("Failed to save Q&A entry %s: %s", qa_entry_id, exc)

        asyncio.create_task(_save())

        yield {"event": "done", "data": {"qa_entry_id": str(qa_entry_id)}}

    # -------------------------------------------------------------------------
    # Context building
    # -------------------------------------------------------------------------

    async def _build_qa_context(
        self,
        session,
        current_point_id: Optional[UUID],
        question: str,
    ) -> str:
        language = session.language or "en"
        detail_level = session.detail_level or "standard"

        # Q&A history
        qa_entries = await self._repo.get_session_qa_history(session.id, limit=5)
        qa_history = "\n".join(
            f"Q: {e.question_text}\nA: {e.answer_text}" for e in qa_entries
        ) or "(none)"

        # Current point knowledge
        location_context = "the current location"
        main_knowledge = "No additional information available."
        neighbor_names = ""

        if current_point_id is not None:
            # Load point info
            from src.guide.domain.models import GuidePoint
            point = await self._repo._db.get(GuidePoint, current_point_id)
            if point is not None:
                location_context = point.name or location_context

            card = await self._repo.get_knowledge_card_for_qa(current_point_id)

            if card and card.get("card_type") == "street_context":
                # Connector fallback: use nearest POI knowledge
                main_knowledge = f"On {card.get('street_name', 'a nearby street')}."
                if card.get("wikipedia_summary"):
                    main_knowledge += f" {card['wikipedia_summary']}"
            elif card and card.get("wikipedia_summary"):
                main_knowledge = card["wikipedia_summary"]

        return _build_qa_prompt(
            location_context=location_context,
            main_knowledge=main_knowledge,
            neighbor_names=neighbor_names,
            qa_history=qa_history,
            question=question,
            language=language,
            detail_level=detail_level,
        )

    # -------------------------------------------------------------------------
    # Q&A rate limit
    # -------------------------------------------------------------------------

    async def _check_qa_limit(self, session) -> bool:
        """True if the user is within Q&A quota."""
        qa_count = await self._repo.count_session_qa(session.id)
        seconds_billed = getattr(session, "total_seconds_billed", 0) or 0
        max_questions = max(1, seconds_billed // 90)
        return qa_count < max_questions

    # -------------------------------------------------------------------------
    # Voice lookup
    # -------------------------------------------------------------------------

    async def _get_elevenlabs_voice_id(self, voice_id: UUID) -> str:
        """Return the ElevenLabs voice ID string for the session's voice."""
        from src.guide.domain.models import GuideVoice
        voice = await self._repo._db.get(GuideVoice, voice_id)
        if voice is not None and voice.elevenlabs_voice_id:
            return voice.elevenlabs_voice_id
        # Fallback to settings default or a safe default
        return getattr(self._settings, "elevenlabs_voice_id", "21m00Tcm4TlvDq8ikWAM")
