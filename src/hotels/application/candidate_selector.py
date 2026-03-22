"""
CandidateSelector — Phase 2a + 2b component.

Phase 2a: fetch_wide_funnel — adaptive multi-sort hotel search.
  - Uses dest_result.nr_hotels to classify city size.
  - Small city (≤25): single page, RELAXED thresholds.
  - Medium city (26–60): 2 parallel sorts.
  - Large city (>60): 4 parallel sorts (bayesian/price/distance/popularity).
  - Adapts sort selection based on scoring_weights from intent.
  - Deduplicates by hotel_id.

Phase 2b: apply_l1_filter — pure deterministic filter + base score.
  - Filters out: sold_out, below min_review_score, price out of budget, below stars_min.
  - Scores: 0.5×review_score_norm + 0.3×price_fit + 0.2×stars_fit.
  - Returns top 25 candidates (or all if fewer).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date

from src.hotels.domain.schemas import DestinationResult, ParsedIntent
from src.hotels.infrastructure.booking_client import BookingClient

logger = logging.getLogger(__name__)

_MAX_CANDIDATES = 25
_PAGE_SIZE = 20   # Booking.com returns up to 20 per page


def _extract_hotel_fields(h: dict) -> dict:
    """Normalise the nested searchHotels response into a flat dict."""
    prop = h.get("property", {})
    price_bd = prop.get("priceBreakdown", {})
    gross = price_bd.get("grossPrice", {})

    price_total = float(gross.get("value") or 0.0)
    nights = _nights(prop.get("checkinDate", ""), prop.get("checkoutDate", ""))
    price_per_night = price_total / nights if price_total and nights else 0.0

    return {
        "hotel_id": h.get("hotel_id") or prop.get("id"),
        "name": prop.get("name", ""),
        "review_score": float(prop.get("reviewScore") or 0.0),
        "review_count": int(prop.get("reviewCount") or 0),
        "stars": int(prop.get("accuratePropertyClass") or prop.get("propertyClass") or 0),
        "price_total": price_total,
        "price_per_night": price_per_night,
        "nights": nights,
        "currency": gross.get("currency", "EUR"),
        "sold_out": bool(prop.get("soldout")),
        "latitude": prop.get("latitude"),
        "longitude": prop.get("longitude"),
        "is_preferred": bool(prop.get("isPreferred")),
        # keep original for later phases
        "_raw": h,
    }


def _nights(arrival: str, departure: str) -> int:
    """Return number of nights between two YYYY-MM-DD date strings."""
    try:
        a = date.fromisoformat(arrival)
        d = date.fromisoformat(departure)
        return max(1, (d - a).days)
    except Exception:
        return 1


class CandidateSelector:
    """
    Adaptive multi-sort hotel fetcher + deterministic L1 filter.
    """

    # ------------------------------------------------------------------
    # Phase 2a: Wide funnel fetch
    # ------------------------------------------------------------------

    async def fetch_wide_funnel(
        self,
        dest_result: DestinationResult,
        intent: ParsedIntent,
        booking_client: BookingClient,
        arrival_date: str,
        departure_date: str,
        adults: int,
        currency: str = "EUR",
        children_age: str | None = None,
    ) -> list[dict]:
        """
        Fetch a wide pool of hotel candidates using adaptive multi-sort strategy.

        City size is determined from dest_result.nr_hotels:
          ≤25:  single request, RELAXED thresholds
          ≤60:  2 parallel requests (bayesian + 1 adaptive)
          >60:  4 parallel requests (bayesian, price, distance, popularity)

        Returns deduplicated list of normalised hotel dicts.
        """
        nr_hotels = dest_result.nr_hotels or 999  # default → large city

        # Common search kwargs
        common = dict(
            dest_ids=dest_result.dest_id,
            search_type=dest_result.search_type,
            arrival_date=arrival_date,
            departure_date=departure_date,
            adults=adults,
            currency_code=currency,
            children_age=children_age,
            price_min=intent.price_min,
            price_max=intent.price_max,
            categories_filter=",".join(intent.api_filters) if intent.api_filters else None,
        )

        # Determine which sorts to use (adapt to scoring_weights)
        sorts = self._select_sorts(intent, nr_hotels)

        tasks = [
            booking_client.search_hotels(**common, sort_by=s, page_number=1)
            for s in sorts
        ]

        pages = await asyncio.gather(*tasks, return_exceptions=True)

        # Flatten and deduplicate
        seen: set[int] = set()
        result: list[dict] = []
        for page in pages:
            if isinstance(page, Exception):
                logger.warning("CandidateSelector: search page failed: %s", page)
                continue
            for h in page:
                flat = _extract_hotel_fields(h)
                hid = flat["hotel_id"]
                if hid and hid not in seen:
                    seen.add(hid)
                    result.append(flat)

        logger.info(
            "CandidateSelector.fetch_wide_funnel: nr_hotels=%d, sorts=%s → %d unique candidates",
            nr_hotels, sorts, len(result),
        )
        return result

    def _select_sorts(self, intent: ParsedIntent, nr_hotels: int) -> list[str]:
        """Return list of sort strategies based on city size and scoring weights."""
        w = intent.scoring_weights

        if nr_hotels <= 25:
            return ["bayesian_review_score"]

        if nr_hotels <= 60:
            second = "distance" if w.location > 0.25 else "price" if w.price_value > 0.25 else "popularity"
            return ["bayesian_review_score", second]

        # Large city: 4 sorts with weight-based adaptation
        sorts = ["bayesian_review_score"]
        if w.location > 0.30:
            sorts += ["distance", "distance"]          # double distance weight
        else:
            sorts.append("distance")

        if w.price_value > 0.30:
            sorts += ["price", "price"]                # double price weight
        else:
            sorts.append("price")

        if len(sorts) < 4:
            sorts.append("popularity")

        return sorts[:4]  # cap at 4

    # ------------------------------------------------------------------
    # Phase 2b: L1 fast filter
    # ------------------------------------------------------------------

    def apply_l1_filter(
        self,
        raw_hotels: list[dict],
        intent: ParsedIntent,
        relaxed: bool = False,
    ) -> list[dict]:
        """
        Deterministic L1 filter: discard obviously unsuitable hotels, score rest.

        Args:
            raw_hotels: Normalised hotel dicts from fetch_wide_funnel.
            intent: ParsedIntent with thresholds.
            relaxed: If True, use relaxed thresholds (small cities).

        Returns:
            Top _MAX_CANDIDATES by base score.
        """
        budget_factor = 1.5 if relaxed else 1.2
        score_penalty = 0.5 if relaxed else 0.0
        min_score = max(0.0, intent.min_review_score - score_penalty)

        # Budget thresholds (None = no budget constraint)
        price_max_hard = (intent.price_max * budget_factor) if intent.price_max else None
        price_min_hard = (intent.price_min * 0.5) if intent.price_min else None

        stars_min = None  # stars_min comes from HotelSearchRequest, not ParsedIntent directly

        survivors: list[dict] = []
        discarded = 0

        for h in raw_hotels:
            # Sold out → skip
            if h["sold_out"]:
                discarded += 1
                continue

            # Review score filter
            if h["review_score"] > 0 and h["review_score"] < min_score:
                discarded += 1
                continue

            # Price filter — compare price_per_night against per-night budget
            pn = h["price_per_night"]
            if pn > 0:
                if price_max_hard and pn > price_max_hard:
                    discarded += 1
                    continue
                if price_min_hard and pn < price_min_hard:
                    discarded += 1
                    continue

            # Compute base score
            h["_base_score"] = self._base_score(h, intent)
            survivors.append(h)

        survivors.sort(key=lambda x: x["_base_score"], reverse=True)
        top = survivors[:_MAX_CANDIDATES]

        logger.info(
            "CandidateSelector.apply_l1_filter: %d → %d (discarded %d, relaxed=%s)",
            len(raw_hotels), len(top), discarded, relaxed,
        )
        return top

    def _base_score(self, h: dict, intent: ParsedIntent) -> float:
        """
        Simple deterministic score: 0.5×review_norm + 0.3×price_fit + 0.2×stars_fit
        Used only for ranking within L1 filter (not the final AI score).
        """
        # Review score: normalise to [0, 1] (max possible = 10)
        review_norm = min(h["review_score"] / 10.0, 1.0) if h["review_score"] else 0.5

        # Price fit: 1.0 = at or below budget, 0.0 = 2× budget (per-night comparison)
        price_fit = 1.0
        pn = h.get("price_per_night", 0.0)
        if pn > 0 and intent.price_max:
            price_fit = max(0.0, 1.0 - (pn - intent.price_max) / intent.price_max)

        # Stars fit: prefer higher stars (0–5 scale)
        stars_fit = h["stars"] / 5.0 if h["stars"] else 0.5

        return 0.5 * review_norm + 0.3 * price_fit + 0.2 * stars_fit
