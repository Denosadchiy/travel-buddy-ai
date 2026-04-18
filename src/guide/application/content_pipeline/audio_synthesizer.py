"""
AudioSynthesizer — Stage 4 of the Content Pipeline.

Batch ElevenLabs TTS synthesis for all 'reviewed' content blocks in a zone:
  1. Load 'reviewed' blocks
  2. Mark as 'synthesizing' (bulk)
  3. For each block (parallel, rate-limited by semaphore):
     a. ElevenLabs synthesize_batch()
     b. FFmpeg post-processing (loudnorm → apad → afade)
     c. S3 upload → CDN URL
     d. Audio QA checks (duration range, leading silence)
     e. Update guide_content_blocks: audio_url, duration, synthesized_at, status='synthesized'
  4. Collect spot-check URLs for manual spot-check
  5. Mark job complete with stats

FFmpeg fallback: if ffmpeg binary not found in PATH, post-processing is skipped
with a WARNING (raw ElevenLabs bytes are uploaded directly). This allows
development without ffmpeg installed.

Duration detection: uses mutagen.mp3.MP3 (fast, no subprocess).
If mutagen is unavailable, falls back to word-count heuristic.
"""
from __future__ import annotations

import asyncio
import logging
import random
import shutil
from asyncio import subprocess as asubprocess
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from src.config import settings as _default_settings

if TYPE_CHECKING:
    from src.guide.application.content_pipeline.repository import ContentPipelineRepository
    from src.guide.infrastructure.elevenlabs_client import ElevenLabsClient
    from src.guide.infrastructure.s3_client import GuideS3Client

logger = logging.getLogger(__name__)

# Expected audio duration ranges per content_type (seconds)
EXPECTED_DURATION: dict[str, tuple[float, float]] = {
    "main":            (15.0, 90.0),
    "bonus":           (10.0, 60.0),
    "transition":      (3.0,  20.0),
    "zone_transition": (5.0,  25.0),
    "recap":           (3.0,  15.0),
}

# How many spot-check samples per content_type to include in job progress
_SPOT_CHECK_COUNT = 1


class AudioSynthesizer:
    """Batch TTS synthesizer for Stage 4 of the Content Pipeline."""

    def __init__(
        self,
        repo: "ContentPipelineRepository",
        elevenlabs_client: "ElevenLabsClient",
        s3_client: "GuideS3Client",
        app_settings=None,
    ) -> None:
        self._repo = repo
        self._tts = elevenlabs_client
        self._s3 = s3_client
        self._settings = app_settings or _default_settings
        max_parallel = getattr(self._settings, "guide_tts_max_parallel", 3)
        self._semaphore = asyncio.Semaphore(max_parallel)
        self._ffmpeg_available: Optional[bool] = None  # lazily detected

    # -------------------------------------------------------------------------
    # Public entry point
    # -------------------------------------------------------------------------

    async def synthesize_zone(
        self,
        zone_id: UUID,
        voice_ids: Optional[list[UUID]] = None,
        force_resynthesize: bool = False,
        job_id: Optional[UUID] = None,
    ) -> dict:
        """
        Synthesize audio for all 'reviewed' blocks in the zone.

        With force_resynthesize=True: also re-synthesizes already 'synthesized' blocks.
        Returns stats: {synthesized, failed, total_duration_s, spot_check_urls}.
        """
        self._ffmpeg_available = self._check_ffmpeg()

        blocks = await self._repo.get_reviewed_blocks(
            zone_id,
            voice_ids=voice_ids,
            include_synthesized=force_resynthesize,
        )

        if not blocks:
            logger.info("AudioSynthesizer: no reviewed blocks found for zone %s", zone_id)
            return {"synthesized": 0, "failed": 0, "total_duration_s": 0.0, "spot_check_urls": []}

        # Bulk mark as synthesizing
        await self._repo.bulk_update_status([b.id for b in blocks], "synthesizing")

        stats = {"synthesized": 0, "failed": 0, "total_duration_s": 0.0}
        spot_check_by_type: dict[str, str] = {}

        tasks = [
            self._synthesize_block(block, stats, spot_check_by_type)
            for block in blocks
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

        spot_check_urls = list(spot_check_by_type.values())
        result = {**stats, "spot_check_urls": spot_check_urls}

        if job_id is not None:
            await self._repo.update_job_progress(job_id, {
                "phase": "audio_synthesis",
                "total": len(blocks),
                **result,
            })
            await self._repo.mark_job_complete(job_id, result)

        logger.info("AudioSynthesizer: done zone %s — %s", zone_id, stats)
        return result

    # -------------------------------------------------------------------------
    # Per-block synthesis
    # -------------------------------------------------------------------------

    async def _synthesize_block(
        self,
        block,
        stats: dict,
        spot_check_by_type: dict,
    ) -> None:
        async with self._semaphore:
            try:
                await self._do_synthesize(block, stats, spot_check_by_type)
            except Exception as exc:
                logger.error(
                    "TTS failed for block %s (%s/%s): %s",
                    block.id, block.content_type, block.language, exc,
                )
                await self._repo.mark_block_failed(block.id)
                stats["failed"] += 1

    async def _do_synthesize(self, block, stats: dict, spot_check: dict) -> None:
        voice = await self._repo.get_voice_by_id(block.voice_id)
        if voice is None:
            raise RuntimeError(f"Voice {block.voice_id} not found")

        # 1. ElevenLabs TTS
        audio_bytes = await self._tts.synthesize_batch(
            text=block.text_script,
            voice_id=voice.elevenlabs_voice_id,
        )

        # 2. FFmpeg post-processing (with fallback)
        if self._ffmpeg_available:
            try:
                audio_bytes = await self._ffmpeg_postprocess(audio_bytes)
            except Exception as exc:
                logger.warning("FFmpeg post-processing failed for block %s: %s", block.id, exc)
                # Use raw bytes rather than failing the whole block
        else:
            logger.debug("FFmpeg unavailable — skipping post-processing for block %s", block.id)

        # 3. S3 upload
        key = self._s3.build_content_audio_key(
            zone_id=str(block.zone_id),
            point_id=str(block.point_id),
            voice_id=str(block.voice_id),
            language=block.language,
            content_type=block.content_type,
            variant_index=block.variant_index,
            detail_level=block.detail_level,
        )
        cdn_url = await self._s3.upload_audio(key, audio_bytes)

        # 4. Duration
        duration_s = await self._get_audio_duration(audio_bytes)

        # 5. QA checks (log warnings, don't fail)
        warnings = await self._qa_audio(block, audio_bytes, duration_s)
        if warnings:
            logger.warning("Block %s audio QA warnings: %s", block.id, "; ".join(warnings))

        # 6. DB update
        await self._repo.update_block_audio(block.id, cdn_url, duration_s, status="synthesized")

        stats["synthesized"] += 1
        stats["total_duration_s"] += duration_s

        # Spot-check: keep one URL per content_type
        if block.content_type not in spot_check:
            spot_check[block.content_type] = cdn_url

    # -------------------------------------------------------------------------
    # FFmpeg post-processing
    # -------------------------------------------------------------------------

    def _check_ffmpeg(self) -> bool:
        found = shutil.which("ffmpeg") is not None
        if not found:
            logger.warning(
                "ffmpeg not found in PATH — audio post-processing will be skipped. "
                "Install ffmpeg to enable loudnorm + silence padding + fade-out."
            )
        return found

    async def _ffmpeg_postprocess(self, audio_bytes: bytes) -> bytes:
        """
        Apply loudnorm (-16 LUFS), 400ms silence padding, 150ms fade-out.
        Raises RuntimeError if ffmpeg returns non-zero.
        """
        af_chain = (
            "loudnorm=I=-16:TP=-1.5:LRA=11,"
            "apad=pad_dur=400ms,"
            "afade=type=out:duration=0.15"
        )
        cmd = [
            "ffmpeg", "-i", "pipe:0",
            "-af", af_chain,
            "-c:a", "libmp3lame", "-b:a", "128k",
            "-f", "mp3", "pipe:1",
            "-loglevel", "error",
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asubprocess.PIPE,
            stdout=asubprocess.PIPE,
            stderr=asubprocess.PIPE,
        )
        stdout, stderr = await proc.communicate(input=audio_bytes)
        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg error: {stderr.decode()[:500]}")
        if not stdout:
            raise RuntimeError("FFmpeg returned empty output")
        return stdout

    # -------------------------------------------------------------------------
    # Audio duration detection
    # -------------------------------------------------------------------------

    async def _get_audio_duration(self, audio_bytes: bytes) -> float:
        """
        Determine MP3 duration.
        1. Try mutagen (fast, no subprocess).
        2. Fall back to word-count heuristic (~140 wpm).
        """
        try:
            return _duration_via_mutagen(audio_bytes)
        except Exception:
            pass

        # Fallback via ffprobe if available
        if shutil.which("ffprobe"):
            try:
                return await _duration_via_ffprobe(audio_bytes)
            except Exception:
                pass

        # Last resort: heuristic (caller supplies text length indirectly via bytes)
        # ~128 kbps MP3: 16 kB/s → duration_s ≈ len(bytes) / 16000
        return round(len(audio_bytes) / 16_000, 1)

    # -------------------------------------------------------------------------
    # Audio QA
    # -------------------------------------------------------------------------

    async def _qa_audio(self, block, audio_bytes: bytes, duration_s: float) -> list[str]:
        """
        Automated checks:
        - Duration within expected range for content_type
        - No leading silence > 0.5s (TTS artifact)
        Returns list of warning strings (empty = OK).
        """
        warnings: list[str] = []
        min_s, max_s = EXPECTED_DURATION.get(block.content_type, (1.0, 120.0))
        if duration_s < min_s:
            warnings.append(f"Duration {duration_s:.1f}s < min {min_s}s for {block.content_type}")
        if duration_s > max_s:
            warnings.append(f"Duration {duration_s:.1f}s > max {max_s}s for {block.content_type}")

        # Leading silence detection (best-effort via ffmpeg)
        if self._ffmpeg_available and len(audio_bytes) > 0:
            silence_s = await _detect_leading_silence(audio_bytes)
            if silence_s is not None and silence_s > 0.5:
                warnings.append(f"Leading silence {silence_s:.2f}s detected (TTS artifact?)")

        return warnings


# -------------------------------------------------------------------------
# Duration helpers (module-level, no instance state)
# -------------------------------------------------------------------------

def _duration_via_mutagen(audio_bytes: bytes) -> float:
    """Use mutagen to read MP3 duration from bytes via an in-memory buffer."""
    import io
    from mutagen.mp3 import MP3
    buf = io.BytesIO(audio_bytes)
    audio = MP3(buf)
    return round(float(audio.info.length), 2)


async def _duration_via_ffprobe(audio_bytes: bytes) -> float:
    """Use ffprobe to extract duration from piped MP3 bytes."""
    cmd = [
        "ffprobe", "-i", "pipe:0",
        "-show_entries", "format=duration",
        "-v", "quiet", "-of", "csv=p=0",
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asubprocess.PIPE,
        stdout=asubprocess.PIPE,
        stderr=asubprocess.DEVNULL,
    )
    stdout, _ = await proc.communicate(input=audio_bytes)
    return float(stdout.decode().strip())


async def _detect_leading_silence(audio_bytes: bytes, threshold_db: float = -40.0) -> Optional[float]:
    """
    Detect leading silence duration using ffmpeg silencedetect filter.
    Returns seconds of leading silence, or None on error.
    """
    cmd = [
        "ffmpeg", "-i", "pipe:0",
        "-af", f"silencedetect=noise={threshold_db}dB:d=0.1",
        "-f", "null", "-",
        "-loglevel", "info",
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asubprocess.PIPE,
        stdout=asubprocess.DEVNULL,
        stderr=asubprocess.PIPE,
    )
    _, stderr = await proc.communicate(input=audio_bytes)
    stderr_text = stderr.decode()

    # Parse "silence_end: X.XX" from ffmpeg output
    import re
    match = re.search(r"silence_end: (\d+\.\d+)", stderr_text)
    if match:
        return float(match.group(1))
    return None
