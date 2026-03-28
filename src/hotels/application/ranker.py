"""
MasterRanker — Phase 5 component.

Two modes:

PRIMARY (LLM-driven):
  Single LLM call with all HotelProfile + ParsedIntent (including scoring_weights).
  scoring_weights serve as "priority guidance" — LLM may deviate for context
  that weights cannot capture (e.g. "3 reviews mention ongoing renovation").
  Outputs: ranked_top10, filtered_out reasons, notable_excluded.
  Timeout: 20s.

FALLBACK (deterministic formula):
  ai_score = Σ(w_i × score_i) × penalty_factor
  score_i components (all normalised to [0,1]):
    - semantic_match: keyword overlap of semantic_criteria vs hotel name/highlights
    - segment_fit: ReviewAnalysis.segment_fit
    - facility_match: fraction of must_have present in hotel facilities
    - review_quality: review_score/10 minus hidden_issue penalty
    - price_value: closeness of price_per_night to budget
    - location: 1 − min(distance_to_cc / 5km, 1)
  penalty_factor: 0.5 if any dealbreaker found in cons/hidden_issues, else 1.0.
  Does not generate ai_match_reason or notable_excluded.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from src.hotels.domain.schemas import (
    ExcludedHotel,
    HotelProfile,
    HotelRanked,
    MasterRankingResult,
    ParsedIntent,
)
from src.infrastructure.llm_client import get_hotel_ranking_llm_client

logger = logging.getLogger(__name__)

_RANK_TIMEOUT = 40.0

_SYSTEM_PROMPT = """\
You are a world-class hotel recommendation expert. Rank hotels based on user preferences.
Consider all data carefully. The scoring_weights show priority — treat them as guidance,
not a rigid formula. Account for nuances the weights cannot capture.
Return ONLY valid JSON — no markdown, no explanation.\
"""

_SEGMENT_SCORE_KEYS: dict[str, list[str]] = {
    "couple": ["young_couple", "couple"],
    "family": ["family_with_young_children", "family"],
    "business": ["review_category_business_travellers", "business"],
    "solo": ["solo_traveller", "solo"],
    "group": ["group"],
}


def _hotel_profile_summary(profile: HotelProfile) -> dict[str, Any]:
    """Condense HotelProfile to a compact dict for the LLM prompt."""
    raw = profile.raw
    ra = profile.review_analysis

    return {
        "hotel_id": raw.hotel_id,
        "name": raw.name,
        "stars": raw.stars,
        "address": raw.address,
        "distance_to_center_km": raw.distance_to_cc,
        "review_score": raw.review_score,
        "review_count": raw.review_count,
        "price_per_night": raw.price_per_night,
        "currency": raw.currency,
        "breakfast_included": raw.breakfast_included,
        "free_cancellation": raw.free_cancellation,
        "accommodation_type": raw.accommodation_type,
        "is_chain": raw.chaincode is not None,
        "key_facilities": [f.title for f in raw.facilities[:15]],
        "top_pros": ra.top_pros,
        "top_cons": ra.top_cons,
        "hidden_issues": ra.hidden_issues,
        "trend": ra.trend,
        "segment_fit_score": ra.segment_fit,
        "segment_highlights": ra.segment_highlights,
    }


def _build_rank_prompt(hotels: list[HotelProfile], intent: ParsedIntent) -> str:
    profiles = [_hotel_profile_summary(h) for h in hotels]
    profiles_str = json.dumps(profiles, ensure_ascii=False, indent=2)

    weights = intent.scoring_weights.model_dump()

    return f"""\
Rank these {len(hotels)} hotels for a user with the following preferences:

User segment: {intent.user_segment}
Must-have requirements: {intent.must_have}
Dealbreakers: {intent.dealbreakers}
Semantic criteria: {intent.semantic_criteria}
Budget max: {intent.price_max} {{}}/night
Min review score: {intent.min_review_score}
Boutique preferred: {intent.is_boutique_preferred}
Remote work: {intent.is_remote_work}
Prefers free cancellation: {intent.prefers_free_cancellation} (give bonus to hotels with free_cancellation=true)

Scoring weights (priority guidance):
{json.dumps(weights, indent=2)}

Hotels to rank:
{profiles_str}

Tasks:
1. Select and rank the TOP 10 hotels.
2. For each top-10 hotel: provide ai_score (0-10), ai_match_reason (1-2 sentences, personal, specific), why_this_hotel (3 bullet points).
   IMPORTANT for ai_match_reason: Each hotel MUST have a UNIQUE reason. Do NOT repeat generic phrases like "excellent location and comfortable rooms". Highlight what specifically distinguishes THIS hotel — its neighborhood, a standout amenity, design style, unusual value, specific guest praise, or anything memorable that sets it apart from the others in this list.
3. For remaining hotels: brief filtered_out reason (10-15 words).
4. Identify 3-5 "notable_excluded" hotels that nearly made the top-10.

Return this exact JSON structure:
{{
  "ranked_top10": [
    {{
      "hotel_id": <int>,
      "ai_score": <float 0-10>,
      "ai_match_reason": "<personalized explanation>",
      "why_this_hotel": ["<reason1>", "<reason2>", "<reason3>"]
    }}
  ],
  "filtered_out": {{
    "<hotel_id_str>": "<short reason why not in top 10>"
  }},
  "notable_excluded": [
    {{
      "hotel_id": <int>,
      "name": "<name>",
      "stars": <int>,
      "review_score": <float>,
      "price_per_night": <float>,
      "ai_score": <float>,
      "reason": "<why it almost made it>"
    }}
  ]
}}

JSON only:\
"""


class MasterRanker:
    """
    Phase 5: LLM-driven hotel ranker with deterministic formula fallback.
    """

    def __init__(self) -> None:
        try:
            self._llm = get_hotel_ranking_llm_client()
        except Exception as exc:
            logger.warning("MasterRanker: LLM unavailable (%s), formula fallback only", exc)
            self._llm = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def rank(
        self,
        hotels: list[HotelProfile],
        intent: ParsedIntent,
    ) -> MasterRankingResult:
        """
        Rank hotels using LLM-driven analysis.
        Falls back to deterministic formula on timeout or error.
        """
        if not hotels:
            return MasterRankingResult(ranked_top10=[])

        if not self._llm:
            logger.info("MasterRanker: using formula fallback (no LLM)")
            return self.rank_fallback(hotels, intent)

        t0 = time.monotonic()
        try:
            prompt = _build_rank_prompt(hotels, intent)
            raw = await asyncio.wait_for(
                self._llm.generate_structured(prompt, _SYSTEM_PROMPT, max_tokens=4096),
                timeout=_RANK_TIMEOUT,
            )
            result = self._parse_rank_response(raw, hotels)
            logger.info(
                "MasterRanker: LLM ranked %d hotels → top10 in %.1fs",
                len(hotels), time.monotonic() - t0,
            )
            return result

        except asyncio.TimeoutError:
            logger.warning(
                "MasterRanker: LLM timeout after %.1fs (limit=%.1fs), using formula fallback",
                time.monotonic() - t0, _RANK_TIMEOUT,
            )
            return self.rank_fallback(hotels, intent)
        except Exception as exc:
            logger.warning(
                "MasterRanker: LLM error [%s] after %.1fs: %s — using formula fallback",
                type(exc).__name__, time.monotonic() - t0, exc,
            )
            return self.rank_fallback(hotels, intent)

    def rank_fallback(
        self,
        hotels: list[HotelProfile],
        intent: ParsedIntent,
    ) -> MasterRankingResult:
        """
        Deterministic formula ranking.
        ai_score = Σ(w_i × score_i) × penalty_factor
        """
        scored: list[tuple[float, HotelProfile]] = []

        for profile in hotels:
            score = self._compute_formula_score(profile, intent)
            scored.append((score, profile))

        scored.sort(key=lambda x: x[0], reverse=True)
        top10 = scored[:10]

        ranked = [
            HotelRanked(
                hotel_id=p.hotel_id,
                ai_score=round(s * 10, 1),
                ai_match_reason=f"Score: {round(s * 10, 1)}/10 (formula ranking)",
                why_this_hotel=[
                    f"Review score: {p.raw.review_score}",
                    f"Price: {p.raw.price_per_night:.0f} {p.raw.currency}/night",
                    f"Distance to center: {p.raw.distance_to_cc:.1f}km",
                ],
            )
            for s, p in top10
        ]

        filtered_out = {
            str(p.hotel_id): f"Score {round(s * 10, 1)}/10 — below top 10"
            for s, p in scored[10:]
        }

        return MasterRankingResult(
            ranked_top10=ranked,
            filtered_out=filtered_out,
            notable_excluded=[],  # formula doesn't identify near-misses
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_rank_response(
        self,
        raw: dict,
        hotels: list[HotelProfile],
    ) -> MasterRankingResult:
        """Parse LLM JSON response into MasterRankingResult."""
        hotel_map = {h.hotel_id: h for h in hotels}

        # ranked_top10 (deduplicated — LLM occasionally returns same hotel twice)
        ranked_top10: list[HotelRanked] = []
        seen_ids: set[int] = set()
        for item in raw.get("ranked_top10", []):
            if not isinstance(item, dict):
                continue
            try:
                hid = int(item["hotel_id"])
                if hid in seen_ids:
                    continue
                seen_ids.add(hid)
                ranked_top10.append(HotelRanked(
                    hotel_id=hid,
                    ai_score=float(item.get("ai_score", 5.0)),
                    ai_match_reason=str(item.get("ai_match_reason", "")),
                    why_this_hotel=item.get("why_this_hotel", []) if isinstance(item.get("why_this_hotel"), list) else [],
                ))
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning("MasterRanker: skipping malformed ranked item: %s", exc)

        # filtered_out
        filtered_out: dict[str, str] = {}
        for k, v in raw.get("filtered_out", {}).items():
            filtered_out[str(k)] = str(v)

        # notable_excluded
        notable_excluded: list[ExcludedHotel] = []
        for item in raw.get("notable_excluded", []):
            if not isinstance(item, dict):
                continue
            try:
                notable_excluded.append(ExcludedHotel(
                    hotel_id=int(item["hotel_id"]),
                    name=str(item.get("name", "")),
                    stars=int(item.get("stars", 0)),
                    review_score=float(item.get("review_score", 0.0)),
                    price_per_night=float(item.get("price_per_night", 0.0)),
                    ai_score=float(item.get("ai_score", 0.0)),
                    reason=str(item.get("reason", "")),
                ))
            except (KeyError, TypeError, ValueError):
                continue

        # If LLM returned fewer than 10, fill with formula fallback
        if len(ranked_top10) < min(10, len(hotels)):
            ranked_ids = {r.hotel_id for r in ranked_top10}
            missing = [h for h in hotels if h.hotel_id not in ranked_ids]
            fallback = self.rank_fallback(missing, ParsedIntent())
            ranked_top10.extend(fallback.ranked_top10[:10 - len(ranked_top10)])

        # Ensure final list is sorted by ai_score descending (LLM may not guarantee it)
        ranked_top10.sort(key=lambda r: r.ai_score, reverse=True)

        return MasterRankingResult(
            ranked_top10=ranked_top10[:10],
            filtered_out=filtered_out,
            notable_excluded=notable_excluded,
        )

    def _compute_formula_score(
        self,
        profile: HotelProfile,
        intent: ParsedIntent,
    ) -> float:
        """Compute normalised [0,1] score using dynamic weights."""
        raw = profile.raw
        ra = profile.review_analysis
        w = intent.scoring_weights

        # semantic_match: keyword overlap
        semantic_score = self._semantic_match(raw, intent)

        # segment_fit: from review analysis
        segment_score = ra.segment_fit  # already 0–1

        # facility_match: must_have coverage
        facility_score = self._facility_match(raw, intent)

        # review_quality: normalised score minus hidden issue penalty
        review_score_norm = min(raw.review_score / 10.0, 1.0) if raw.review_score else 0.5
        hidden_penalty = min(len(ra.hidden_issues) * 0.1, 0.3)
        review_quality = max(0.0, review_score_norm - hidden_penalty)

        # price_value: closeness to budget (1.0 = exactly at budget or free)
        price_value = self._price_value(raw.price_per_night, intent)

        # location: proximity to center (5km scale)
        location_score = max(0.0, 1.0 - min(raw.distance_to_cc / 5.0, 1.0))

        base_score = (
            w.semantic_match * semantic_score
            + w.segment_fit * segment_score
            + w.facility_match * facility_score
            + w.review_quality * review_quality
            + w.price_value * price_value
            + w.location * location_score
        )

        # Bonus: free cancellation preference
        cancellation_bonus = 0.05 if (intent.prefers_free_cancellation and raw.free_cancellation) else 0.0

        # Penalty: dealbreaker found in cons or hidden issues
        penalty = self._dealbreaker_penalty(ra, intent)

        return (base_score + cancellation_bonus) * penalty

    def _semantic_match(self, raw: Any, intent: ParsedIntent) -> float:
        """Simple keyword overlap between semantic_criteria and hotel data."""
        if not intent.semantic_criteria:
            return 0.5  # neutral if no criteria

        # Build text from hotel name + highlights + facility titles
        hotel_text = " ".join([
            raw.name or "",
            raw.accommodation_type or "",
            *raw.property_highlights,
            *raw.top_benefits,
            *[f.title for f in raw.facilities[:10]],
        ]).lower()

        all_keywords = [
            kw.lower()
            for keywords in intent.semantic_criteria.values()
            for kw in keywords
        ]
        if not all_keywords:
            return 0.5

        matches = sum(1 for kw in all_keywords if kw in hotel_text)
        return min(matches / len(all_keywords), 1.0)

    def _facility_match(self, raw: Any, intent: ParsedIntent) -> float:
        """Fraction of must_have facilities present in hotel."""
        if not intent.must_have:
            return 0.7  # no requirements → decent default

        facility_titles = {f.title.lower() for f in raw.facilities}
        matches = sum(
            1 for mh in intent.must_have
            if any(mh.lower() in ft for ft in facility_titles)
        )
        return matches / len(intent.must_have)

    def _price_value(self, price_per_night: float, intent: ParsedIntent) -> float:
        """Price value score: 1.0 at budget, 0.0 at 2× budget."""
        if not price_per_night or not intent.price_max:
            return 0.7  # no price data → neutral

        if price_per_night <= intent.price_max:
            return 1.0
        return max(0.0, 1.0 - (price_per_night - intent.price_max) / intent.price_max)

    def _dealbreaker_penalty(self, ra: Any, intent: ParsedIntent) -> float:
        """0.5 if a dealbreaker is mentioned in cons/hidden_issues, else 1.0."""
        if not intent.dealbreakers:
            return 1.0

        issue_text = " ".join(ra.top_cons + ra.hidden_issues).lower()
        for db in intent.dealbreakers:
            if db.lower() in issue_text:
                return 0.5
        return 1.0
