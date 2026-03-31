from datetime import date
from typing import Optional

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.application.trip_spec import TripSpecCollector
from src.domain.schemas import TripCreateRequest
from src.infrastructure.database import Base
from src.infrastructure.geocoding import GeocodingResult
from src.infrastructure.models import TripModel


class _StubGeocodingService:
    def __init__(self, result: Optional[GeocodingResult]):
        self._result = result
        self.calls = 0

    async def geocode_city(self, city: str):
        self.calls += 1
        return self._result


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_create_trip_uses_client_coordinates_and_geoname_id(monkeypatch: pytest.MonkeyPatch, db_session: AsyncSession):
    geocoding_stub = _StubGeocodingService(result=None)

    async def _fake_photo(_: str):
        return None

    monkeypatch.setattr("src.application.trip_spec.get_geocoding_service", lambda: geocoding_stub)
    monkeypatch.setattr("src.application.trip_spec.fetch_city_photo_reference", _fake_photo)

    collector = TripSpecCollector()
    request = TripCreateRequest(
        city="Cape Town",
        city_geoname_id=3369157,
        latitude=-33.92584,
        longitude=18.42322,
        start_date=date(2026, 4, 10),
        end_date=date(2026, 4, 14),
        num_travelers=2,
        pace="medium",
        budget="medium",
        interests=["food"],
    )

    response = await collector.create_trip(request=request, db=db_session)

    assert response.city_geoname_id == 3369157
    assert response.city_center_lat == -33.92584
    assert response.city_center_lon == 18.42322
    assert geocoding_stub.calls == 0

    saved = (await db_session.execute(select(TripModel).where(TripModel.id == response.id))).scalars().one()
    assert saved.city_geoname_id == 3369157
    assert saved.city_center_lat == -33.92584
    assert saved.city_center_lon == 18.42322


@pytest.mark.asyncio
async def test_create_trip_geocodes_when_coordinates_missing(monkeypatch: pytest.MonkeyPatch, db_session: AsyncSession):
    geocoding_stub = _StubGeocodingService(
        result=GeocodingResult(
            city="Buenos Aires",
            lat=-34.6037,
            lon=-58.3816,
            formatted_address="Buenos Aires, Argentina",
        )
    )

    async def _fake_photo(_: str):
        return None

    monkeypatch.setattr("src.application.trip_spec.get_geocoding_service", lambda: geocoding_stub)
    monkeypatch.setattr("src.application.trip_spec.fetch_city_photo_reference", _fake_photo)

    collector = TripSpecCollector()
    request = TripCreateRequest(
        city="Buenos Aires",
        city_geoname_id=3435910,
        start_date=date(2026, 5, 1),
        end_date=date(2026, 5, 5),
        num_travelers=1,
        pace="medium",
        budget="medium",
        interests=[],
    )

    response = await collector.create_trip(request=request, db=db_session)

    assert response.city_geoname_id == 3435910
    assert response.city_center_lat == -34.6037
    assert response.city_center_lon == -58.3816
    assert geocoding_stub.calls == 1


@pytest.mark.asyncio
async def test_create_trip_uses_client_hotel_coordinates(monkeypatch: pytest.MonkeyPatch, db_session: AsyncSession):
    """When hotel_lat/hotel_lon are provided by client, skip geocoding hotel name."""
    geocoding_stub = _StubGeocodingService(result=None)

    async def _fake_photo(_: str):
        return None

    monkeypatch.setattr("src.application.trip_spec.get_geocoding_service", lambda: geocoding_stub)
    monkeypatch.setattr("src.application.trip_spec.fetch_city_photo_reference", _fake_photo)

    collector = TripSpecCollector()
    request = TripCreateRequest(
        city="Prague",
        latitude=50.0755,
        longitude=14.4378,
        start_date=date(2026, 5, 10),
        end_date=date(2026, 5, 14),
        num_travelers=2,
        pace="medium",
        budget="medium",
        interests=["food"],
        hotel_location="Hotel Marais",
        hotel_lat=50.0880,
        hotel_lon=14.4208,
    )

    response = await collector.create_trip(request=request, db=db_session)

    saved = (await db_session.execute(select(TripModel).where(TripModel.id == response.id))).scalars().one()
    assert saved.hotel_lat == 50.0880
    assert saved.hotel_lon == 14.4208
    assert saved.hotel_location == "Hotel Marais"
    # Geocoding should NOT be called for hotel (only for city if needed)
    # With client lat/lon provided for city, geocoding calls = 0
    assert geocoding_stub.calls == 0


@pytest.mark.asyncio
async def test_create_trip_geocodes_hotel_when_no_coordinates(monkeypatch: pytest.MonkeyPatch, db_session: AsyncSession):
    """When hotel_lat/hotel_lon NOT provided, fall back to geocoding hotel name."""
    geocoding_stub = _StubGeocodingService(
        result=GeocodingResult(
            city="Hotel Marais, Prague",
            lat=50.0880,
            lon=14.4208,
            formatted_address="Hotel Marais, Prague, Czech Republic",
        )
    )

    async def _fake_photo(_: str):
        return None

    monkeypatch.setattr("src.application.trip_spec.get_geocoding_service", lambda: geocoding_stub)
    monkeypatch.setattr("src.application.trip_spec.fetch_city_photo_reference", _fake_photo)

    collector = TripSpecCollector()
    request = TripCreateRequest(
        city="Prague",
        latitude=50.0755,
        longitude=14.4378,
        start_date=date(2026, 5, 10),
        end_date=date(2026, 5, 14),
        num_travelers=2,
        pace="medium",
        budget="medium",
        interests=[],
        hotel_location="Hotel Marais",
        # hotel_lat and hotel_lon NOT provided
    )

    response = await collector.create_trip(request=request, db=db_session)

    saved = (await db_session.execute(select(TripModel).where(TripModel.id == response.id))).scalars().one()
    assert saved.hotel_lat == 50.0880
    assert saved.hotel_lon == 14.4208
    # Geocoding called once for hotel name
    assert geocoding_stub.calls == 1
