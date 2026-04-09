"""
ReviewAnalyzer — Phase 4 component.

Analyzes hotel reviews using LLM in batches of 5 hotels per call.
5 batches × 5 hotels = 25 hotels analyzed; ~80% cheaper than 25 individual calls.
All batches run in parallel via asyncio.gather.

Batch input:  list of {hotel_id, reviews[{pros, cons, author_type}], review_scores}
Batch output: dict[hotel_id → ReviewAnalysis]

Fallback on LLM timeout/error: keyword extraction from raw pros/cons.
"""
from __future__ import annotations

import asyncio
import collections
import logging
import time
from typing import Any

from src.hotels.domain.schemas import HotelRawData, ReviewAnalysis
from src.infrastructure.llm_client import get_hotel_review_llm_client

logger = logging.getLogger(__name__)

_BATCH_SIZE = 5
_BATCH_TIMEOUT = 15.0

_SYSTEM_PROMPT = """\
You are an expert hotel review analyst. Analyze hotel reviews and return structured JSON.
Focus on patterns across multiple reviews, not individual opinions.
Return ONLY valid JSON — no markdown, no explanation.\
"""


def _build_batch_prompt(hotels: list[HotelRawData], user_segment: str) -> str:
    hotels_json: list[dict[str, Any]] = []
    for h in hotels:
        reviews_summary = [
            {
                "pros": r.pros[:200] if r.pros else "",
                "cons": r.cons[:200] if r.cons else "",
                "author_type": r.author_type,
                "score": r.average_score,
            }
            for r in h.reviews[:20]  # max 20 reviews per hotel
        ]
        hotels_json.append({
            "hotel_id": h.hotel_id,
            "name": h.name,
            "review_score": h.review_score,
            "review_count": h.review_count,
            "reviews": reviews_summary,
            "scores_by_segment": h.review_scores.by_segment,
        })

    import json
    hotels_str = json.dumps(hotels_json, ensure_ascii=False, indent=2)

    return f"""\
Analyze the reviews for these {len(hotels)} hotels for a {user_segment} traveler.

Hotels data:
{hotels_str}

For each hotel, return a ReviewAnalysis object. Focus on:
- Recurring themes across multiple reviews (not one-off opinions)
- Issues mentioned in 20%+ of reviews → hidden_issues
- Whether the hotel is particularly good/bad for {user_segment} travelers
- Quality trend (improving/declining/stable) based on score distribution

Return JSON with this exact structure:
{{
  "results": {{
    "<hotel_id_as_string>": {{
      "top_pros": ["<pro1>", "<pro2>", "<pro3>"],
      "top_cons": ["<con1>", "<con2>"],
      "hidden_issues": ["<issue if 20%+ reviews mention it>"],
      "trend": "quality_improving" | "declining" | "stable",
      "segment_fit": <float 0.0-1.0 for {user_segment}>,
      "segment_highlights": ["<highlight specific to {user_segment}>"]
    }}
  }}
}}

JSON only:\
"""


def _keyword_fallback(hotel: HotelRawData) -> ReviewAnalysis:
    """Simple keyword extraction from pros/cons when LLM is unavailable."""
    word_count: dict[str, int] = collections.Counter()
    cons_count: dict[str, int] = collections.Counter()

    for r in hotel.reviews:
        for word in (r.pros or "").lower().split():
            if len(word) > 4:
                word_count[word] += 1
        for word in (r.cons or "").lower().split():
            if len(word) > 4:
                cons_count[word] += 1

    top_pros = [w for w, _ in word_count.most_common(5)][:3]
    top_cons = [w for w, _ in cons_count.most_common(3)][:2]

    # Segment fit: use by_segment scores if available
    by_seg = hotel.review_scores.by_segment
    segment_score = by_seg.get("couple", by_seg.get("young_couple", 0.0))
    segment_fit = min(segment_score / 10.0, 1.0) if segment_score else 0.5

    return ReviewAnalysis(
        hotel_id=hotel.hotel_id,
        top_pros=top_pros,
        top_cons=top_cons,
        hidden_issues=[],
        trend="stable",
        segment_fit=segment_fit,
        segment_highlights=[],
    )


class ReviewAnalyzer:
    """
    Phase 4: Batch LLM analysis of hotel reviews, segment-focused.

    Splits hotels into batches of 5, runs all batches in parallel.
    Falls back to keyword extraction on LLM timeout or error.
    """

    def __init__(self) -> None:
        try:
            self._llm = get_hotel_review_llm_client()
        except Exception as exc:
            logger.warning("ReviewAnalyzer: LLM unavailable at init (%s), will retry per-request", exc)
            self._llm = None

    def _ensure_llm(self) -> None:
        """Lazy-retry LLM client creation if it failed at init time."""
        if self._llm is None:
            try:
                self._llm = get_hotel_review_llm_client()
                logger.info("ReviewAnalyzer: LLM client recovered on retry")
            except Exception:
                pass

    async def analyze_batch(
        self,
        hotels: list[HotelRawData],
        user_segment: str,
    ) -> dict[int, ReviewAnalysis]:
        """
        Analyze reviews for all hotels in parallel batches of 5.

        Args:
            hotels: List of HotelRawData with reviews populated.
            user_segment: Traveler type for segment-focused analysis.

        Returns:
            Dict mapping hotel_id → ReviewAnalysis.
        """
        if not hotels:
            return {}

        self._ensure_llm()
        t0 = time.monotonic()

        # Split into batches of BATCH_SIZE
        batches = [hotels[i:i + _BATCH_SIZE] for i in range(0, len(hotels), _BATCH_SIZE)]

        batch_tasks = [
            self._analyze_one_batch(batch, user_segment)
            for batch in batches
        ]

        batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)

        # Merge all batch results
        merged: dict[int, ReviewAnalysis] = {}
        for i, result in enumerate(batch_results):
            if isinstance(result, Exception):
                logger.warning(
                    "ReviewAnalyzer: batch %d failed (%s), applying keyword fallback",
                    i, result,
                )
                for h in batches[i]:
                    merged[h.hotel_id] = _keyword_fallback(h)
            elif isinstance(result, dict):
                merged.update(result)

        # Ensure every hotel has an entry (fallback for missing)
        for h in hotels:
            if h.hotel_id not in merged:
                merged[h.hotel_id] = _keyword_fallback(h)

        elapsed = time.monotonic() - t0
        logger.info(
            "ReviewAnalyzer: %d hotels in %d batches analyzed in %.1fs",
            len(merged), len(batches), elapsed,
        )
        return merged

    async def _analyze_one_batch(
        self,
        hotels: list[HotelRawData],
        user_segment: str,
    ) -> dict[int, ReviewAnalysis]:
        """Run LLM analysis for one batch; fall back to keywords on error."""
        if not self._llm:
            return {h.hotel_id: _keyword_fallback(h) for h in hotels}

        try:
            prompt = _build_batch_prompt(hotels, user_segment)
            raw = await asyncio.wait_for(
                self._llm.generate_structured(prompt, _SYSTEM_PROMPT, max_tokens=2048),
                timeout=_BATCH_TIMEOUT,
            )
            return self._parse_batch_response(raw, hotels)

        except asyncio.TimeoutError:
            logger.warning(
                "ReviewAnalyzer: batch timeout (%.1fs), keyword fallback for %d hotels",
                _BATCH_TIMEOUT, len(hotels),
            )
            return {h.hotel_id: _keyword_fallback(h) for h in hotels}
        except Exception as exc:
            logger.warning("ReviewAnalyzer: batch error (%s), keyword fallback", exc)
            return {h.hotel_id: _keyword_fallback(h) for h in hotels}

    def _parse_batch_response(
        self,
        raw: dict,
        hotels: list[HotelRawData],
    ) -> dict[int, ReviewAnalysis]:
        """Convert LLM JSON response into ReviewAnalysis objects."""
        results_raw: dict = raw.get("results", raw)  # handle both formats
        hotel_map = {h.hotel_id: h for h in hotels}
        output: dict[int, ReviewAnalysis] = {}

        for key, val in results_raw.items():
            try:
                hotel_id = int(key)
            except (ValueError, TypeError):
                continue

            if not isinstance(val, dict):
                continue

            hotel = hotel_map.get(hotel_id)
            if not hotel:
                continue

            try:
                segment_fit = float(val.get("segment_fit", 0.5))
                segment_fit = max(0.0, min(1.0, segment_fit))
            except (TypeError, ValueError):
                segment_fit = 0.5

            output[hotel_id] = ReviewAnalysis(
                hotel_id=hotel_id,
                top_pros=val.get("top_pros", []) if isinstance(val.get("top_pros"), list) else [],
                top_cons=val.get("top_cons", []) if isinstance(val.get("top_cons"), list) else [],
                hidden_issues=val.get("hidden_issues", []) if isinstance(val.get("hidden_issues"), list) else [],
                trend=val.get("trend", "stable"),
                segment_fit=segment_fit,
                segment_highlights=val.get("segment_highlights", []) if isinstance(val.get("segment_highlights"), list) else [],
            )

        # Fallback for any hotel missing from LLM response
        for h in hotels:
            if h.hotel_id not in output:
                logger.warning("ReviewAnalyzer: hotel %d missing from LLM response, using fallback", h.hotel_id)
                output[h.hotel_id] = _keyword_fallback(h)

        return output
