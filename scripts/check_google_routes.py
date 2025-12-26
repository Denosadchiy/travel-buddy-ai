#!/usr/bin/env python3
"""
Integration check for Google Routes API.
Tests that the travel time provider can successfully get routes from Google.

Usage:
    python -m scripts.check_google_routes
    or
    make check-google-routes

Exit codes:
    0: Success - Google Routes API is working
    1: Failure - API request failed or invalid response
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.infrastructure.travel_time import (
    GoogleMapsTravelTimeProvider,
    TravelLocation,
)
from src.config import settings


async def check_google_routes():
    """Check Google Routes API connectivity."""

    # Check configuration
    if not settings.google_maps_api_key:
        print("❌ Google Routes check: FAILED")
        print("   Reason: GOOGLE_MAPS_API_KEY not configured")
        print("   Set the GOOGLE_MAPS_API_KEY environment variable")
        return False

    try:
        print(f"🔄 Testing Google Routes API connectivity...")
        print(f"   Base URL: {settings.google_routes_base_url}")
        print(f"   Test route: Eiffel Tower → Louvre (Paris)")

        # Create provider instance
        provider = GoogleMapsTravelTimeProvider(
            api_key=settings.google_maps_api_key,
            base_url=settings.google_routes_base_url,
            timeout_seconds=settings.google_routes_timeout_seconds,
        )

        # Well-known Paris landmarks with coordinates
        eiffel_tower = TravelLocation(
            lat=48.8584,
            lon=2.2945,
            address="Champ de Mars, 5 Avenue Anatole France, 75007 Paris, France"
        )

        louvre = TravelLocation(
            lat=48.8606,
            lon=2.3376,
            address="Rue de Rivoli, 75001 Paris, France"
        )

        print(f"   Origin: Eiffel Tower (48.8584, 2.2945)")
        print(f"   Destination: Louvre (48.8606, 2.3376)")

        # Request travel time and route
        result = await provider.estimate_travel(
            origin=eiffel_tower,
            destination=louvre,
            mode="DRIVE",
        )

        # Validate response
        if result.duration_minutes <= 0:
            print("❌ Google Routes check: FAILED")
            print(f"   Reason: Invalid duration ({result.duration_minutes} minutes)")
            return False

        if result.distance_meters is None or result.distance_meters <= 0:
            print("❌ Google Routes check: FAILED")
            print(f"   Reason: Invalid distance ({result.distance_meters} meters)")
            return False

        # Success
        print(f"\n✅ Google Routes check: OK")
        print(f"   Duration: {result.duration_minutes} minutes")
        print(f"   Distance: {result.distance_meters} meters ({result.distance_meters / 1000:.2f} km)")

        if result.polyline:
            print(f"   Polyline: {result.polyline[:50]}..." if len(result.polyline) > 50 else f"   Polyline: {result.polyline}")
        else:
            print(f"   Polyline: None (API may not have returned it)")

        # Sanity check - Eiffel to Louvre is about 3-5 km
        expected_min_distance = 2000  # 2 km
        expected_max_distance = 8000  # 8 km

        if not (expected_min_distance <= result.distance_meters <= expected_max_distance):
            print(f"\n⚠️  Warning: Distance seems unusual for this route")
            print(f"   Expected: {expected_min_distance}-{expected_max_distance}m")
            print(f"   Got: {result.distance_meters}m")

        return True

    except ValueError as e:
        print(f"❌ Google Routes check: FAILED")
        print(f"   Reason: Configuration error - {str(e)}")
        return False
    except Exception as e:
        print(f"❌ Google Routes check: FAILED")
        print(f"   Reason: {type(e).__name__}: {str(e)}")
        import traceback
        print(f"\n   Stack trace:")
        traceback.print_exc()
        return False


def main():
    """Main entry point."""
    success = asyncio.run(check_google_routes())
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
