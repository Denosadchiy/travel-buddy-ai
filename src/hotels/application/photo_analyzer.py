"""
PhotoAnalyzer — Phase 6 component (optional, vision-based).

Analyzes hotel photos to extract visual attributes:
  - interior_style: modern | classic | boutique | rustic | mixed
  - cleanliness_visual: excellent | good | average | poor
  - view_quality: sea | city | garden | parking | none | mixed
  - room_size_estimate: spacious | standard | compact
  - style_tags: ["minimalist", "luxury", "cozy", ...]
  - photo_match_score: 0–1 semantic criteria match

Enabled ONLY when HOTEL_VISION_MODEL is configured (non-empty).
Otherwise silently returns {} — this is NOT an error.

Photo selection: up to 5 representative photos from 40+ available,
chosen by URL keyword matching: lobby, room, pool, exterior, view.
"""
from __future__ import annotations

import asyncio
import json
import logging

from src.config import settings
from src.hotels.domain.schemas import ParsedIntent, PhotoAnalysis
from src.hotels.infrastructure.booking_client import BookingClient

logger = logging.getLogger(__name__)

_PHOTO_TIMEOUT = 8.0    # seconds per hotel (vision call)
_FETCH_TIMEOUT = 4.0    # seconds for photo list fetch
_MAX_PHOTOS = 5

_VISION_SYSTEM = """\
You are a hotel visual analyst. Analyze hotel photos and return structured JSON.
Return ONLY valid JSON — no markdown, no explanation."""

# URL-keyword mapping to pick representative photos
_CATEGORY_KEYWORDS = {
    "lobby":    ["lobby", "reception", "entrance", "hall", "foyer"],
    "room":     ["room", "bedroom", "suite", "bed", "interior"],
    "pool":     ["pool", "spa", "jacuzzi", "wellness", "sauna"],
    "exterior": ["exterior", "facade", "building", "outside", "front"],
    "view":     ["view", "balcony", "terrace", "sea", "panoram"],
}


def _select_photos(photos: list[dict]) -> list[str]:
    """
    Pick up to 5 representative photo URLs from a raw photo list.
    Prefers url_square1024, then url_max500, then url_max300.
    Tries to cover lobby / room / pool / exterior / view categories.
    Falls back to first 5 if URL keywords don't match.
    """
    url_pairs: list[tuple[str, int]] = []
    for i, p in enumerate(photos):
        url = (
            p.get("url_square1024")
            or p.get("url_max500")
            or p.get("url_max300")
            or p.get("url_original", "")
        )
        if url:
            url_pairs.append((url, i))

    if not url_pairs:
        return []

    selected: list[str] = []
    used: set[int] = set()

    # One photo per category
    for keywords in _CATEGORY_KEYWORDS.values():
        for url, idx in url_pairs:
            if idx in used:
                continue
            if any(kw in url.lower() for kw in keywords):
                selected.append(url)
                used.add(idx)
                break

    # Fill remaining slots
    for url, idx in url_pairs:
        if len(selected) >= _MAX_PHOTOS:
            break
        if idx not in used:
            selected.append(url)
            used.add(idx)

    return selected[:_MAX_PHOTOS]


def _parse_vision_response(text: str) -> PhotoAnalysis:
    """Parse JSON from LLM vision response."""
    if "```json" in text:
        text = text[text.find("```json") + 7:text.rfind("```")]
    elif "```" in text:
        text = text[text.find("```") + 3:text.rfind("```")]
    raw = json.loads(text.strip())
    return PhotoAnalysis(
        interior_style=str(raw.get("interior_style", "mixed")),
        cleanliness_visual=str(raw.get("cleanliness_visual", "average")),
        view_quality=str(raw.get("view_quality", "none")),
        room_size_estimate=str(raw.get("room_size_estimate", "standard")),
        style_tags=raw.get("style_tags", []) if isinstance(raw.get("style_tags"), list) else [],
        photo_match_score=float(raw.get("photo_match_score", 0.5)),
    )


def _build_vision_prompt(photo_urls: list[str], intent: ParsedIntent) -> str:
    semantic_str = str(intent.semantic_criteria) if intent.semantic_criteria else "none specified"
    urls_str = "\n".join(f"  {i + 1}. {u}" for i, u in enumerate(photo_urls))
    return f"""\
Analyze these {len(photo_urls)} hotel photos:
{urls_str}

Semantic criteria to match: {semantic_str}

Return this exact JSON:
{{
  "interior_style": "modern" | "classic" | "boutique" | "rustic" | "mixed",
  "cleanliness_visual": "excellent" | "good" | "average" | "poor",
  "view_quality": "sea" | "city" | "garden" | "parking" | "none" | "mixed",
  "room_size_estimate": "spacious" | "standard" | "compact",
  "style_tags": ["<tag1>", "<tag2>", "<tag3>"],
  "photo_match_score": <float 0.0-1.0>
}}

JSON only:"""


class PhotoAnalyzer:
    """
    Phase 6: Optional vision analysis of hotel photos (top 5 from final ranking).

    Only active when HOTEL_VISION_MODEL is set.
    All errors/timeouts silently return {} — vision is always optional.
    """

    def __init__(self) -> None:
        self._vision_model = settings.hotel_vision_model
        self._enabled = bool(self._vision_model)
        if not self._enabled:
            logger.info("PhotoAnalyzer: HOTEL_VISION_MODEL not configured — Phase 6 disabled")

    async def analyze_top_hotels(
        self,
        hotel_ids: list[int],
        booking_client: BookingClient,
        intent: ParsedIntent,
    ) -> dict[int, PhotoAnalysis]:
        """
        Fetch and vision-analyze photos for the given hotel IDs (≤5).

        Returns dict of hotel_id → PhotoAnalysis.
        Returns empty dict if vision is disabled or all analyses fail.
        """
        if not self._enabled:
            return {}

        target_ids = hotel_ids[:_MAX_PHOTOS]
        tasks = [
            self._analyze_one(hid, booking_client, intent)
            for hid in target_ids
        ]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        results: dict[int, PhotoAnalysis] = {}
        for hid, res in zip(target_ids, raw_results):
            if isinstance(res, Exception):
                logger.debug("PhotoAnalyzer: hotel %d failed: %s", hid, res)
            elif isinstance(res, PhotoAnalysis):
                results[hid] = res

        logger.info("PhotoAnalyzer: %d/%d hotels vision-analyzed", len(results), len(target_ids))
        return results

    async def _analyze_one(
        self,
        hotel_id: int,
        booking_client: BookingClient,
        intent: ParsedIntent,
    ) -> PhotoAnalysis | None:
        """Fetch + analyze one hotel's photos. Returns None on any failure."""
        try:
            photos = await asyncio.wait_for(
                booking_client.get_hotel_photos(hotel_id),
                timeout=_FETCH_TIMEOUT,
            )
            if not photos:
                return None

            urls = _select_photos(photos)
            if not urls:
                return None

            return await asyncio.wait_for(
                self._call_vision(urls, intent),
                timeout=_PHOTO_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.debug("PhotoAnalyzer: hotel %d timed out", hotel_id)
            return None
        except Exception as exc:
            logger.debug("PhotoAnalyzer: hotel %d error: %s", hotel_id, exc)
            return None

    async def _call_vision(
        self,
        photo_urls: list[str],
        intent: ParsedIntent,
    ) -> PhotoAnalysis:
        """Dispatch to Anthropic vision or text-based fallback."""
        if settings.llm_provider == "anthropic":
            return await self._anthropic_vision(photo_urls, intent)
        return await self._text_vision(photo_urls, intent)

    async def _anthropic_vision(
        self,
        photo_urls: list[str],
        intent: ParsedIntent,
    ) -> PhotoAnalysis:
        """Use Anthropic messages API with image_url content blocks."""
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        content: list[dict] = []
        for url in photo_urls:
            content.append({"type": "image", "source": {"type": "url", "url": url}})
        content.append({"type": "text", "text": _build_vision_prompt(photo_urls, intent)})

        response = await client.messages.create(
            model=self._vision_model,
            max_tokens=512,
            system=_VISION_SYSTEM,
            messages=[{"role": "user", "content": content}],
        )
        return _parse_vision_response(response.content[0].text)

    async def _text_vision(
        self,
        photo_urls: list[str],
        intent: ParsedIntent,
    ) -> PhotoAnalysis:
        """
        Text-based fallback for non-vision providers.
        Asks LLM to infer visual properties from URL keywords.
        """
        from src.infrastructure.llm_client import get_llm_client

        llm = get_llm_client(model=self._vision_model)
        prompt = (
            "Based on these hotel photo URLs, infer visual characteristics "
            "from the filenames and URL tags:\n"
            + "\n".join(f"  - {u}" for u in photo_urls)
            + "\n\n"
            + _build_vision_prompt(photo_urls, intent)
        )
        raw = await llm.generate_structured(prompt, _VISION_SYSTEM, max_tokens=512)
        return PhotoAnalysis(
            interior_style=str(raw.get("interior_style", "mixed")),
            cleanliness_visual=str(raw.get("cleanliness_visual", "average")),
            view_quality=str(raw.get("view_quality", "none")),
            room_size_estimate=str(raw.get("room_size_estimate", "standard")),
            style_tags=raw.get("style_tags", []) if isinstance(raw.get("style_tags"), list) else [],
            photo_match_score=float(raw.get("photo_match_score", 0.5)),
        )
