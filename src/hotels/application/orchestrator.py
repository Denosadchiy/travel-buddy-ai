"""
HotelSearchOrchestrator — main pipeline controller.

7-phase pipeline (≤62s deadline):
  Phase 1 (0–5s):   IntentParser + searchDestination — parallel
  Phase 2a (5–8s):  Multi-sort adaptive fetch — adaptive × searchHotels
  Phase 2b (8–9s):  Dedup + L1 deterministic filter → 25 finalists
  Phase 3 (9–31s):  Deep fetch: 25 hotels × 5 calls = 125 requests
  Phase 4 (after 3): Batch review analysis — 5 LLM batches × 5 hotels
  Phase 5 (after 4): MasterRanker LLM-driven (formula fallback)
  Phase 6 (after 5): Photo vision for final top-5 (optional, if time remains)
  Phase 7:          Format + return HotelSearchResponse
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Callable
from urllib.parse import urlencode

from src.hotels.application.candidate_selector import CandidateSelector
from src.hotels.application.data_fetcher import HotelDataFetcher
from src.hotels.application.intent_parser import IntentParser
from src.hotels.application.photo_analyzer import PhotoAnalyzer
from src.hotels.application.ranker import MasterRanker
from src.hotels.application.review_analyzer import ReviewAnalyzer
from src.hotels.application.session_store import SearchSessionStore
from src.hotels.domain.schemas import (
    DestinationResult,
    HotelExplainRequest,
    HotelExplanationResponse,
    HotelFindRequest,
    HotelProfile,
    HotelResult,
    HotelSearchRequest,
    HotelSearchResponse,
    MasterRankingResult,
    ParsedIntent,
    PhotoAnalysis,
    ReviewAnalysis,
)
from src.hotels.infrastructure.booking_client import (
    BookingClient,
    DestinationNotFoundError,
)
from src.infrastructure.llm_client import get_hotel_intent_llm_client

logger = logging.getLogger(__name__)

_CITY_TRANSLATE_TIMEOUT = 5.0


async def _translate_city_via_llm(city: str) -> str | None:
    """
    Minimal LLM call to translate a non-Latin city name to its Booking.com English equivalent.
    Used as a last resort when the destination search returns suspiciously few hotels.
    Returns None on any failure.
    """
    try:
        llm = get_hotel_intent_llm_client()
        prompt = (
            f"What is the standard English name of this city as used on Booking.com? "
            f"City: {city}\n"
            "Return ONLY the English city name, nothing else. "
            "Examples: Москва → Moscow, 東京 → Tokyo, München → Munich, Παρίσι → Paris, "
            "北京 → Beijing, 서울 → Seoul, القاهرة → Cairo"
        )
        system = "You are a city name translator. Return only the English city name, one word or phrase, nothing else."
        text = await asyncio.wait_for(
            llm.generate_text(prompt, system, max_tokens=20),
            timeout=_CITY_TRANSLATE_TIMEOUT,
        )
        translated = str(text).strip().strip('"').strip("'").split("\n")[0].strip()
        return translated if translated else None
    except Exception as exc:
        logger.debug("_translate_city_via_llm: failed for '%s': %s", city, exc)
        return None

_DEADLINE = 90.0           # hard deadline seconds (Railway + Booking.com can be slow)
_VISION_MIN_REMAINING = 15.0   # skip vision if less time left
_VISION_PHASE_TIMEOUT = 10.0   # hard cap on entire Phase 6 (all 5 hotels)

# Progress messages for SSE streaming
_PHASE_MESSAGES: dict[str, dict[int, str]] = {
    "en": {
        1: "Analyzing your preferences…",
        2: "Searching hotels…",
        3: "Collecting hotel details…",
        4: "Analyzing guest reviews…",
        5: "Finding your best matches…",
        6: "Analyzing hotel photos…",
        7: "Preparing your results…",
    },
    "ru": {
        1: "Анализируем ваши предпочтения…",
        2: "Ищем отели…",
        3: "Собираем данные об отелях…",
        4: "Анализируем отзывы гостей…",
        5: "Подбираем лучшие варианты для вас…",
        6: "Анализируем фотографии…",
        7: "Готовим результаты…",
    },
}

_PHASE_PROGRESS = {1: 0.05, 2: 0.15, 3: 0.35, 4: 0.55, 5: 0.75, 6: 0.90, 7: 0.97}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _detect_language(user_wishes: str | None) -> str:
    """Return 'ru' if user_wishes contains Cyrillic characters, else 'en'."""
    if user_wishes and any("\u0400" <= c <= "\u04FF" for c in user_wishes):
        return "ru"
    return "en"


def _score_word(score: float) -> str:
    if score >= 9.0:
        return "Exceptional"
    if score >= 8.0:
        return "Superb"
    if score >= 7.5:
        return "Very Good"
    if score >= 7.0:
        return "Good"
    if score > 0:
        return "Pleasant"
    return ""


def _build_booking_url(
    base_url: str,
    hotel_id: int,
    check_in: str,
    check_out: str,
    adults: int,
    children_ages: list[int],
    currency: str,
) -> str:
    """
    Build a Booking.com deep link with pre-filled booking parameters.

    Uses the hotel page URL from the API (e.g. https://www.booking.com/hotel/fr/name.html)
    and appends checkin, checkout, group_adults, group_children, age, currency params.
    Falls back to searchresults.html with hotel_id if base_url is empty.
    """
    if base_url and "booking.com/hotel/" in base_url:
        # Strip any existing query string
        base = base_url.split("?")[0]
    elif base_url and "booking.com" in base_url:
        base = base_url.split("?")[0]
    else:
        base = "https://www.booking.com/searchresults.html"

    params: list[tuple[str, str]] = [
        ("checkin", check_in),
        ("checkout", check_out),
        ("group_adults", str(adults)),
        ("group_children", str(len(children_ages))),
        ("selected_currency", currency),
    ]
    for age in children_ages:
        params.append(("age", str(age)))

    # If we used the fallback URL, include hotel_id so the search lands on the right property
    if "searchresults.html" in base:
        params.append(("hotel_id", str(hotel_id)))

    return f"{base}?{urlencode(params)}"


def _assemble_hotel_result(
    ranked_item,
    profile: HotelProfile,
    photo: PhotoAnalysis | None = None,
    check_in: str = "",
    check_out: str = "",
    adults: int = 2,
    children_ages: list[int] | None = None,
    currency: str = "EUR",
) -> HotelResult:
    raw = profile.raw
    ra = profile.review_analysis

    key_facilities = [
        f.title for f in raw.facilities[:20]
        if f.charge_mode in ("FREE", "UNKNOWN_CHARGE_MODE")
    ][:10]

    pets_allowed = any(f.id == 4 for f in raw.facilities)

    if ra.segment_highlights:
        review_summary = " ".join(ra.segment_highlights[:2])
    elif ra.top_pros:
        review_summary = f"Guests love: {', '.join(ra.top_pros[:2])}"
    else:
        review_summary = ""

    booking_url = _build_booking_url(
        base_url=raw.url or "",
        hotel_id=raw.hotel_id,
        check_in=check_in,
        check_out=check_out,
        adults=adults,
        children_ages=children_ages or [],
        currency=currency,
    )

    return HotelResult(
        hotel_id=raw.hotel_id,
        name=raw.name or f"Hotel {raw.hotel_id}",
        accommodation_type=raw.accommodation_type or "Hotel",
        stars=raw.stars,
        is_boutique=(
            raw.chaincode is None and raw.stars in (0, 3, 4, 5)
        ) or any(
            kw in (raw.name or "").lower()
            for kw in ("boutique", "maison", "casa", "palazzo", "villa", "manor", "château")
        ),
        url=raw.url or "",
        booking_url=booking_url,
        review_score=raw.review_score,
        review_score_word=_score_word(raw.review_score),
        review_count=raw.review_count,
        category_scores={
            k: v for k, v in {
                "cleanliness": raw.review_scores.cleanliness,
                "comfort": raw.review_scores.comfort,
                "location": raw.review_scores.location,
                "staff": raw.review_scores.staff,
                "value": raw.review_scores.value,
                "wifi": raw.review_scores.wifi,
            }.items() if v is not None
        },
        segment_scores=raw.review_scores.by_segment,
        price_per_night=raw.price_per_night,
        total_price=raw.total_price,
        currency=raw.currency,
        address=raw.address,
        district=raw.district,
        distance_to_center_km=raw.distance_to_cc,
        latitude=raw.latitude or 0.0,
        longitude=raw.longitude or 0.0,
        # Передаём все фото в том же порядке, что вернул Booking.com.
        # Клиент (iOS) показывает их как есть — без дополнительного ранжирования.
        photos=raw.photo_urls,
        key_facilities=key_facilities,
        breakfast_included=raw.breakfast_included,
        pets_allowed=pets_allowed,
        free_cancellation=raw.free_cancellation,
        checkin_from=raw.checkin_from,
        checkout_until=raw.checkout_until,
        ai_score=ranked_item.ai_score,
        ai_match_reason=ranked_item.ai_match_reason,
        ai_pros=ra.top_pros,
        ai_cons=ra.top_cons,
        ai_hidden_issues=ra.hidden_issues,
        review_summary=review_summary,
        interior_style=photo.interior_style if photo else None,
        view_quality=photo.view_quality if photo else None,
        visual_cleanliness=photo.cleanliness_visual if photo else None,
    )


def _filters_summary(
    intent: ParsedIntent,
    dest: DestinationResult,
    search_mode: str = "full",
    effective_intent: ParsedIntent | None = None,
) -> str:
    parts: list[str] = []

    if intent.price_max:
        eff_price = effective_intent.price_max if effective_intent else None
        if eff_price and abs(eff_price - intent.price_max) > 1:
            parts.append(f"Budget ≤{intent.price_max:.0f} (expanded to ≤{eff_price:.0f})")
        else:
            parts.append(f"Budget ≤{intent.price_max:.0f}/night")

    if intent.min_review_score > 0:
        parts.append(f"Score ≥{intent.min_review_score:.0f}")

    if intent.api_filters:
        parts.append(f"{len(intent.api_filters)} amenity filters")

    if search_mode == "basic":
        parts.append("⚠ filters relaxed — limited availability")
    elif search_mode == "user_only":
        parts.append("(AI filters relaxed)")
    elif search_mode == "relax_cancel":
        parts.append("(cancellation filter relaxed)")

    parts.append(f"{dest.name} ({dest.nr_hotels} hotels available)")
    return " · ".join(parts)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class HotelSearchOrchestrator:
    """
    Main pipeline controller for AI hotel search.
    Single instance shared across all requests (stateful via session store).
    """

    def __init__(self) -> None:
        self._intent_parser = IntentParser()
        self._selector = CandidateSelector()
        self._fetcher = HotelDataFetcher()
        self._analyzer = ReviewAnalyzer()
        self._ranker = MasterRanker()
        self._photo = PhotoAnalyzer()
        self._sessions = SearchSessionStore()

    # ──────────────────────────────────────────────────────────────────
    # search() — main 7-phase pipeline
    # ──────────────────────────────────────────────────────────────────

    async def search(
        self,
        request: HotelSearchRequest,
        progress_callback: Callable | None = None,
    ) -> HotelSearchResponse:
        """Enforce hard deadline then delegate to pipeline."""
        try:
            return await asyncio.wait_for(
                self._run_pipeline(request, progress_callback),
                timeout=_DEADLINE,
            )
        except asyncio.TimeoutError:
            logger.error("Hotel search pipeline exceeded %ss deadline", _DEADLINE)
            raise

    async def _run_pipeline(
        self,
        request: HotelSearchRequest,
        progress_callback: Callable | None = None,
    ) -> HotelSearchResponse:
        """Full 7-phase hotel search pipeline (≤62s deadline)."""
        t0 = time.monotonic()
        timings: dict[str, float] = {}
        lang = _detect_language(request.user_wishes)

        def elapsed() -> float:
            return time.monotonic() - t0

        def remaining() -> float:
            return _DEADLINE - elapsed()

        async def _report(phase: int, city_name: str = "") -> None:
            if not progress_callback:
                return
            msg = _PHASE_MESSAGES[lang].get(phase, "")
            if phase == 2 and city_name:
                if lang == "ru":
                    msg = f"Ищем отели в {city_name}…"
                else:
                    msg = f"Searching hotels in {city_name}…"
            pct = _PHASE_PROGRESS.get(phase, 0.5)
            await progress_callback(phase, msg, pct)

        children_age_str = (
            ",".join(str(a) for a in request.children_ages)
            if request.children_ages else None
        )

        # ── Phase 1: Intent + Destination (parallel) ─────────────────
        await _report(1)
        p1 = elapsed()
        intent, dest = await asyncio.gather(
            self._intent_parser.parse(request),
            self._resolve_destination(request.city),
        )

        # City normalization retry: if dest has suspiciously few hotels (< 10),
        # try IntentParser's city_for_booking as additional candidate.
        # Note: _resolve_destination already handles LLM translation for non-Latin scripts,
        # so we only need the IntentParser fallback here.
        if dest.nr_hotels < 10:
            if intent.city_for_booking and intent.city_for_booking.lower() != request.city.lower():
                logger.info(
                    "Phase 1: dest.nr_hotels=%d for '%s', retrying with IntentParser suggestion '%s'",
                    dest.nr_hotels, request.city, intent.city_for_booking,
                )
                try:
                    dest2 = await self._resolve_destination(intent.city_for_booking)
                    if dest2.nr_hotels > dest.nr_hotels:
                        logger.info(
                            "Phase 1: city normalization improved '%s'→'%s' (%d→%d hotels)",
                            request.city, intent.city_for_booking, dest.nr_hotels, dest2.nr_hotels,
                        )
                        dest = dest2
                except Exception as exc:
                    logger.warning("Phase 1: city normalization retry '%s' failed: %s", intent.city_for_booking, exc)

        timings["phase1"] = elapsed() - p1
        logger.info(
            "Phase 1: %.1fs | segment=%s filters=%d city='%s' weights_sum=%.2f",
            timings["phase1"], intent.user_segment, len(intent.api_filters),
            dest.name, sum(intent.scoring_weights.model_dump().values()),
        )

        # ── Phases 2–3: shared BookingClient ─────────────────────────
        await _report(2, city_name=dest.name)
        async with BookingClient() as booking_client:

            # Phase 2a + 2b: wide funnel + L1 filter WITH cascade fallback
            p2a = elapsed()
            original_intent = intent  # preserve for applied_filters_summary transparency
            raw_hotels, finalists, search_mode, effective_intent = await self._fetch_candidates_with_cascade(
                booking_client=booking_client,
                dest=dest,
                intent=intent,
                request=request,
                children_age_str=children_age_str,
            )
            # Use effective_intent (may be relaxed) for downstream phases
            intent = effective_intent
            timings["phase2"] = elapsed() - p2a
            logger.info(
                "Phase 2: %.1fs | mode=%s wide=%d → finalists=%d",
                timings["phase2"], search_mode, len(raw_hotels), len(finalists),
            )

            if not finalists:
                logger.warning("Phase 2: 0 finalists after all cascade attempts")
                return self._empty_response(request)

            # Phase 3: deep data fetch
            await _report(3)
            p3 = elapsed()
            hotel_ids = [h["hotel_id"] for h in finalists]
            raw_data = await self._fetcher.fetch_all(
                hotel_ids=hotel_ids,
                booking_client=booking_client,
                arrival=request.check_in,
                departure=request.check_out,
                adults=request.adults,
                currency=request.currency,
                children_age=children_age_str,
            )
            timings["phase3"] = elapsed() - p3
            logger.info("Phase 3: %.1fs | %d/%d fetched", timings["phase3"], len(raw_data), len(hotel_ids))

        # ── Phase 4: review analysis ──────────────────────────────────
        await _report(4)
        p4 = elapsed()
        review_map = await self._analyzer.analyze_batch(raw_data, user_segment=intent.user_segment)
        timings["phase4"] = elapsed() - p4
        logger.info("Phase 4: %.1fs | %d analyzed", timings["phase4"], len(review_map))

        profiles = [
            HotelProfile(
                raw=rd,
                review_analysis=review_map.get(rd.hotel_id, ReviewAnalysis(hotel_id=rd.hotel_id)),
            )
            for rd in raw_data
        ]

        # ── Phase 5: master ranking ───────────────────────────────────
        await _report(5)
        p5 = elapsed()
        ranking = await self._ranker.rank(profiles, intent)
        timings["phase5"] = elapsed() - p5
        logger.info("Phase 5: %.1fs | top %d ranked", timings["phase5"], len(ranking.ranked_top10))

        # ── Phase 6: photo vision (conditional) ──────────────────────
        photo_results: dict[int, PhotoAnalysis] = {}
        if remaining() >= _VISION_MIN_REMAINING:
            await _report(6)
            p6 = elapsed()
            top5_ids = [r.hotel_id for r in ranking.ranked_top10[:5]]
            # Hard cap: if photo vision takes longer than _VISION_PHASE_TIMEOUT,
            # skip it and continue to Phase 7 — results are still complete without photos.
            try:
                async with BookingClient() as bc6:
                    photo_results = await asyncio.wait_for(
                        self._photo.analyze_top_hotels(top5_ids, bc6, intent),
                        timeout=_VISION_PHASE_TIMEOUT,
                    )
            except asyncio.TimeoutError:
                logger.warning("Phase 6: timed out after %.1fs — skipping photo vision", _VISION_PHASE_TIMEOUT)
                photo_results = {}
            timings["phase6"] = elapsed() - p6
            logger.info("Phase 6: %.1fs | %d photos", timings["phase6"], len(photo_results))
        else:
            logger.info("Phase 6: skipped (%.1fs remaining)", remaining())

        # ── Phase 7: assemble response ────────────────────────────────
        await _report(7)
        profile_map = {p.hotel_id: p for p in profiles}
        hotels_out: list[HotelResult] = []
        for ranked_item in ranking.ranked_top10:
            profile = profile_map.get(ranked_item.hotel_id)
            if not profile:
                continue
            hotels_out.append(
                _assemble_hotel_result(
                    ranked_item,
                    profile,
                    photo_results.get(ranked_item.hotel_id),
                    check_in=request.check_in,
                    check_out=request.check_out,
                    adults=request.adults,
                    children_ages=request.children_ages,
                    currency=request.currency,
                )
            )

        # Save session for pagination / explain
        fetch_params = {
            "check_in": request.check_in,
            "check_out": request.check_out,
            "adults": request.adults,
            "currency": request.currency,
            "children_age": children_age_str,
            "children_ages": request.children_ages,
            "dest_id": dest.dest_id,
            "search_type": dest.search_type,
        }
        session_id = self._sessions.create_session(
            intent=intent,
            all_candidates=raw_hotels,
            fetch_params=fetch_params,
        )
        self._sessions.update_session(
            session_id,
            analyzed_hotels=[rd.hotel_id for rd in raw_data],
            ranked_results=ranking,
            offset=len(finalists),
        )

        total = elapsed()
        timing_str = " | ".join(f"Ph{k[-1]}: {v:.1f}s" for k, v in timings.items())
        logger.info(
            "[HOTEL_SEARCH] city=%s adults=%d phases=%d total_time=%.1fs "
            "candidates=%d finalists=%d top10=%d vision=%s",
            request.city, request.adults, len(timings), total,
            len(raw_hotels), len(finalists), len(hotels_out),
            "done" if photo_results else "skipped",
        )
        logger.info("%s | Total: %.1fs", timing_str, total)

        return HotelSearchResponse(
            hotels=hotels_out,
            notable_excluded=ranking.notable_excluded,
            city=request.city,
            check_in=request.check_in,
            check_out=request.check_out,
            total_found=dest.nr_hotels or len(raw_hotels),
            session_id=session_id,
            applied_filters_summary=_filters_summary(
                original_intent, dest,
                search_mode=search_mode,
                effective_intent=intent,  # may be relaxed after cascade
            ),
            has_more=len(raw_hotels) > len(finalists),
        )

    # ──────────────────────────────────────────────────────────────────
    # search_more() — pagination
    # ──────────────────────────────────────────────────────────────────

    async def search_more(self, session_id: str) -> HotelSearchResponse:
        """Return next batch of hotels from cached session."""
        session = self._sessions.get_session(session_id)
        if session is None:
            raise ValueError(f"Session '{session_id}' not found or expired")

        intent: ParsedIntent = session["intent"]
        all_candidates: list[dict] = session["all_candidates"]
        analyzed_ids: set[int] = set(session.get("analyzed_hotels", []))
        fetch_params: dict = session.get("fetch_params", {})

        # Parse children_ages for booking URL
        children_age_str = fetch_params.get("children_age") or ""
        children_ages_list = fetch_params.get("children_ages") or [
            int(a) for a in children_age_str.split(",") if a.strip()
        ]

        remaining_candidates = [
            h for h in all_candidates if h["hotel_id"] not in analyzed_ids
        ]

        if not remaining_candidates:
            return HotelSearchResponse(
                hotels=[],
                city="",
                check_in=fetch_params.get("check_in", ""),
                check_out=fetch_params.get("check_out", ""),
                total_found=len(all_candidates),
                session_id=session_id,
                applied_filters_summary="No more hotels available",
                has_more=False,
            )

        next_batch = remaining_candidates[:15]
        next_ids = [h["hotel_id"] for h in next_batch]

        async with BookingClient() as booking_client:
            raw_data = await self._fetcher.fetch_all(
                hotel_ids=next_ids,
                booking_client=booking_client,
                arrival=fetch_params.get("check_in", ""),
                departure=fetch_params.get("check_out", ""),
                adults=fetch_params.get("adults", 2),
                currency=fetch_params.get("currency", "EUR"),
                children_age=fetch_params.get("children_age"),
            )

        review_map = await self._analyzer.analyze_batch(raw_data, user_segment=intent.user_segment)
        profiles = [
            HotelProfile(
                raw=rd,
                review_analysis=review_map.get(rd.hotel_id, ReviewAnalysis(hotel_id=rd.hotel_id)),
            )
            for rd in raw_data
        ]
        ranking = await self._ranker.rank(profiles, intent)

        self._sessions.update_session(
            session_id,
            analyzed_hotels=list(analyzed_ids) + next_ids,
        )

        profile_map = {p.hotel_id: p for p in profiles}
        hotels_out = [
            _assemble_hotel_result(
                r,
                profile_map[r.hotel_id],
                check_in=fetch_params.get("check_in", ""),
                check_out=fetch_params.get("check_out", ""),
                adults=fetch_params.get("adults", 2),
                children_ages=children_ages_list,
                currency=fetch_params.get("currency", "EUR"),
            )
            for r in ranking.ranked_top10
            if r.hotel_id in profile_map
        ]

        return HotelSearchResponse(
            hotels=hotels_out,
            notable_excluded=ranking.notable_excluded,
            city="",
            check_in=fetch_params.get("check_in", ""),
            check_out=fetch_params.get("check_out", ""),
            total_found=len(all_candidates),
            session_id=session_id,
            applied_filters_summary="",
            has_more=len(remaining_candidates) > len(next_batch),
        )

    # ──────────────────────────────────────────────────────────────────
    # find_hotel() — direct hotel search by name
    # ──────────────────────────────────────────────────────────────────

    async def find_hotel(self, request: HotelFindRequest) -> HotelSearchResponse:
        """Find a specific hotel by name with full AI analysis."""
        check_in = request.check_in or "2026-06-01"
        check_out = request.check_out or "2026-06-04"
        hotel_ids: list[int] = []

        async with BookingClient() as booking_client:
            # Try direct destination search by hotel name
            try:
                dest = await booking_client.search_destination(request.hotel_name)
                if dest.search_type in ("hotel", "landmark"):
                    raw_id = dest.dest_id.lstrip("-")
                    if raw_id.isdigit():
                        hotel_ids = [int(dest.dest_id)]
            except Exception:
                pass

            # Fallback: search by city, fuzzy match by name
            if not hotel_ids and request.city:
                try:
                    city_dest = await booking_client.search_destination(request.city)
                    hotels_list = await booking_client.search_hotels(
                        dest_ids=city_dest.dest_id,
                        search_type=city_dest.search_type,
                        arrival_date=check_in,
                        departure_date=check_out,
                        adults=request.adults,
                        currency_code=request.currency,
                        sort_by="bayesian_review_score",
                        page_number=1,
                    )
                    name_lower = request.hotel_name.lower()
                    for h in hotels_list:
                        prop = h.get("property", {})
                        h_name = (prop.get("name") or "").lower()
                        hid = h.get("hotel_id") or prop.get("id")
                        if hid and (name_lower in h_name or h_name in name_lower):
                            hotel_ids = [int(hid)]
                            break
                    # Last resort: take first result
                    if not hotel_ids and hotels_list:
                        h = hotels_list[0]
                        prop = h.get("property", {})
                        hid = h.get("hotel_id") or prop.get("id")
                        if hid:
                            hotel_ids = [int(hid)]
                except Exception as exc:
                    logger.warning("find_hotel: city search failed: %s", exc)

            if not hotel_ids:
                return self._empty_response_custom(
                    city=request.city or "",
                    check_in=check_in,
                    check_out=check_out,
                    note="Hotel not found",
                )

            raw_data = await self._fetcher.fetch_all(
                hotel_ids=hotel_ids,
                booking_client=booking_client,
                arrival=check_in,
                departure=check_out,
                adults=request.adults,
                currency=request.currency,
            )

        if not raw_data:
            return self._empty_response_custom(
                city=request.city or "",
                check_in=check_in,
                check_out=check_out,
                note="Hotel data unavailable",
            )

        intent = ParsedIntent()
        review_map = await self._analyzer.analyze_batch(raw_data, user_segment="couple")
        profiles = [
            HotelProfile(
                raw=rd,
                review_analysis=review_map.get(rd.hotel_id, ReviewAnalysis(hotel_id=rd.hotel_id)),
            )
            for rd in raw_data
        ]
        ranking = await self._ranker.rank(profiles, intent)
        profile_map = {p.hotel_id: p for p in profiles}

        hotels_out = [
            _assemble_hotel_result(
                r,
                profile_map[r.hotel_id],
                check_in=check_in,
                check_out=check_out,
                adults=request.adults,
                children_ages=[],
                currency=request.currency,
            )
            for r in ranking.ranked_top10
            if r.hotel_id in profile_map
        ]

        session_id = self._sessions.create_session(
            intent=intent,
            all_candidates=[{"hotel_id": hid} for hid in hotel_ids],
        )

        return HotelSearchResponse(
            hotels=hotels_out,
            city=request.city or "",
            check_in=check_in,
            check_out=check_out,
            total_found=len(hotel_ids),
            session_id=session_id,
            applied_filters_summary=f"Direct lookup: {request.hotel_name}",
            has_more=False,
        )

    # ──────────────────────────────────────────────────────────────────
    # explain_hotel() — why not in top-10
    # ──────────────────────────────────────────────────────────────────

    async def explain_hotel(self, request: HotelExplainRequest) -> HotelExplanationResponse:
        """Explain why a hotel didn't make the top-10."""
        session = self._sessions.get_session(request.session_id)
        if session is None:
            return HotelExplanationResponse(
                hotel_name=request.hotel_name,
                found_in_candidates=False,
                reason="Session not found or expired. Please start a new search.",
            )

        all_candidates: list[dict] = session.get("all_candidates", [])
        ranking: MasterRankingResult | None = session.get("ranked_results")

        # Fuzzy name match
        name_lower = request.hotel_name.lower()
        matched_id: int | None = None
        matched_name: str = request.hotel_name

        for c in all_candidates:
            c_name = (c.get("name") or "").lower()
            if c_name and (name_lower in c_name or c_name in name_lower):
                matched_id = c["hotel_id"]
                matched_name = c.get("name", request.hotel_name)
                break

        if matched_id is None:
            return HotelExplanationResponse(
                hotel_name=request.hotel_name,
                found_in_candidates=False,
                reason=(
                    "This hotel was not in the candidate pool (~80 hotels). "
                    "It may have been filtered by price, review score, or availability."
                ),
            )

        # Check MasterRanker's filtered_out reasons
        if ranking and hasattr(ranking, "filtered_out"):
            reason = ranking.filtered_out.get(str(matched_id))
            if reason:
                return HotelExplanationResponse(
                    hotel_id=matched_id,
                    hotel_name=matched_name,
                    found_in_candidates=True,
                    reason=reason,
                )

        return HotelExplanationResponse(
            hotel_id=matched_id,
            hotel_name=matched_name,
            found_in_candidates=True,
            reason=(
                "The hotel was analyzed but did not score high enough for the top-10. "
                "It may have lower reviews, a higher price, or fewer matching facilities "
                "compared to the selected hotels."
            ),
        )

    # ──────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────

    async def _resolve_destination(self, city: str) -> DestinationResult:
        """
        Resolve city name to Booking.com destination.

        Strategy:
          1. If city contains non-Latin chars (Cyrillic, CJK, Arabic, etc.),
             translate to English FIRST via LLM — Booking.com API works best
             with English/Latin city names. Use original as fallback.
          2. Try the best candidate with Booking API.
          3. Unicode normalization (strip accents) as last resort for Latin scripts.
        """
        import unicodedata

        has_non_latin = any(ord(c) > 127 for c in city)

        # Pre-translate non-Latin city names to English for Booking.com API
        translated_city: str | None = None
        if has_non_latin:
            translated_city = await _translate_city_via_llm(city)
            if translated_city:
                logger.info(
                    "_resolve_destination: pre-translated '%s' → '%s'",
                    city, translated_city,
                )

        # Build ordered list of candidate names to try
        candidates: list[str] = []
        if translated_city and translated_city.lower() != city.lower():
            candidates.append(translated_city)  # English name first (most reliable)
        candidates.append(city)                  # original name as fallback

        async with BookingClient() as bc:
            best_result: DestinationResult | None = None

            for candidate in candidates:
                try:
                    result = await bc.search_destination(candidate)
                    if result.nr_hotels > 0:
                        # Sanity check: if we translated, prefer translated result
                        # If original also returned results, pick one with more hotels
                        if best_result is None or result.nr_hotels > best_result.nr_hotels:
                            best_result = result
                        # If this is the translated (English) name and it found hotels, use it
                        if candidate == translated_city:
                            logger.info(
                                "_resolve_destination: using translated '%s' → dest='%s' (%d hotels)",
                                city, result.name, result.nr_hotels,
                            )
                            return result
                except Exception as exc:
                    logger.debug(
                        "_resolve_destination: candidate '%s' failed: %s",
                        candidate, exc,
                    )

            # If best_result found from original name, return it
            if best_result is not None and best_result.nr_hotels > 0:
                return best_result

            # Attempt: Unicode normalization (handles accented Latin chars like München)
            try:
                nfkd = unicodedata.normalize("NFKD", city)
                ascii_city = nfkd.encode("ascii", "ignore").decode("ascii").strip()
                if ascii_city and ascii_city.lower() != city.lower():
                    result2 = await bc.search_destination(ascii_city)
                    if result2.nr_hotels > 0:
                        logger.info(
                            "_resolve_destination: unicode fallback '%s' → '%s' (%d hotels)",
                            city, ascii_city, result2.nr_hotels,
                        )
                        return result2
            except Exception:
                pass

            # Return whatever we got (even 0 hotels — cascade will handle it)
            if best_result is not None:
                return best_result

            # All failed — re-raise
            from src.hotels.infrastructure.booking_client import DestinationNotFoundError
            raise DestinationNotFoundError(f"No destination found for '{city}'")

    def _empty_response(self, request: HotelSearchRequest) -> HotelSearchResponse:
        return HotelSearchResponse(
            hotels=[],
            city=request.city,
            check_in=request.check_in,
            check_out=request.check_out,
            total_found=0,
            session_id="",
            applied_filters_summary="No hotels found matching your criteria",
            has_more=False,
        )

    async def _fetch_candidates_with_cascade(
        self,
        booking_client: BookingClient,
        dest: DestinationResult,
        intent: ParsedIntent,
        request: HotelSearchRequest,
        children_age_str: str | None,
    ) -> tuple[list[dict], list[dict], str, ParsedIntent]:
        """
        4-round cascade to prevent 0-result responses due to over-filtering.

        Round 1 (full): all api_filters + price/score as-is
        Round 2 (relax_cancel): drop free_cancellation from filters (if present)
        Round 3 (user_only): keep only user_api_filters (drop LLM-generated)
        Round 4 (basic): no api_filters, relaxed budget×1.3, min_score-1.0

        Returns (raw_hotels, finalists, search_mode, effective_intent).
        """
        rounds = [
            ("full", intent.api_filters, intent, False),
        ]

        # Round 2: drop free_cancellation (already removed from hard filters but may still slip in)
        r2_filters = [f for f in intent.api_filters if "free_cancellation" not in f.lower()]
        if r2_filters != intent.api_filters:
            r2_intent = intent.model_copy(update={"api_filters": r2_filters})
            rounds.append(("relax_cancel", r2_filters, r2_intent, False))

        # Round 3: user amenities only (drop LLM-generated filters)
        if intent.user_api_filters != intent.api_filters:
            r3_intent = intent.model_copy(update={"api_filters": intent.user_api_filters})
            rounds.append(("user_only", intent.user_api_filters, r3_intent, False))

        # Round 4: no filters, relaxed thresholds
        relaxed_score = max(6.0, intent.min_review_score - 1.0)
        relaxed_price_max = (intent.price_max * 1.3) if intent.price_max else None
        r4_intent = intent.model_copy(update={
            "api_filters": [],
            "min_review_score": relaxed_score,
            "price_max": relaxed_price_max,
        })
        rounds.append(("basic", [], r4_intent, True))

        for search_mode, filters, effective_intent, relaxed in rounds:
            try:
                raw_hotels = await self._selector.fetch_wide_funnel(
                    dest_result=dest,
                    intent=effective_intent,
                    booking_client=booking_client,
                    arrival_date=request.check_in,
                    departure_date=request.check_out,
                    adults=request.adults,
                    currency=request.currency,
                    children_age=children_age_str,
                )
            except Exception as exc:
                logger.warning("Cascade round '%s' fetch failed: %s", search_mode, exc)
                continue

            finalists = self._selector.apply_l1_filter(raw_hotels, effective_intent, relaxed=relaxed)

            if len(finalists) >= 5:
                if search_mode != "full":
                    logger.info(
                        "Cascade: round '%s' succeeded → %d finalists (was 0 in earlier rounds)",
                        search_mode, len(finalists),
                    )
                return raw_hotels, finalists, search_mode, effective_intent

            logger.info(
                "Cascade round '%s': only %d finalists, trying next round",
                search_mode, len(finalists),
            )

        # All rounds exhausted — return whatever the last round gave us
        return raw_hotels, finalists, search_mode, effective_intent  # type: ignore[return-value]

    def _empty_response_custom(
        self, city: str, check_in: str, check_out: str, note: str
    ) -> HotelSearchResponse:
        return HotelSearchResponse(
            hotels=[],
            city=city,
            check_in=check_in,
            check_out=check_out,
            total_found=0,
            session_id="",
            applied_filters_summary=note,
            has_more=False,
        )
