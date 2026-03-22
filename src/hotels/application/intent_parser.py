"""
IntentParser — Phase 1 component.

Converts HotelSearchRequest → ParsedIntent by combining:
  1. Deterministic extraction from structured fields (amenities, budget, children)
  2. LLM semantic analysis of user_wishes → segment, weights, dealbreakers

LLM: HOTEL_INTENT_MODEL → fallback TRIP_CHAT_MODEL.
Timeout: 8s. Fallback: deterministic ParsedIntent with DEFAULT_WEIGHTS.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from src.hotels.domain.schemas import (
    HotelSearchRequest,
    ParsedIntent,
    ScoringWeights,
)
from src.infrastructure.llm_client import get_hotel_intent_llm_client

logger = logging.getLogger(__name__)

_LLM_TIMEOUT = 8.0

_SYSTEM_PROMPT = """\
You are an expert hotel search assistant. Analyze travel requests and extract
structured parameters. Return ONLY valid JSON — no explanation, no markdown.\
"""

_FACILITY_REFERENCE = """\
Available filter codes (use in api_filters):
Facility (facility::N):
  107=Free WiFi, 3=Restaurant, 11=Fitness, 16=Non-smoking, 54=Spa, 433=Pool,
  28=Family rooms, 17=Airport shuttle, 4=Pets allowed, 2=Parking,
  8=24h front desk, 46=Free parking, 5=Room service, 185=Wheelchair, 182=EV charging
Room facility (room_facility::N):
  11=Air conditioning, 23=Desk/workspace, 79=Soundproofing, 81=View,
  34=Washing machine, 75=Flat-screen TV, 5=Bath, 38=Private bathroom
Distance (distance::N): 1000=<1km from center, 3000=<3km, 5000=<5km
Review bucket (reviewscorebuckets::N): 60=OK+, 70=Good+, 80=Very Good+, 90=Superb
Stay type (stay_type::N): 2=Adults only, 4=LGBTQ+ friendly\
"""

_FEW_SHOT = """\
Example 1 — "Romantic boutique hotel in city center, quiet, not a chain":
{
  "api_filters": ["distance::1000", "reviewscorebuckets::80"],
  "price_min": null, "price_max": null,
  "sort_by": "bayesian_review_score", "min_review_score": 8.0,
  "semantic_criteria": {"atmosphere": ["romantic", "intimate"], "style": ["boutique"]},
  "must_have": ["boutique hotel", "quiet location"],
  "dealbreakers": ["chain hotel", "noisy street", "corporate"],
  "user_segment": "couple", "children_ages": [],
  "is_remote_work": false, "is_boutique_preferred": true,
  "implicit_needs": ["good WiFi", "cozy bar"],
  "scoring_weights": {
    "semantic_match": 0.35, "location": 0.25, "review_quality": 0.20,
    "facility_match": 0.10, "price_value": 0.05, "segment_fit": 0.05
  }
}

Example 2 — "Family trip, kids 3 and 7, need pool and playground":
{
  "api_filters": ["facility::433", "facility::28", "reviewscorebuckets::70"],
  "price_min": null, "price_max": null,
  "sort_by": "bayesian_review_score", "min_review_score": 7.0,
  "semantic_criteria": {"amenities": ["pool", "playground"], "atmosphere": ["family-friendly"]},
  "must_have": ["swimming pool", "family rooms"],
  "dealbreakers": ["adults only"],
  "user_segment": "family", "children_ages": [3, 7],
  "is_remote_work": false, "is_boutique_preferred": false,
  "implicit_needs": ["crib available", "high chair"],
  "scoring_weights": {
    "facility_match": 0.30, "segment_fit": 0.25, "review_quality": 0.20,
    "location": 0.15, "semantic_match": 0.05, "price_value": 0.05
  }
}

Example 3 — "Need to work from hotel, fast WiFi, desk, quiet room":
{
  "api_filters": ["facility::107", "room_facility::23", "room_facility::79"],
  "price_min": null, "price_max": null,
  "sort_by": "bayesian_review_score", "min_review_score": 8.0,
  "semantic_criteria": {"environment": ["quiet", "productive"]},
  "must_have": ["fast WiFi", "desk in room", "quiet room"],
  "dealbreakers": ["noisy", "slow WiFi"],
  "user_segment": "business", "children_ages": [],
  "is_remote_work": true, "is_boutique_preferred": false,
  "implicit_needs": ["power outlets", "good lighting"],
  "scoring_weights": {
    "facility_match": 0.30, "review_quality": 0.25, "semantic_match": 0.20,
    "location": 0.10, "price_value": 0.10, "segment_fit": 0.05
  }
}\
"""


def _build_prompt(request: HotelSearchRequest) -> str:
    guests = f"{request.adults} adults"
    if request.children_ages:
        guests += f", children ages {request.children_ages}"

    budget_lines = []
    if request.budget_min and request.budget_max:
        budget_lines.append(f"Budget: {request.budget_min}–{request.budget_max} {request.currency}/night")
    elif request.budget_max:
        budget_lines.append(f"Budget: up to {request.budget_max} {request.currency}/night")

    extras = []
    if request.free_cancellation:
        extras.append("free cancellation required")
    if request.adults_only:
        extras.append("adults only property")
    if request.pets_allowed:
        extras.append("pets allowed required")
    if request.amenities:
        extras.append(f"pre-selected amenities: {request.amenities}")
    if request.stars_min:
        extras.append(f"minimum {request.stars_min} stars")

    context_lines = budget_lines + ([f"Additional: {', '.join(extras)}"] if extras else [])
    context = "\n".join(context_lines)

    return f"""\
Analyze this hotel search request and return JSON matching ParsedIntent.

City: {request.city}
Guests: {guests}
{context}
User's wishes (free text): "{request.user_wishes or ''}"

{_FACILITY_REFERENCE}

{_FEW_SHOT}

Return ONLY a JSON object with ALL of these fields:
- api_filters: list[str] — filter codes from the reference above
- price_min: float | null
- price_max: float | null
- sort_by: "bayesian_review_score" | "price" | "distance" | "popularity"
- min_review_score: float (6.0–10.0)
- semantic_criteria: dict[str, list[str]]
- must_have: list[str]
- dealbreakers: list[str]
- user_segment: "couple" | "family" | "business" | "solo" | "group"
- children_ages: list[int]
- is_remote_work: bool
- is_boutique_preferred: bool
- implicit_needs: list[str]
- scoring_weights: {{"semantic_match": f, "segment_fit": f, "facility_match": f, "review_quality": f, "price_value": f, "location": f}} — must sum to 1.0

JSON only:\
"""


def _safe_list(val: Any, default: list) -> list:
    return val if isinstance(val, list) else default


def _safe_float(val: Any, default: float | None) -> float | None:
    try:
        return float(val) if val is not None else default
    except (TypeError, ValueError):
        return default


def _parse_llm_result(raw: dict, request: HotelSearchRequest) -> ParsedIntent:
    """Convert raw LLM dict → ParsedIntent with safe defaults."""
    try:
        weights_raw = raw.get("scoring_weights", {})
        weights = ScoringWeights(**weights_raw) if isinstance(weights_raw, dict) and weights_raw else ScoringWeights()
    except Exception:
        weights = ScoringWeights()

    return ParsedIntent(
        api_filters=_safe_list(raw.get("api_filters"), []),
        price_min=_safe_float(raw.get("price_min"), request.budget_min),
        price_max=_safe_float(raw.get("price_max"), request.budget_max),
        sort_by=raw.get("sort_by", "bayesian_review_score"),
        min_review_score=_safe_float(raw.get("min_review_score"), 7.0) or 7.0,
        semantic_criteria=(
            raw.get("semantic_criteria")
            if isinstance(raw.get("semantic_criteria"), dict)
            else {}
        ),
        must_have=_safe_list(raw.get("must_have"), []),
        dealbreakers=_safe_list(raw.get("dealbreakers"), []),
        user_segment=raw.get("user_segment", "couple"),
        children_ages=_safe_list(raw.get("children_ages"), list(request.children_ages)),
        is_remote_work=bool(raw.get("is_remote_work", False)),
        is_boutique_preferred=bool(raw.get("is_boutique_preferred", False)),
        implicit_needs=_safe_list(raw.get("implicit_needs"), []),
        scoring_weights=weights,
    )


class IntentParser:
    """
    Phase 1: HotelSearchRequest → ParsedIntent.

    Uses LLM to analyze free-text user_wishes when present.
    Always merges LLM result with deterministic extraction from structured fields.
    Falls back to deterministic-only on LLM failure or timeout.
    """

    def __init__(self) -> None:
        try:
            self._llm = get_hotel_intent_llm_client()
        except Exception as exc:
            logger.warning("IntentParser: LLM unavailable (%s), deterministic mode only", exc)
            self._llm = None

    def _deterministic_parse(self, request: HotelSearchRequest) -> ParsedIntent:
        """Build ParsedIntent purely from structured request fields (no LLM)."""
        api_filters: list[str] = list(request.amenities) + list(request.property_types)

        if request.free_cancellation:
            api_filters.append("free_cancellation::1")
        if request.adults_only:
            api_filters.append("stay_type::2")
        if request.pets_allowed:
            api_filters.append("facility::4")
        if request.meal_plan:
            api_filters.append(f"mealplan::{request.meal_plan}")

        user_segment = "couple"
        if request.children_ages:
            user_segment = "family"
        elif request.adults == 1:
            user_segment = "solo"
        elif request.adults > 4:
            user_segment = "group"

        return ParsedIntent(
            api_filters=list(set(api_filters)),
            price_min=request.budget_min,
            price_max=request.budget_max,
            user_segment=user_segment,
            children_ages=list(request.children_ages),
            scoring_weights=ScoringWeights(),
        )

    async def parse(self, request: HotelSearchRequest) -> ParsedIntent:
        """
        Parse HotelSearchRequest → ParsedIntent.

        If user_wishes is present and LLM is available:
          → LLM call (8s timeout) → merge with deterministic base.
        Otherwise:
          → purely deterministic result.
        """
        base = self._deterministic_parse(request)

        if not request.user_wishes or not self._llm:
            logger.info("IntentParser: deterministic mode (no user_wishes or no LLM)")
            return base

        try:
            prompt = _build_prompt(request)
            raw = await asyncio.wait_for(
                self._llm.generate_structured(prompt, _SYSTEM_PROMPT, max_tokens=1024),
                timeout=_LLM_TIMEOUT,
            )
            llm_intent = _parse_llm_result(raw, request)

            # Merge: union api_filters, LLM wins on semantic fields
            merged_filters = list(set(base.api_filters + llm_intent.api_filters))
            result = llm_intent.model_copy(update={"api_filters": merged_filters})

            logger.info(
                "IntentParser: LLM OK — segment=%s filters=%d weights=%s",
                result.user_segment,
                len(result.api_filters),
                {k: round(v, 2) for k, v in result.scoring_weights.model_dump().items()},
            )
            return result

        except asyncio.TimeoutError:
            logger.warning(
                "IntentParser: LLM timeout (%.1fs), deterministic fallback", _LLM_TIMEOUT
            )
            return base
        except Exception as exc:
            logger.warning("IntentParser: LLM error (%s), deterministic fallback", exc)
            return base
