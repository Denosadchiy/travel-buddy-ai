"""
POI Agent - preference-aware scoring and selection helpers.

This module builds a compact preference profile (optionally via LLM),
then applies deterministic scoring to keep POIs aligned with user intent
and geographic coherence.
"""
import json
import asyncio
import logging
import math
from dataclasses import dataclass, field
from typing import Optional

from src.config import settings, Settings
from src.domain.models import POICandidate, BlockType, BudgetLevel, PaceLevel
from src.domain.schemas import TripResponse, StructuredPreference
from src.infrastructure.llm_client import LLMClient, get_poi_selection_llm_client
from src.infrastructure.poi_providers import haversine_distance_km

logger = logging.getLogger(__name__)

CATEGORY_ALIASES = [
    ("fine dining", "restaurant"),
    ("seafood", "restaurant"),
    ("tapas", "restaurant"),
    ("cuisine", "restaurant"),
    ("restaurant", "restaurant"),
    ("cafe", "cafe"),
    ("coffee", "cafe"),
    ("bakery", "bakery"),
    ("breakfast", "cafe"),
    ("bar", "bar"),
    ("pub", "bar"),
    ("brewery", "bar"),
    ("nightclub", "nightlife"),
    ("club", "nightlife"),
    ("live music", "nightlife"),
    ("nightlife", "nightlife"),
    ("museum", "museum"),
    ("gallery", "museum"),
    ("art", "museum"),
    ("history", "attraction"),
    ("historical", "attraction"),
    ("architecture", "attraction"),
    ("landmark", "attraction"),
    ("monument", "attraction"),
    ("sightseeing", "attraction"),
    ("attraction", "attraction"),
    ("park", "park"),
    ("nature", "park"),
    ("viewpoint", "park"),
    ("garden", "park"),
    ("shopping", "shopping"),
    ("market", "shopping"),
    ("boutique", "shopping"),
    ("spa", "wellness"),
    ("wellness", "wellness"),
    ("gym", "wellness"),
]
VALID_CATEGORIES = {
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
}


def normalize_category(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    raw = str(value).strip().lower()
    if raw in VALID_CATEGORIES:
        return raw
    for keyword, mapped in CATEGORY_ALIASES:
        if keyword in raw:
            return mapped
    return None


@dataclass
class POIPreferenceProfile:
    """Preference signals used for scoring and filtering POIs."""
    must_include_keywords: list[str] = field(default_factory=list)
    avoid_keywords: list[str] = field(default_factory=list)
    search_keywords: list[str] = field(default_factory=list)
    category_boosts: dict[str, float] = field(default_factory=dict)
    tag_boosts: dict[str, float] = field(default_factory=dict)
    min_rating: float = 4.2
    preferred_price_levels: list[int] = field(default_factory=list)
    rating_weight: float = 1.0
    popularity_weight: float = 0.25
    price_level_weight: float = 1.5
    structured_preferences: list[StructuredPreference] = field(default_factory=list)


class POIPreferenceAgent:
    """
    Builds a preference profile from TripSpec using LLM when available.

    Falls back to heuristics when LLM is disabled or fails.
    """
    SYSTEM_PROMPT = """You are a travel preference analyzer.
Extract preference signals for POI ranking. Return ONLY JSON.

Constraints:
- Use only the provided taxonomy keys for category_boosts:
  restaurant, cafe, bar, museum, attraction, park, shopping, nightlife, wellness
- Keep keyword lists short (<= 6 items each).
- min_rating must be between 3.5 and 4.8.
- preferred_price_levels must be a list of 0-4 integers.

IMPORTANT: category_boosts mapping rules:
- Use strong positive boosts (+8.0 to +10.0) for interests that match
- Use strong negative penalties (-4.0 to -6.0) for incompatible categories
- "architecture", "views", "landmarks" → boost "attraction" (+10.0), penalize "museum" (-6.0)
- "museum", "art", "history" → boost "museum" (+10.0), boost "attraction" (+3.0), penalize "shopping" (-4.0), penalize "nightlife" (-4.0)
- "modern art" (separate from "museum") → boost "museum" (+4.0), prefer art galleries via tag_boosts
- "nightlife", "clubs", "bars" → boost "nightlife" (+8.0), boost "bar" (+6.0), penalize "museum" (-3.0)
- "shopping" → boost "shopping" (+8.0), penalize "museum" (-3.0)
- "gastronomy", "food", "culinary" → boost "restaurant" (+8.0), boost "cafe" (+5.0)
"""

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        app_settings: Optional[Settings] = None,
    ):
        self._llm_client = llm_client
        self._settings = app_settings or settings

    @property
    def llm_client(self) -> LLMClient:
        if self._llm_client is None:
            self._llm_client = get_poi_selection_llm_client(self._settings)
        return self._llm_client

    async def build_profile(
        self,
        trip_spec: TripResponse,
        timeout_seconds: Optional[float] = None,
    ) -> POIPreferenceProfile:
        """Build a preference profile for the trip."""
        if not self._settings.use_llm_for_poi_preferences:
            return self._build_heuristic_profile(trip_spec)
        if timeout_seconds is not None and timeout_seconds <= 0:
            return self._build_heuristic_profile(trip_spec)

        # Convert structured preferences to a dict for the prompt
        structured_prefs_dict = [p.model_dump() for p in trip_spec.structured_preferences]

        payload = {
            "city": trip_spec.city,
            "pace": trip_spec.pace.value if isinstance(trip_spec.pace, PaceLevel) else str(trip_spec.pace),
            "budget": trip_spec.budget.value if isinstance(trip_spec.budget, BudgetLevel) else str(trip_spec.budget),
            "interests": trip_spec.interests,
            "additional_preferences": trip_spec.additional_preferences or {},
            "structured_preferences": structured_prefs_dict,
        }

        prompt = f"""Trip preferences (JSON):
{json.dumps(payload, ensure_ascii=False)}

Return JSON with this exact schema:
{{
  "must_include_keywords": ["..."],
  "avoid_keywords": ["..."],
  "search_keywords": ["..."],
  "category_boosts": {{"restaurant": 0.0}},
  "tag_boosts": {{"michelin": 0.0}},
  "min_rating": 4.2,
  "preferred_price_levels": [2,3],
  "rating_weight": 1.0,
  "popularity_weight": 0.25,
  "price_level_weight": 1.5
}}"""

        try:
            timeout = (
                timeout_seconds
                if timeout_seconds is not None
                else float(self._settings.poi_preference_llm_timeout_seconds)
            )
            response = await asyncio.wait_for(
                self.llm_client.generate_structured(
                    prompt=prompt,
                    system_prompt=self.SYSTEM_PROMPT,
                    max_tokens=512,
                ),
                timeout=timeout,
            )
            profile = self._parse_profile_response(response, trip_spec)
            # Make sure to carry over the structured preferences
            profile.structured_preferences = trip_spec.structured_preferences
            return profile
        except Exception as exc:
            logger.warning(f"POI preference LLM failed, using heuristics: {exc}")
            return self._build_heuristic_profile(trip_spec)

    def _parse_profile_response(
        self,
        response: dict,
        trip_spec: TripResponse,
    ) -> POIPreferenceProfile:
        """Validate and normalize LLM response."""
        def _list(value):
            return value if isinstance(value, list) else []

        def _dict(value):
            return value if isinstance(value, dict) else {}

        profile = POIPreferenceProfile(
            must_include_keywords=[str(k).lower() for k in _list(response.get("must_include_keywords"))],
            avoid_keywords=[str(k).lower() for k in _list(response.get("avoid_keywords"))],
            search_keywords=[str(k).lower() for k in _list(response.get("search_keywords"))],
            category_boosts={k: float(v) for k, v in _dict(response.get("category_boosts")).items()},
            tag_boosts={k: float(v) for k, v in _dict(response.get("tag_boosts")).items()},
            min_rating=float(response.get("min_rating", 4.2)),
            preferred_price_levels=[int(v) for v in _list(response.get("preferred_price_levels")) if str(v).isdigit()],
            rating_weight=float(response.get("rating_weight", 1.0)),
            popularity_weight=float(response.get("popularity_weight", 0.25)),
            price_level_weight=float(response.get("price_level_weight", 1.5)),
            structured_preferences=trip_spec.structured_preferences, # Carry over from trip spec
        )

        if profile.min_rating < 3.5 or profile.min_rating > 4.8:
            profile.min_rating = 4.2

        return profile

    def _build_heuristic_profile(self, trip_spec: TripResponse) -> POIPreferenceProfile:
        """Fallback profile based on simple keyword heuristics."""
        interests = " ".join(trip_spec.interests or []).lower()
        prefs = json.dumps(trip_spec.additional_preferences or {}, ensure_ascii=False).lower()
        text = f"{interests} {prefs}"

        print(f"🔍 POI Agent: Building heuristic profile for interests: {trip_spec.interests}")
        print(f"🔍 POI Agent: Interests text: '{text}'")

        profile = POIPreferenceProfile()
        profile.structured_preferences = trip_spec.structured_preferences # Always carry over

        if "michelin" in text or "star restaurant" in text or "fine dining" in text:
            profile.must_include_keywords = ["michelin", "fine dining", "tasting"]
            profile.search_keywords = ["michelin", "fine dining"]
            profile.tag_boosts.update({"michelin": 4.0, "fine dining": 2.5})
            profile.min_rating = 4.5
            profile.preferred_price_levels = [3, 4]

        if "budget" in text or "cheap" in text:
            profile.preferred_price_levels = [0, 1]
            profile.min_rating = min(profile.min_rating, 4.2)
        
        if "expensive" in text:
            profile.preferred_price_levels = [3, 4]
            profile.min_rating = 4.4

        # Strong interest-based category boosts for better personalization
        if "shop" in text:
            profile.category_boosts["shopping"] = 8.0
            # Penalty for unrelated categories
            profile.category_boosts["museum"] = profile.category_boosts.get("museum", 0.0) - 3.0

        if "nightlife" in text or "club" in text:
            profile.category_boosts["nightlife"] = 8.0
            profile.category_boosts["bar"] = 6.0
            # Penalty for day-focused activities
            profile.category_boosts["museum"] = profile.category_boosts.get("museum", 0.0) - 3.0

        if "museum" in text or "history" in text:
            profile.category_boosts["museum"] = 10.0
            profile.category_boosts["art_gallery"] = 8.0
            profile.category_boosts["attraction"] = 3.0  # Lower than museum
            # Penalty for shopping/nightlife
            profile.category_boosts["shopping"] = profile.category_boosts.get("shopping", 0.0) - 4.0
            profile.category_boosts["nightlife"] = profile.category_boosts.get("nightlife", 0.0) - 4.0

        # Separate art from museums (modern art is different from museum art)
        if "modern art" in text or ("art" in text and "museum" not in text):
            profile.category_boosts["art_gallery"] = 10.0
            profile.category_boosts["museum"] = 4.0  # Some art museums ok, but galleries preferred
            profile.category_boosts["attraction"] = 3.0

        if "food" in text or "gastronomy" in text or "culinary" in text:
            profile.category_boosts["restaurant"] = 8.0
            profile.category_boosts["cafe"] = 5.0

        if "architecture" in text or "view" in text or "landmark" in text:
            profile.category_boosts["attraction"] = 10.0
            profile.category_boosts["park"] = 5.0
            # Strong penalty for museums when focus is on outdoor architecture/views
            if "museum" not in text and "art" not in text:
                profile.category_boosts["museum"] = profile.category_boosts.get("museum", 0.0) - 6.0
            # Penalty for indoor shopping
            profile.category_boosts["shopping"] = profile.category_boosts.get("shopping", 0.0) - 3.0

        # Process structured preferences to populate other profile fields
        for sp in profile.structured_preferences:
            if sp.keyword:
                profile.search_keywords.append(sp.keyword)
                profile.must_include_keywords.append(sp.keyword)
            if sp.price_level == "expensive":
                profile.preferred_price_levels = [3, 4]
            elif sp.price_level == "moderate":
                profile.preferred_price_levels = [2]
            elif sp.price_level == "cheap":
                profile.preferred_price_levels = [0, 1]

        print(f"✅ POI Agent: Final category_boosts: {dict(profile.category_boosts)}")

        return profile


def score_candidate(
    candidate: POICandidate,
    block_type: BlockType,
    desired_categories: list[str],
    profile: POIPreferenceProfile,
    anchor_lat: Optional[float] = None,
    anchor_lon: Optional[float] = None,
    day_center_lat: Optional[float] = None,
    day_center_lon: Optional[float] = None,
    distance_weight: float = 0.4,
) -> float:
    """Compute a preference-aware score for a POI candidate."""
    score = candidate.rank_score

    if candidate.rating is not None:
        score += profile.rating_weight * candidate.rating

    if candidate.user_ratings_total:
        score += profile.popularity_weight * math.log1p(candidate.user_ratings_total)

    if candidate.price_level is not None and profile.preferred_price_levels:
        if candidate.price_level in profile.preferred_price_levels:
            score += profile.price_level_weight
        else:
            score -= profile.price_level_weight * 0.75

    # Category boosts - apply boost for candidate's actual category
    # This allows penalties to work (e.g., -6.0 for museums when architecture is preferred)
    if candidate.category and candidate.category in profile.category_boosts:
        score += profile.category_boosts[candidate.category]

    # Keyword boosts/penalties
    haystack = f"{candidate.name} {' '.join(candidate.tags or [])}".lower()
    for keyword, boost in profile.tag_boosts.items():
        if keyword in haystack:
            score += boost
    for keyword in profile.must_include_keywords:
        if keyword in haystack:
            score += 6.0
    for keyword in profile.avoid_keywords:
        if keyword in haystack:
            score -= 5.0
            
    # Huge boost for matching structured preferences
    for sp in profile.structured_preferences:
        matches = True
        if sp.keyword and sp.keyword.lower() not in haystack:
            matches = False
        sp_category = normalize_category(sp.category)
        if sp_category:
            candidate_category = (candidate.category or "").lower()
            if sp_category not in candidate_category:
                if not candidate.tags or not any(sp_category == tag.lower() for tag in candidate.tags):
                    matches = False
        
        price_map = {"cheap": [0,1], "moderate": [2], "expensive": [3,4]}
        if sp.price_level and candidate.price_level is not None:
            if candidate.price_level not in price_map.get(sp.price_level, []):
                matches = False

        if matches:
            score += 50.0  # Very strong boost for matching a specific request

    if candidate.business_status and candidate.business_status.upper() != "OPERATIONAL":
        score -= 2.5

    if block_type == BlockType.MEAL and candidate.open_now is False:
        score -= 1.0

    # Distance penalty (anchor and day center)
    if candidate.lat is not None and candidate.lon is not None:
        if anchor_lat is not None and anchor_lon is not None:
            score -= distance_weight * haversine_distance_km(
                anchor_lat, anchor_lon, candidate.lat, candidate.lon
            )
        if day_center_lat is not None and day_center_lon is not None:
            score -= (distance_weight * 0.5) * haversine_distance_km(
                day_center_lat, day_center_lon, candidate.lat, candidate.lon
            )

    # Block-type nuance
    if block_type == BlockType.MEAL and candidate.rating is not None:
        score += 0.25 * candidate.rating

    return score


def filter_candidates_for_block(
    candidates: list[POICandidate],
    profile: POIPreferenceProfile,
    block_type: BlockType,
) -> list[POICandidate]:
    """Filter candidates by rating and strong preference keywords if available."""
    if not candidates:
        return []

    filtered = [c for c in candidates if (c.rating or 0) >= profile.min_rating]
    if not filtered:
        filtered = candidates

    # Prefer operational places when status is available
    if any(c.business_status for c in filtered):
        operational = [
            c for c in filtered
            if not c.business_status or c.business_status.upper() == "OPERATIONAL"
        ]
        if operational:
            filtered = operational

    # If there are structured preferences for this block type, try to match them
    block_category_map = {
        BlockType.MEAL: ["restaurant", "cafe"],
        BlockType.ACTIVITY: ["museum", "attraction", "park"],
        BlockType.NIGHTLIFE: ["bar", "nightclub"],
    }
    
    applicable_sp = []
    for sp in profile.structured_preferences:
        normalized = normalize_category(sp.category)
        if normalized and normalized in block_category_map.get(block_type, []):
            applicable_sp.append(sp)

    if applicable_sp:
        matched = []
        for sp in applicable_sp:
            for candidate in filtered:
                haystack = f"{candidate.name} {' '.join(candidate.tags or [])}".lower()
                if sp.keyword and sp.keyword.lower() in haystack:
                    matched.append(candidate)
        if matched:
            return matched

    if profile.must_include_keywords and block_type == BlockType.MEAL:
        matched = []
        for candidate in filtered:
            haystack = f"{candidate.name} {' '.join(candidate.tags or [])}".lower()
            if any(keyword in haystack for keyword in profile.must_include_keywords):
                matched.append(candidate)
        if matched:
            return matched

    return filtered
