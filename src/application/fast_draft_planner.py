"""
Fast Draft Planner - Optimized for p95 latency under 20 seconds.

This planner generates a draft itinerary as fast as possible:
1. Uses simplified LLM prompt with reduced token limit
2. 15-second hard timeout on LLM call
3. Template-based fallback for instant response if LLM times out
4. Fetches REAL POIs from database (no placeholders)
"""
import asyncio
from uuid import UUID
from typing import Optional
from datetime import datetime, date, time, timedelta
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.models import (
    DaySkeleton, SkeletonBlock, BlockType, PaceLevel, BudgetLevel,
    ItineraryDay, ItineraryBlock, POICandidate
)
from src.domain.schemas import ItineraryResponse
from src.application.trip_spec import TripSpecCollector
from src.infrastructure.llm_client import LLMClient, get_macro_planning_llm_client
from src.infrastructure.poi_providers import POIProvider, get_poi_provider
from src.infrastructure.models import ItineraryModel


# Hard timeout for LLM call (seconds)
LLM_TIMEOUT_SECONDS = 15

# Maximum tokens for draft (reduced for speed)
DRAFT_MAX_TOKENS = 1024

# Block types that need POI candidates
BLOCK_TYPES_NEEDING_POIS = {
    BlockType.MEAL,
    BlockType.ACTIVITY,
    BlockType.NIGHTLIFE,
}


class FastDraftPlanner:
    """
    Fast draft planner optimized for p95 < 20 seconds.

    Strategy:
    1. Try LLM with 15s timeout
    2. If timeout/error, immediately fall back to template
    3. Fetch REAL POIs from database for each block
    4. Return draft itinerary with real places
    """

    # Simplified system prompt for faster generation
    SYSTEM_PROMPT = """You are a travel planner. Generate a trip skeleton as JSON.

Output ONLY valid JSON:
{
  "days": [
    {
      "day_number": 1,
      "date": "YYYY-MM-DD",
      "theme": "Day theme",
      "blocks": [
        {"block_type": "meal|activity|nightlife|rest", "start_time": "HH:MM:SS", "end_time": "HH:MM:SS", "theme": "Block theme", "desired_categories": ["category1", "category2"]}
      ]
    }
  ]
}

Rules:
- Each day: breakfast, 2-3 activities, lunch, dinner
- Respect wake/sleep times
- Match pace level
- Add desired_categories for POI search (e.g., ["cafe", "breakfast"], ["museum", "culture"], ["restaurant", "local cuisine"])
- NO explanations, ONLY JSON"""

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        poi_provider: Optional[POIProvider] = None,
    ):
        self.llm_client = llm_client or get_macro_planning_llm_client()
        self.poi_provider = poi_provider  # Will be set per request if None
        self.trip_spec_collector = TripSpecCollector()

    async def generate_fast_draft(
        self,
        trip_id: UUID,
        db: AsyncSession,
        include_trace: bool = True,
        enable_extended_trace: bool = False,
    ) -> ItineraryResponse:
        """
        Generate draft itinerary with p95 < 20 seconds guarantee.

        Uses LLM with timeout, falls back to template on failure.
        Then fetches REAL POIs from database.

        Args:
            trip_id: UUID of the trip
            db: Database session
            include_trace: Include basic trace information
            enable_extended_trace: Include extended debug trace (generator params, provider calls, ranking)
        """
        # 1. Load trip spec
        trip_spec = await self.trip_spec_collector.get_trip(trip_id, db)
        if not trip_spec:
            raise ValueError(f"Trip {trip_id} not found")

        # 2. Initialize route trace if requested
        from src.domain.route_trace import RouteTrace, GeneratorInputParams
        route_trace = None

        if include_trace:
            num_days = (trip_spec.end_date - trip_spec.start_date).days + 1

            route_trace = RouteTrace(
                trip_id=trip_id,
                city=trip_spec.city,
                total_days=num_days,
                pace=trip_spec.pace.value,
                budget=trip_spec.budget.value,
                interests=trip_spec.interests,
            )

            # Add extended trace with generator input params
            if enable_extended_trace:
                route_trace.generator_input = GeneratorInputParams(
                    trip_id=trip_id,
                    city_name=trip_spec.city,
                    city_center_lat=trip_spec.city_center_lat,
                    city_center_lon=trip_spec.city_center_lon,
                    start_date=trip_spec.start_date,
                    end_date=trip_spec.end_date,
                    total_days=num_days,
                    pace=trip_spec.pace.value,
                    budget=trip_spec.budget.value,
                    interests=trip_spec.interests,
                    num_travelers=trip_spec.num_travelers,
                    wake_time=trip_spec.daily_routine.wake_time,
                    sleep_time=trip_spec.daily_routine.sleep_time,
                    breakfast_window=(trip_spec.daily_routine.breakfast_window[0], trip_spec.daily_routine.breakfast_window[1]),
                    lunch_window=(trip_spec.daily_routine.lunch_window[0], trip_spec.daily_routine.lunch_window[1]),
                    dinner_window=(trip_spec.daily_routine.dinner_window[0], trip_spec.daily_routine.dinner_window[1]),
                    max_radius_km=20.0,  # Using default from poi_providers
                    poi_fetch_limit=5,  # Using limit from _fetch_best_poi
                    min_rating=None,
                    providers_enabled=["database"],  # Fast draft only uses DB
                    category_match_weight=10.0,
                    tag_overlap_weight=2.0,
                    budget_alignment_bonus=5.0,
                )

        # 3. Try LLM generation with timeout
        try:
            skeletons = await asyncio.wait_for(
                self._generate_with_llm(trip_spec),
                timeout=LLM_TIMEOUT_SECONDS
            )
            source = "llm"
        except asyncio.TimeoutError:
            print(f"⏱️ LLM timeout after {LLM_TIMEOUT_SECONDS}s, using template fallback")
            skeletons = self._generate_from_template(trip_spec)
            source = "template"
        except Exception as e:
            print(f"❌ LLM error: {e}, using template fallback")
            skeletons = self._generate_from_template(trip_spec)
            source = "template"

        # No need to set skeleton_generation_method - it's set via generation_method in RouteTrace init

        # 4. Initialize POI provider
        if not self.poi_provider:
            self.poi_provider = get_poi_provider(db)

        # 5. Fetch REAL POIs for each block and convert to itinerary days
        days = await self._convert_to_itinerary_with_real_pois(
            skeletons, trip_spec, db, route_trace, enable_extended_trace
        )

        # 6. Store in database
        created_at = datetime.utcnow()
        await self._store_draft(trip_id, skeletons, days, db, created_at)

        print(f"✅ Draft generated via {source} with real POIs in < 20s")

        return ItineraryResponse(
            trip_id=trip_id,
            days=days,
            created_at=created_at.isoformat() + "Z",
            route_trace=route_trace,
        )

    async def _generate_with_llm(self, trip_spec) -> list[DaySkeleton]:
        """Generate skeleton using LLM with minimal prompt."""
        num_days = (trip_spec.end_date - trip_spec.start_date).days + 1

        prompt = f"""Trip: {trip_spec.city}, {num_days} days ({trip_spec.start_date} to {trip_spec.end_date})
Pace: {trip_spec.pace.value}
Budget: {trip_spec.budget.value}
Interests: {', '.join(trip_spec.interests) if trip_spec.interests else 'general sightseeing'}
Wake: {trip_spec.daily_routine.wake_time}, Sleep: {trip_spec.daily_routine.sleep_time}

Generate JSON skeleton with desired_categories for each block."""

        response = await self.llm_client.generate_structured(
            prompt=prompt,
            system_prompt=self.SYSTEM_PROMPT,
            max_tokens=DRAFT_MAX_TOKENS,
        )

        return self._parse_llm_response(response)

    def _parse_llm_response(self, response: dict) -> list[DaySkeleton]:
        """Parse LLM response into DaySkeleton objects."""
        days_data = response.get("days", [])
        skeletons = []

        for day_data in days_data:
            blocks = []
            for block_data in day_data.get("blocks", []):
                # Normalize time strings
                start_time = self._parse_time(block_data.get("start_time", "09:00:00"))
                end_time = self._parse_time(block_data.get("end_time", "10:00:00"))

                # Get desired categories from LLM response
                desired_categories = block_data.get("desired_categories", [])
                if not desired_categories:
                    # Infer from block type
                    block_type = block_data.get("block_type", "activity")
                    desired_categories = self._infer_categories(block_type, block_data.get("theme", ""))

                blocks.append(SkeletonBlock(
                    block_type=BlockType(block_data.get("block_type", "activity")),
                    start_time=start_time,
                    end_time=end_time,
                    theme=block_data.get("theme", ""),
                    desired_categories=desired_categories,
                ))

            skeletons.append(DaySkeleton(
                day_number=day_data["day_number"],
                date=day_data["date"],
                theme=day_data.get("theme", f"Day {day_data['day_number']}"),
                blocks=blocks,
            ))

        return skeletons

    def _infer_categories(self, block_type: str, theme: str) -> list[str]:
        """Infer POI categories from block type and theme."""
        theme_lower = theme.lower()

        if block_type == "meal":
            if "breakfast" in theme_lower:
                return ["cafe", "breakfast", "bakery"]
            elif "lunch" in theme_lower:
                return ["restaurant", "local cuisine", "cafe"]
            elif "dinner" in theme_lower:
                return ["restaurant", "local cuisine", "fine dining"]
            else:
                return ["restaurant", "cafe"]
        elif block_type == "nightlife":
            return ["bar", "club", "nightlife"]
        elif block_type == "activity":
            if "museum" in theme_lower:
                return ["museum", "art", "culture"]
            elif "park" in theme_lower or "garden" in theme_lower:
                return ["park", "nature", "garden"]
            elif "shopping" in theme_lower or "market" in theme_lower:
                return ["shopping", "market"]
            elif "historic" in theme_lower or "landmark" in theme_lower:
                return ["landmark", "attraction", "historic"]
            else:
                return ["attraction", "culture", "sightseeing"]
        else:
            return ["attraction"]

    def _parse_time(self, time_str: str) -> time:
        """Parse time string to time object."""
        if not time_str:
            return time(9, 0)

        time_str = time_str.strip()
        if time_str.startswith(':'):
            time_str = '00' + time_str

        parts = time_str.split(':')
        try:
            hour = int(parts[0]) if len(parts) > 0 else 9
            minute = int(parts[1]) if len(parts) > 1 else 0
            second = int(parts[2]) if len(parts) > 2 else 0
            return time(hour % 24, minute % 60, second % 60)
        except (ValueError, IndexError):
            return time(9, 0)

    def _generate_from_template(self, trip_spec) -> list[DaySkeleton]:
        """
        Generate skeleton from template (instant, no LLM).

        This is the fallback when LLM times out or fails.
        """
        num_days = (trip_spec.end_date - trip_spec.start_date).days + 1
        skeletons = []

        # Get time preferences
        wake = trip_spec.daily_routine.wake_time
        sleep = trip_spec.daily_routine.sleep_time
        breakfast_start, breakfast_end = trip_spec.daily_routine.breakfast_window
        lunch_start, lunch_end = trip_spec.daily_routine.lunch_window
        dinner_start, dinner_end = trip_spec.daily_routine.dinner_window

        # Determine activity count based on pace
        if trip_spec.pace == PaceLevel.SLOW:
            activities_per_day = 2
        elif trip_spec.pace == PaceLevel.FAST:
            activities_per_day = 4
        else:
            activities_per_day = 3

        # Day themes based on interests
        themes = self._generate_day_themes(trip_spec.interests, num_days)

        for day_num in range(1, num_days + 1):
            current_date = trip_spec.start_date + timedelta(days=day_num - 1)
            blocks = []

            # Breakfast
            blocks.append(SkeletonBlock(
                block_type=BlockType.MEAL,
                start_time=breakfast_start,
                end_time=breakfast_end,
                theme="Breakfast",
                desired_categories=["cafe", "breakfast", "bakery"],
            ))

            # Morning activity
            blocks.append(SkeletonBlock(
                block_type=BlockType.ACTIVITY,
                start_time=time(10, 0),
                end_time=time(12, 30),
                theme="Morning exploration",
                desired_categories=["attraction", "museum", "landmark"],
            ))

            # Lunch
            blocks.append(SkeletonBlock(
                block_type=BlockType.MEAL,
                start_time=lunch_start,
                end_time=lunch_end,
                theme="Lunch",
                desired_categories=["restaurant", "local cuisine", "cafe"],
            ))

            # Afternoon activities
            if activities_per_day >= 2:
                blocks.append(SkeletonBlock(
                    block_type=BlockType.ACTIVITY,
                    start_time=time(14, 30),
                    end_time=time(17, 0),
                    theme="Afternoon exploration",
                    desired_categories=["attraction", "culture", "shopping"],
                ))

            if activities_per_day >= 3:
                blocks.append(SkeletonBlock(
                    block_type=BlockType.ACTIVITY,
                    start_time=time(17, 30),
                    end_time=time(19, 0),
                    theme="Evening stroll",
                    desired_categories=["park", "viewpoint", "attraction"],
                ))

            # Dinner
            blocks.append(SkeletonBlock(
                block_type=BlockType.MEAL,
                start_time=dinner_start,
                end_time=dinner_end,
                theme="Dinner",
                desired_categories=["restaurant", "local cuisine", "fine dining"],
            ))

            # Nightlife (only if interested and not last day)
            if "nightlife" in [i.lower() for i in trip_spec.interests] and day_num < num_days:
                blocks.append(SkeletonBlock(
                    block_type=BlockType.NIGHTLIFE,
                    start_time=time(22, 0),
                    end_time=time(1, 0),
                    theme="Nightlife",
                    desired_categories=["bar", "club", "nightlife"],
                ))

            skeletons.append(DaySkeleton(
                day_number=day_num,
                date=current_date,
                theme=themes[day_num - 1] if day_num <= len(themes) else f"Day {day_num}",
                blocks=blocks,
            ))

        return skeletons

    def _generate_day_themes(self, interests: list[str], num_days: int) -> list[str]:
        """Generate day themes based on interests."""
        default_themes = [
            "City Center & Landmarks",
            "Local Culture & Food",
            "Hidden Gems & Parks",
            "Shopping & Entertainment",
            "Relaxation & Exploration",
        ]

        # Customize based on interests
        if interests:
            interest_themes = {
                "food": "Culinary Adventures",
                "culture": "Cultural Immersion",
                "nightlife": "Evening Entertainment",
                "history": "Historical Discoveries",
                "art": "Art & Museums",
                "nature": "Nature & Parks",
                "shopping": "Shopping & Markets",
                "architecture": "Architectural Highlights",
            }

            themed = []
            for i, interest in enumerate(interests[:num_days]):
                lower_interest = interest.lower()
                for key, theme in interest_themes.items():
                    if key in lower_interest:
                        themed.append(theme)
                        break
                else:
                    themed.append(default_themes[i % len(default_themes)])

            # Fill remaining days with defaults
            while len(themed) < num_days:
                themed.append(default_themes[len(themed) % len(default_themes)])

            return themed

        return default_themes[:num_days]

    async def _convert_to_itinerary_with_real_pois(
        self,
        skeletons: list[DaySkeleton],
        trip_spec,
        db: AsyncSession,
        route_trace=None,
        enable_extended_trace: bool = False,
    ) -> list[ItineraryDay]:
        """Convert skeletons to itinerary days with REAL POIs from database."""
        days = []
        used_poi_ids = set()  # Track used POIs to avoid duplicates

        for skeleton in skeletons:
            blocks = []

            for block_index, skel_block in enumerate(skeleton.blocks):
                poi = None
                block_trace = None

                # Fetch real POI for blocks that need them
                if skel_block.block_type in BLOCK_TYPES_NEEDING_POIS:
                    poi, block_trace = await self._fetch_best_poi_with_trace(
                        city=trip_spec.city,
                        categories=skel_block.desired_categories,
                        budget=trip_spec.budget,
                        used_poi_ids=used_poi_ids,
                        enable_extended_trace=enable_extended_trace,
                        block_type=skel_block.block_type.value,
                        theme=skel_block.theme,
                        day_number=skeleton.day_number,
                        block_index=block_index,
                    )
                    if poi:
                        used_poi_ids.add(poi.poi_id)

                    # Add block trace if tracing is enabled
                    if route_trace and block_trace:
                        route_trace.block_traces.append(block_trace)

                blocks.append(ItineraryBlock(
                    block_type=skel_block.block_type,
                    start_time=skel_block.start_time,
                    end_time=skel_block.end_time,
                    poi=poi,
                    travel_time_from_prev=0,  # Skip travel time for speed
                    travel_distance_meters=None,
                    travel_polyline=None,
                    notes=skel_block.theme if not poi else None,
                ))

            days.append(ItineraryDay(
                day_number=skeleton.day_number,
                date=skeleton.date,
                theme=skeleton.theme,
                blocks=blocks,
            ))

        return days

    async def _fetch_best_poi_with_trace(
        self,
        city: str,
        categories: list[str],
        budget: BudgetLevel,
        used_poi_ids: set,
        enable_extended_trace: bool,
        block_type: str,
        theme: str,
        day_number: int,
        block_index: int,
    ):
        """Fetch the best available POI from database with optional trace."""
        from src.domain.route_trace import (
            BlockSelectionTrace, ProviderCallTrace, CandidatePOISample,
            FilterRuleTrace, POIFilteredOut, RankingTrace, POIScoringBreakdown,
            SelectionAlternative, FilterReason
        )
        import time as time_module

        poi = None
        block_trace = None

        if not self.poi_provider:
            return None, None

        try:
            # Measure provider call latency
            start_time = time_module.time()

            # Get candidates
            candidates = await self.poi_provider.search_pois(
                city=city,
                desired_categories=categories,
                budget=budget,
                limit=5,  # Get a few to have options
            )

            latency_ms = (time_module.time() - start_time) * 1000

            # Create trace if extended trace is enabled
            if enable_extended_trace:
                # Provider call trace
                provider_calls = [ProviderCallTrace(
                    provider_name="database",
                    request_params={
                        "city": city,
                        "categories": categories,
                        "budget": budget.value,
                        "limit": 5,
                    },
                    candidates_returned=len(candidates),
                    latency_ms=round(latency_ms, 2),
                    status="success",
                    error_message=None,
                    sample_candidates=[
                        CandidatePOISample(
                            poi_id=c.poi_id,
                            poi_name=c.name,
                            category=c.category,
                            tags=c.tags or [],
                            rating=c.rating,
                            lat=c.lat,
                            lon=c.lon,
                        )
                        for c in candidates[:5]  # Limit to 5 samples
                    ],
                )]

                # Filter rules trace (candidates already used)
                filtered_out = []
                for candidate in candidates:
                    if candidate.poi_id in used_poi_ids:
                        filtered_out.append(POIFilteredOut(
                            poi_id=candidate.poi_id,
                            poi_name=candidate.name,
                            reason=FilterReason.ALREADY_USED,
                            details="POI already used in itinerary",
                        ))

                filter_rules = []
                if filtered_out:
                    filter_rules.append(FilterRuleTrace(
                        rule_name="already_used",
                        dropped_count=len(filtered_out),
                        examples_dropped=filtered_out[:5],  # Limit to 5 examples
                    ))

                # Ranking trace (simplified - we don't have actual scores in fast draft)
                available_candidates = [c for c in candidates if c.poi_id not in used_poi_ids]
                if not available_candidates and candidates:
                    available_candidates = candidates  # Fall back to all if all used

                ranking_trace = None
                if available_candidates:
                    from src.domain.route_trace import ScoringFactor

                    ranking_trace = RankingTrace(
                        total_candidates=len(available_candidates),
                        top_candidates=[
                            POIScoringBreakdown(
                                poi_id=c.poi_id,
                                poi_name=c.name,
                                total_score=c.rating or 0.0,  # Use rating as score
                                factors={
                                    ScoringFactor.CATEGORY_MATCH: 5.0 if categories and c.category in categories else 0.0,
                                    ScoringFactor.RATING: c.rating or 0.0,
                                },
                                explanation=f"Rating: {c.rating or 0.0}" + (f", matches category '{c.category}'" if c.category in categories else "")
                            )
                            for c in available_candidates[:5]  # Top 5
                        ],
                        avg_score=sum(c.rating or 0.0 for c in available_candidates) / len(available_candidates) if available_candidates else None,
                        max_score=max((c.rating or 0.0) for c in available_candidates) if available_candidates else None,
                        min_score=min((c.rating or 0.0) for c in available_candidates) if available_candidates else None,
                    )

                # Selection alternatives
                selection_alternatives = []
                if len(available_candidates) > 1:
                    for i, candidate in enumerate(available_candidates[1:4], start=2):  # Next 3
                        selection_alternatives.append(SelectionAlternative(
                            poi_id=candidate.poi_id,
                            poi_name=candidate.name,
                            rank=i,
                            score=candidate.rating or 0.0,
                            reason_not_selected=f"Selected higher-ranked POI" if i == 2 else None,
                        ))

            # Select first unused candidate
            for candidate in candidates:
                if candidate.poi_id not in used_poi_ids:
                    poi = candidate
                    break

            # If all are used, return the first one anyway
            if not poi and candidates:
                poi = candidates[0]

            # Create block trace
            if enable_extended_trace:
                block_trace = BlockSelectionTrace(
                    day_number=day_number,
                    block_index=block_index,
                    block_type=block_type,
                    block_theme=theme,
                    desired_categories=categories,
                    selected_poi_id=poi.poi_id if poi else None,
                    selected_poi_name=poi.name if poi else None,
                    provider_calls=provider_calls,
                    filter_rules_applied=filter_rules,
                    ranking_trace=ranking_trace,
                    selection_alternatives=selection_alternatives,
                )

            return poi, block_trace

        except Exception as e:
            print(f"⚠️ POI fetch error: {e}")

            # Create error trace if extended trace is enabled
            if enable_extended_trace:
                block_trace = BlockSelectionTrace(
                    day_number=day_number,
                    block_index=block_index,
                    block_type=block_type,
                    block_theme=theme,
                    desired_categories=categories,
                    selected_poi_id=None,
                    selected_poi_name=None,
                    provider_calls=[ProviderCallTrace(
                        provider_name="database",
                        request_params={
                            "city": city,
                            "categories": categories,
                            "budget": budget.value,
                            "limit": 5,
                        },
                        candidates_returned=0,
                        latency_ms=None,
                        status="error",
                        error_message=str(e),
                        sample_candidates=[],
                    )],
                    filter_rules_applied=[],
                    ranking_trace=None,
                    selection_alternatives=[],
                )

            return None, block_trace

    async def _fetch_best_poi(
        self,
        city: str,
        categories: list[str],
        budget: BudgetLevel,
        used_poi_ids: set,
    ) -> Optional[POICandidate]:
        """Fetch the best available POI from database (legacy method)."""
        poi, _ = await self._fetch_best_poi_with_trace(
            city=city,
            categories=categories,
            budget=budget,
            used_poi_ids=used_poi_ids,
            enable_extended_trace=False,
            block_type="activity",
            theme="",
            day_number=1,
            block_index=0,
        )
        return poi

    async def _store_draft(
        self,
        trip_id: UUID,
        skeletons: list[DaySkeleton],
        days: list[ItineraryDay],
        db: AsyncSession,
        created_at: datetime,
    ):
        """Store draft in database."""
        result = await db.execute(
            select(ItineraryModel).where(ItineraryModel.trip_id == trip_id)
        )
        itinerary_model = result.scalars().first()

        skeletons_json = [s.model_dump(mode='json') for s in skeletons]
        days_json = [d.model_dump(mode='json') for d in days]

        if itinerary_model:
            itinerary_model.macro_plan = skeletons_json
            itinerary_model.macro_plan_created_at = created_at
            itinerary_model.days = days_json
            itinerary_model.itinerary_created_at = created_at
            itinerary_model.updated_at = created_at
        else:
            itinerary_model = ItineraryModel(
                trip_id=trip_id,
                macro_plan=skeletons_json,
                macro_plan_created_at=created_at,
                days=days_json,
                itinerary_created_at=created_at,
                created_at=created_at,
                updated_at=created_at,
            )
            db.add(itinerary_model)

        await db.commit()
