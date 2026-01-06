"""
LLM-based POI Selection service.

This service uses LLM to select and re-rank POI candidates that have ALREADY
been filtered deterministically (by city radius, block type, category).

CRITICAL SAFETY INVARIANT:
- The LLM can ONLY choose from candidates provided to it.
- The LLM MUST NOT invent new places.
- All LLM outputs are validated against the provided candidate list.
- On any failure (invalid JSON, unknown IDs, etc.), we fall back to deterministic ranking.
"""
import json
import logging
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from src.config import settings, Settings
from src.domain.models import POICandidate, BlockType, BudgetLevel, PaceLevel
from src.domain.schemas import TripResponse
from src.infrastructure.llm_client import (
    LLMClient,
    get_poi_selection_llm_client,
    get_route_engineer_llm_client,
)
from src.infrastructure.poi_providers import haversine_distance_km

logger = logging.getLogger(__name__)


# ============================================================================
# Context dataclasses for LLM
# ============================================================================

@dataclass
class DayContext:
    """Context about the current day being planned."""
    day_number: int
    date: str
    theme: str
    already_selected_poi_ids: list[UUID]  # POIs already selected for this day


@dataclass
class BlockContext:
    """Context about the current block being filled."""
    block_index: int
    block_type: BlockType
    start_time: str
    end_time: str
    theme: Optional[str]
    desired_categories: list[str]


@dataclass
class TripContext:
    """Summarized trip context for LLM."""
    city: str
    pace: PaceLevel
    budget: BudgetLevel
    interests: list[str]
    additional_notes: Optional[str]


# ============================================================================
# POI Selection LLM Service
# ============================================================================

class POISelectionLLMService:
    """
    LLM-based POI selection service.

    Selects and re-ranks POI candidates using LLM, with strict validation
    to ensure the LLM never invents new places.
    """

    # System prompt - VERY STRICT about not inventing places
    SYSTEM_PROMPT = """You are a POI curator for a travel itinerary. Your ONLY job is to SELECT places from a given list of candidates.

CRITICAL RULES - YOU MUST FOLLOW THESE EXACTLY:
1. You MUST ONLY choose from the candidates provided in the input.
2. You MUST NOT invent, imagine, or suggest any place that is not in the candidate list.
3. You MUST NOT modify candidate IDs or names in any way.
4. If none of the candidates are suitable, return an empty selection - DO NOT make up alternatives.
5. Return ONLY valid JSON matching the exact schema specified.

Your goal is to select the best POIs from the given candidates based on:
- User preferences (pace, interests, budget)
- Block context (meal, activity, nightlife, etc.)
- Diversity (avoid repetition within the day)
- Quality (prefer higher-rated places when appropriate)

IMPORTANT: If you are unsure about a place or it seems to not fit well, simply do not select it.
Do NOT try to fill all slots if the candidates are not good matches."""

    # Day-level selection prompt (select one per block, maintain geographic coherence)
    DAY_LEVEL_SYSTEM_PROMPT = """You are a route-aware POI selector for a single day.

CRITICAL RULES:
1. You MUST ONLY choose from the candidates provided for each block.
2. You MUST select at most ONE candidate per block.
3. You MUST NOT repeat the same candidate across blocks.
4. You MUST NOT invent places or IDs.
5. Prefer candidates that keep consecutive blocks close (avoid long hops).
6. Return ONLY valid JSON matching the schema. No extra text.
"""

    DAY_LEVEL_SYSTEM_PROMPT_WITH_REQUESTS = """You are a route-aware POI selector for a single day.

CRITICAL RULES:
1. You MUST ONLY choose from the candidates provided for each block.
2. You MUST select at most ONE candidate per block.
3. You MUST NOT repeat the same candidate across blocks.
4. You MUST NOT invent places or IDs.
5. Prefer candidates that keep consecutive blocks close (avoid long hops).
6. If key preferences cannot be satisfied with the given candidates, request more candidates.
7. Return ONLY valid JSON matching the schema. No extra text.
"""

    DAY_LEVEL_MAX_CANDIDATES_PER_BLOCK = 8
    REQUEST_CATEGORIES = [
        "restaurant",
        "cafe",
        "bar",
        "bakery",
        "food",
        "museum",
        "attraction",
        "park",
        "shopping",
        "wellness",
        "nightlife",
    ]

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        app_settings: Optional[Settings] = None,
    ):
        """
        Initialize POI Selection LLM Service.

        Args:
            llm_client: Optional LLM client (for dependency injection / testing)
            app_settings: Optional settings override (for testing)
        """
        self._llm_client = llm_client
        self._route_llm_client: Optional[LLMClient] = None
        self._settings = app_settings or settings

    @property
    def llm_client(self) -> LLMClient:
        """Lazy initialization of LLM client."""
        if self._llm_client is None:
            self._llm_client = get_poi_selection_llm_client(self._settings)
        return self._llm_client

    @property
    def route_llm_client(self) -> LLMClient:
        """Lazy initialization of Route Engineer LLM client."""
        if self._route_llm_client is None:
            try:
                self._route_llm_client = get_route_engineer_llm_client(self._settings)
            except Exception as exc:
                logger.warning(
                    f"Route engineer LLM unavailable, falling back: {exc}"
                )
                self._route_llm_client = self.llm_client
        return self._route_llm_client

    def _build_candidate_description(
        self,
        candidate: POICandidate,
        anchor_lat: Optional[float] = None,
        anchor_lon: Optional[float] = None,
        city_center_lat: Optional[float] = None,
        city_center_lon: Optional[float] = None,
    ) -> dict:
        """Build a compact description of a candidate for the LLM."""
        description = {
            "candidate_id": str(candidate.poi_id),
            "name": candidate.name,
            "category": candidate.category,
            "tags": candidate.tags[:5] if candidate.tags else [],  # Limit tags
            "rating": candidate.rating,
            "user_ratings_total": candidate.user_ratings_total,
            "price_level": candidate.price_level,
            "business_status": candidate.business_status,
            "open_now": candidate.open_now,
            "description": candidate.description,
            "reviews": candidate.reviews[:2] if candidate.reviews else [],
            "rank_score": round(candidate.rank_score, 2),
            "location": candidate.location[:100] if candidate.location else "",  # Truncate
        }

        if candidate.lat is not None and candidate.lon is not None:
            if anchor_lat is not None and anchor_lon is not None:
                description["distance_km_from_anchor"] = round(
                    haversine_distance_km(
                        anchor_lat, anchor_lon, candidate.lat, candidate.lon
                    ),
                    2,
                )
            if city_center_lat is not None and city_center_lon is not None:
                description["distance_km_from_center"] = round(
                    haversine_distance_km(
                        city_center_lat, city_center_lon, candidate.lat, candidate.lon
                    ),
                    2,
                )

        return description

    def _build_user_prompt(
        self,
        trip_context: TripContext,
        day_context: DayContext,
        block_context: BlockContext,
        candidates: list[POICandidate],
        max_results: int,
    ) -> str:
        """Build the user prompt for POI selection."""
        # Build candidate list
        candidate_descriptions = [
            self._build_candidate_description(c) for c in candidates
        ]

        # Build list of already-used POI IDs (as strings for comparison)
        already_used = [str(poi_id) for poi_id in day_context.already_selected_poi_ids]

        prompt = f"""Select the best places for this trip block.

## Trip Information
- City: {trip_context.city}
- Pace: {trip_context.pace.value} (slow=relaxed, few activities; medium=balanced; fast=packed schedule)
- Budget: {trip_context.budget.value} (low=budget-friendly; medium=moderate; high=premium)
- Interests: {', '.join(trip_context.interests) if trip_context.interests else 'general sightseeing'}
{f'- Notes: {trip_context.additional_notes}' if trip_context.additional_notes else ''}

## Current Day
- Day {day_context.day_number}: {day_context.theme}

## Block to Fill
- Type: {block_context.block_type.value}
- Time: {block_context.start_time} - {block_context.end_time}
{f'- Theme: {block_context.theme}' if block_context.theme else ''}
- Looking for: {', '.join(block_context.desired_categories)}

## Already Selected Today (DO NOT REPEAT)
{json.dumps(already_used) if already_used else '[]'}

## Available Candidates
```json
{json.dumps(candidate_descriptions, indent=2)}
```

## Instructions
1. Select up to {max_results} places from the candidates above.
2. Order them by preference (best first).
3. Do NOT select any place from the "Already Selected Today" list.
4. Use ONLY the exact candidate_id values from the candidates list.
5. Do NOT invent new places or IDs.

## Required Response Format (JSON only, no other text)
```json
{{
  "selected_places": [
    {{
      "candidate_id": "uuid-from-candidates",
      "reason": "Brief reason for selection (optional)"
    }}
  ]
}}
```

Respond with JSON only. No explanations outside the JSON."""

        return prompt

    def _parse_and_validate_response(
        self,
        llm_response: dict,
        candidates: list[POICandidate],
        already_selected_ids: set[UUID],
        max_results: int,
    ) -> list[POICandidate]:
        """
        Parse and validate LLM response against the candidate list.

        This is the critical safety layer that ensures we never use
        any POI that wasn't in our original candidate list.

        Args:
            llm_response: Parsed JSON from LLM
            candidates: Original candidate list
            already_selected_ids: POI IDs already used today
            max_results: Maximum results to return

        Returns:
            Validated list of POICandidate objects (subset of candidates)
        """
        # Build lookup map: string UUID -> POICandidate
        candidate_map: dict[str, POICandidate] = {
            str(c.poi_id): c for c in candidates
        }

        # Extract selected places from LLM response
        selected_places = llm_response.get("selected_places", [])
        if not isinstance(selected_places, list):
            logger.warning("LLM response 'selected_places' is not a list, ignoring")
            return []

        validated_candidates: list[POICandidate] = []
        seen_ids: set[str] = set()

        for item in selected_places:
            if not isinstance(item, dict):
                logger.debug(f"Skipping non-dict item in selected_places: {item}")
                continue

            candidate_id = item.get("candidate_id")
            if not candidate_id:
                logger.debug("Skipping item without candidate_id")
                continue

            candidate_id_str = str(candidate_id)

            # Check if this ID exists in our candidates
            if candidate_id_str not in candidate_map:
                logger.warning(
                    f"LLM returned unknown candidate_id '{candidate_id_str}' - IGNORING. "
                    "This could be an attempt to invent a new place."
                )
                continue

            # Check for duplicates in this response
            if candidate_id_str in seen_ids:
                logger.debug(f"Skipping duplicate candidate_id: {candidate_id_str}")
                continue

            # Check if already used today
            candidate = candidate_map[candidate_id_str]
            if candidate.poi_id in already_selected_ids:
                logger.debug(f"Skipping already-selected POI: {candidate.name}")
                continue

            # Valid selection!
            validated_candidates.append(candidate)
            seen_ids.add(candidate_id_str)

            # Stop if we have enough
            if len(validated_candidates) >= max_results:
                break

        return validated_candidates

    def _build_day_prompt(
        self,
        trip_context: TripContext,
        day_context: DayContext,
        blocks: list[BlockContext],
        candidates_by_block: dict[int, list[POICandidate]],
        max_hop_distance_km: Optional[float],
        anchor_lat: Optional[float],
        anchor_lon: Optional[float],
        city_center_lat: Optional[float],
        city_center_lon: Optional[float],
        preference_summary: Optional[dict],
        max_candidates_per_block: int,
        must_visit_ids: Optional[list[UUID]] = None,
        nice_to_have_ids: Optional[list[UUID]] = None,
        include_requests: bool = False,
    ) -> str:
        """Build a day-level prompt for selecting one POI per block."""
        must_visit_ids = must_visit_ids or []
        nice_to_have_ids = nice_to_have_ids or []
        must_id_strings = [str(pid) for pid in must_visit_ids]
        nice_id_strings = [str(pid) for pid in nice_to_have_ids]

        blocks_payload = []
        for block in blocks:
            candidates = candidates_by_block.get(block.block_index, [])
            limited = candidates[:max_candidates_per_block]
            candidate_descriptions = [
                self._build_candidate_description(
                    c,
                    anchor_lat=anchor_lat,
                    anchor_lon=anchor_lon,
                    city_center_lat=city_center_lat,
                    city_center_lon=city_center_lon,
                )
                for c in limited
            ]

            blocks_payload.append({
                "block_index": block.block_index,
                "type": block.block_type.value,
                "time": f"{block.start_time} - {block.end_time}",
                "theme": block.theme or "",
                "desired_categories": block.desired_categories,
                "candidates": candidate_descriptions,
            })

        anchor_payload = None
        if anchor_lat is not None and anchor_lon is not None:
            anchor_payload = {"lat": anchor_lat, "lon": anchor_lon}

        priority_payload = []
        if must_id_strings or nice_id_strings:
            priority_ids = set(must_id_strings + nice_id_strings)
            seen_ids = set()
            for block in blocks:
                for candidate in candidates_by_block.get(block.block_index, []):
                    candidate_id = str(candidate.poi_id)
                    if candidate_id not in priority_ids or candidate_id in seen_ids:
                        continue
                    priority_payload.append({
                        "candidate_id": candidate_id,
                        "name": candidate.name,
                        "category": candidate.category,
                        "block_index": block.block_index,
                        "priority": "must" if candidate_id in must_id_strings else "nice",
                    })
                    seen_ids.add(candidate_id)

        request_categories = json.dumps(self.REQUEST_CATEGORIES)
        request_instructions = ""
        response_schema = """{
  "selections": [
    {"block_index": 0, "candidate_id": "uuid-from-candidates", "reason": "optional"}
  ]
}"""

        if include_requests:
            request_instructions = f"""
5. Prefer must-visit candidates when available, then nice-to-have.
6. If key preferences cannot be satisfied with current candidates, add 1-3 requests.

## Request Categories (use only these)
{request_categories}
"""
            response_schema = """{
  "selections": [
    {"block_index": 0, "candidate_id": "uuid-from-candidates", "reason": "optional"}
  ],
  "requests": [
    {
      "category": "restaurant",
      "keywords": ["craft beer", "michelin"],
      "min_count": 10,
      "priority": "must"
    }
  ]
}"""
        else:
            request_instructions = "5. Prefer must-visit candidates when available, then nice-to-have."

        prompt = f"""Select one candidate per block for this day.

## Trip Information
- City: {trip_context.city}
- Pace: {trip_context.pace.value}
- Budget: {trip_context.budget.value}
- Interests: {', '.join(trip_context.interests) if trip_context.interests else 'general sightseeing'}
{f'- Notes: {trip_context.additional_notes}' if trip_context.additional_notes else ''}

## Preference Signals
{json.dumps(preference_summary or {}, indent=2)}

## Day Context
- Day {day_context.day_number}: {day_context.theme}
- Start anchor (start near this if possible): {json.dumps(anchor_payload) if anchor_payload else 'null'}
- Max hop distance (km): {max_hop_distance_km if max_hop_distance_km is not None else 'null'}

## Already Selected (do not repeat)
{json.dumps([str(pid) for pid in day_context.already_selected_poi_ids])}

## Priority Candidates (if present in candidates, prefer them)
{json.dumps(priority_payload, indent=2)}

## Blocks and Candidates
```json
{json.dumps(blocks_payload, indent=2)}
```

## Instructions
1. Select at most ONE candidate per block.
2. Prefer candidates that keep consecutive blocks close together.
3. Avoid duplicates across blocks.
4. Use ONLY candidate_id values from each block's candidate list.
{request_instructions}

## Required Response Format (JSON only)
```json
{response_schema}
```

Respond with JSON only."""

        return prompt

    def _parse_day_response(
        self,
        llm_response: dict,
        candidates_by_block: dict[int, list[POICandidate]],
        already_selected_ids: set[UUID],
    ) -> dict[int, POICandidate]:
        """Validate day-level response and map to candidates by block."""
        selections = llm_response.get("selections", [])
        if not isinstance(selections, list):
            logger.warning("LLM response 'selections' is not a list")
            return {}

        result: dict[int, POICandidate] = {}
        seen_ids: set[str] = set()

        for item in selections:
            if not isinstance(item, dict):
                continue

            block_index = item.get("block_index")
            candidate_id = item.get("candidate_id")
            if not isinstance(block_index, int) or candidate_id is None:
                continue

            if block_index in result:
                continue

            candidates = candidates_by_block.get(block_index, [])
            candidate_map = {str(c.poi_id): c for c in candidates}
            candidate_id_str = str(candidate_id)
            if candidate_id_str not in candidate_map:
                continue

            if candidate_id_str in seen_ids:
                continue

            candidate = candidate_map[candidate_id_str]
            if candidate.poi_id in already_selected_ids:
                continue

            result[block_index] = candidate
            seen_ids.add(candidate_id_str)

        return result

    def _parse_day_response_with_requests(
        self,
        llm_response: dict,
        candidates_by_block: dict[int, list[POICandidate]],
        already_selected_ids: set[UUID],
    ) -> tuple[dict[int, POICandidate], list[dict]]:
        """Validate day-level response and extract search requests."""
        selections = self._parse_day_response(
            llm_response=llm_response,
            candidates_by_block=candidates_by_block,
            already_selected_ids=already_selected_ids,
        )

        raw_requests = llm_response.get("requests", [])
        if not isinstance(raw_requests, list):
            raw_requests = []

        requests: list[dict] = []
        seen_categories: set[str] = set()
        for item in raw_requests:
            if not isinstance(item, dict):
                continue
            category = item.get("category")
            if not isinstance(category, str):
                continue
            category = category.strip().lower()
            if not category or category in seen_categories:
                continue
            keywords_raw = item.get("keywords", [])
            keywords: list[str] = []
            if isinstance(keywords_raw, list):
                for keyword in keywords_raw:
                    keyword = str(keyword).strip().lower()
                    if keyword and keyword not in keywords:
                        keywords.append(keyword)

            try:
                min_count = int(item.get("min_count", 0))
            except (TypeError, ValueError):
                min_count = 0
            if min_count <= 0:
                min_count = 6
            min_count = max(4, min(20, min_count))

            priority = item.get("priority", "normal")
            if priority not in {"must", "high", "normal"}:
                priority = "normal"

            requests.append({
                "category": category,
                "keywords": keywords[:4],
                "min_count": min_count,
                "priority": priority,
            })
            seen_categories.add(category)

            if len(requests) >= 3:
                break

        return selections, requests

    async def select_pois_for_day(
        self,
        trip_context: TripContext,
        day_context: DayContext,
        blocks: list[BlockContext],
        candidates_by_block: dict[int, list[POICandidate]],
        already_selected_ids: set[UUID],
        max_hop_distance_km: Optional[float] = None,
        anchor_lat: Optional[float] = None,
        anchor_lon: Optional[float] = None,
        city_center_lat: Optional[float] = None,
        city_center_lon: Optional[float] = None,
        preference_summary: Optional[dict] = None,
    ) -> dict[int, POICandidate]:
        """
        Use LLM to select one POI per block for a day.

        Returns a mapping of block_index -> selected POICandidate.
        """
        if not blocks:
            return {}

        max_candidates = min(
            self._settings.poi_selection_max_candidates,
            self.DAY_LEVEL_MAX_CANDIDATES_PER_BLOCK,
        )

        prompt = self._build_day_prompt(
            trip_context=trip_context,
            day_context=day_context,
            blocks=blocks,
            candidates_by_block=candidates_by_block,
            max_hop_distance_km=max_hop_distance_km,
            anchor_lat=anchor_lat,
            anchor_lon=anchor_lon,
            city_center_lat=city_center_lat,
            city_center_lon=city_center_lon,
            preference_summary=preference_summary,
            max_candidates_per_block=max_candidates,
        )

        try:
            logger.info(
                f"Calling LLM for day-level POI selection: day={day_context.day_number}, "
                f"blocks={len(blocks)}"
            )
            llm_response = await self.llm_client.generate_structured(
                prompt=prompt,
                system_prompt=self.DAY_LEVEL_SYSTEM_PROMPT,
                max_tokens=768,
            )

            selected_map = self._parse_day_response(
                llm_response=llm_response,
                candidates_by_block=candidates_by_block,
                already_selected_ids=already_selected_ids,
            )

            if selected_map:
                logger.info(
                    f"LLM selected POIs for {len(selected_map)} blocks on day {day_context.day_number}"
                )
                return selected_map

        except ValueError as e:
            logger.warning(f"Day-level LLM selection failed (JSON error): {e}")
        except Exception as e:
            logger.warning(f"Day-level LLM selection failed (unexpected error): {e}")

        return {}

    async def select_pois_for_day_with_requests(
        self,
        trip_context: TripContext,
        day_context: DayContext,
        blocks: list[BlockContext],
        candidates_by_block: dict[int, list[POICandidate]],
        already_selected_ids: set[UUID],
        max_hop_distance_km: Optional[float] = None,
        anchor_lat: Optional[float] = None,
        anchor_lon: Optional[float] = None,
        city_center_lat: Optional[float] = None,
        city_center_lon: Optional[float] = None,
        preference_summary: Optional[dict] = None,
        must_visit_ids: Optional[list[UUID]] = None,
        nice_to_have_ids: Optional[list[UUID]] = None,
    ) -> tuple[dict[int, POICandidate], list[dict]]:
        """
        Use LLM to select one POI per block for a day and request more candidates.

        Returns a mapping of block_index -> selected POICandidate and a list of
        search request dicts.
        """
        if not blocks:
            return {}, []

        max_candidates = min(
            self._settings.poi_selection_max_candidates,
            self.DAY_LEVEL_MAX_CANDIDATES_PER_BLOCK,
        )

        prompt = self._build_day_prompt(
            trip_context=trip_context,
            day_context=day_context,
            blocks=blocks,
            candidates_by_block=candidates_by_block,
            max_hop_distance_km=max_hop_distance_km,
            anchor_lat=anchor_lat,
            anchor_lon=anchor_lon,
            city_center_lat=city_center_lat,
            city_center_lon=city_center_lon,
            preference_summary=preference_summary,
            max_candidates_per_block=max_candidates,
            must_visit_ids=must_visit_ids,
            nice_to_have_ids=nice_to_have_ids,
            include_requests=True,
        )

        try:
            logger.info(
                f"Calling LLM for day-level POI selection with requests: day={day_context.day_number}, "
                f"blocks={len(blocks)}"
            )
            llm_response = await self.route_llm_client.generate_structured(
                prompt=prompt,
                system_prompt=self.DAY_LEVEL_SYSTEM_PROMPT_WITH_REQUESTS,
                max_tokens=896,
            )

            selected_map, requests = self._parse_day_response_with_requests(
                llm_response=llm_response,
                candidates_by_block=candidates_by_block,
                already_selected_ids=already_selected_ids,
            )

            if selected_map:
                logger.info(
                    f"LLM selected POIs for {len(selected_map)} blocks on day {day_context.day_number}"
                )
            if requests:
                logger.info(
                    f"LLM requested {len(requests)} additional POI searches on day {day_context.day_number}"
                )
            return selected_map, requests

        except ValueError as e:
            logger.warning(f"Day-level LLM selection failed (JSON error): {e}")
        except Exception as e:
            logger.warning(f"Day-level LLM selection failed (unexpected error): {e}")

        return {}, []

    async def select_pois_for_block(
        self,
        trip_context: TripContext,
        day_context: DayContext,
        block_context: BlockContext,
        candidates: list[POICandidate],
        max_results: int = 3,
    ) -> list[POICandidate]:
        """
        Use LLM to select POIs for a block from the given candidates.

        This method has a strict fallback: if anything goes wrong with the LLM
        (invalid response, parsing error, etc.), it falls back to returning
        the original candidates in their deterministic order.

        Args:
            trip_context: Summary of trip preferences
            day_context: Context about the current day
            block_context: Context about the current block
            candidates: Pre-filtered candidate POIs (from deterministic layer)
            max_results: Maximum POIs to select

        Returns:
            List of selected POICandidate objects (always a subset of candidates)
        """
        if not candidates:
            return []

        # Limit candidates to control cost (use top N by existing rank_score)
        max_candidates = self._settings.poi_selection_max_candidates
        limited_candidates = candidates[:max_candidates]

        # Build already-selected IDs set for validation
        already_selected_ids = set(day_context.already_selected_poi_ids)

        # Build prompt
        user_prompt = self._build_user_prompt(
            trip_context=trip_context,
            day_context=day_context,
            block_context=block_context,
            candidates=limited_candidates,
            max_results=max_results,
        )

        try:
            # Call LLM
            logger.info(
                f"Calling LLM for POI selection: day={day_context.day_number}, "
                f"block={block_context.block_index}, type={block_context.block_type.value}, "
                f"candidates={len(limited_candidates)}"
            )

            llm_response = await self.llm_client.generate_structured(
                prompt=user_prompt,
                system_prompt=self.SYSTEM_PROMPT,
                max_tokens=512,  # POI selection responses are compact
            )

            # Validate and map back to candidates
            selected = self._parse_and_validate_response(
                llm_response=llm_response,
                candidates=limited_candidates,
                already_selected_ids=already_selected_ids,
                max_results=max_results,
            )

            if selected:
                logger.info(
                    f"LLM selected {len(selected)} POIs for block: "
                    f"{[c.name for c in selected]}"
                )
                return selected
            else:
                logger.warning(
                    "LLM returned no valid selections, falling back to deterministic"
                )
                # Fall through to fallback below

        except ValueError as e:
            # JSON parsing error from LLM client
            logger.warning(f"LLM POI selection failed (JSON error): {e}")
        except Exception as e:
            # Any other error (network, timeout, etc.)
            logger.warning(f"LLM POI selection failed (unexpected error): {e}")

        # FALLBACK: Use deterministic ranking (original candidate order)
        logger.info("Using deterministic fallback for POI selection")
        fallback_candidates = [
            c for c in limited_candidates
            if c.poi_id not in already_selected_ids
        ]
        return fallback_candidates[:max_results]


def build_trip_context_from_response(trip_spec: TripResponse) -> TripContext:
    """Build TripContext from TripResponse."""
    additional_notes = None
    if trip_spec.additional_preferences:
        # Extract relevant notes
        notes_parts = []
        if "note" in trip_spec.additional_preferences:
            notes_parts.append(trip_spec.additional_preferences["note"])
        if "avoid" in trip_spec.additional_preferences:
            avoid = trip_spec.additional_preferences["avoid"]
            if isinstance(avoid, list):
                notes_parts.append(f"Avoid: {', '.join(avoid)}")
            else:
                notes_parts.append(f"Avoid: {avoid}")
        if "dietary" in trip_spec.additional_preferences:
            dietary = trip_spec.additional_preferences["dietary"]
            if isinstance(dietary, list):
                notes_parts.append(f"Dietary: {', '.join(dietary)}")
            else:
                notes_parts.append(f"Dietary: {dietary}")
        if notes_parts:
            additional_notes = "; ".join(notes_parts)

    return TripContext(
        city=trip_spec.city,
        pace=trip_spec.pace,
        budget=trip_spec.budget,
        interests=trip_spec.interests,
        additional_notes=additional_notes,
    )
