"""
HotelDataFetcher — Phase 3 component.

Fetches full data for all finalist hotels in parallel.
Calls BookingClient.fetch_hotel_full_data() for each hotel_id,
which itself runs 5 parallel sub-requests per hotel:
  1. getHotelDetails
  2. getHotelReviewScores
  3. getHotelReviews(page=1)
  4. getHotelReviews(page=2)
  5. getHotelFacilities

Total with 25 hotels: 25 × 5 = 125 HTTP requests.
Semaphore(15) inside BookingClient limits concurrency.

Failed hotels are skipped (logged as warning) — partial results are returned.
"""
from __future__ import annotations

import asyncio
import logging
import time

from src.hotels.domain.schemas import HotelRawData, ParsedIntent
from src.hotels.infrastructure.booking_client import BookingClient

logger = logging.getLogger(__name__)


class HotelDataFetcher:
    """Fetches full data for all finalist hotels in parallel (Phase 3)."""

    async def fetch_all(
        self,
        hotel_ids: list[int],
        booking_client: BookingClient,
        arrival: str,
        departure: str,
        adults: int,
        currency: str = "EUR",
        children_age: str | None = None,
    ) -> list[HotelRawData]:
        """
        Fetch complete data for all hotel_ids in parallel.

        Args:
            hotel_ids: List of Booking.com hotel IDs.
            booking_client: Initialised BookingClient (used as context manager upstream).
            arrival: Check-in date (YYYY-MM-DD).
            departure: Check-out date (YYYY-MM-DD).
            adults: Number of adults.
            currency: Currency code (default EUR).
            children_age: Comma-separated children ages (optional).

        Returns:
            List of HotelRawData for hotels that were fetched successfully.
            Hotels that fail are skipped (not included).
        """
        if not hotel_ids:
            return []

        t0 = time.monotonic()
        logger.info("HotelDataFetcher: fetching full data for %d hotels", len(hotel_ids))

        tasks = [
            booking_client.fetch_hotel_full_data(
                hotel_id=hid,
                arrival=arrival,
                departure=departure,
                adults=adults,
                children_age=children_age,
                currency=currency,
            )
            for hid in hotel_ids
        ]

        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        successes: list[HotelRawData] = []
        for hid, result in zip(hotel_ids, raw_results):
            if isinstance(result, Exception):
                logger.warning(
                    "HotelDataFetcher: hotel %d failed — %s: %s",
                    hid, type(result).__name__, result,
                )
            elif isinstance(result, HotelRawData):
                successes.append(result)
            else:
                logger.warning("HotelDataFetcher: hotel %d returned unexpected type %s", hid, type(result))

        elapsed = time.monotonic() - t0
        logger.info(
            "HotelDataFetcher: %d/%d hotels fetched in %.1fs",
            len(successes), len(hotel_ids), elapsed,
        )
        return successes
