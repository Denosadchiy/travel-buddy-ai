import asyncio
import time

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.api.cities import router as cities_router
from src.application.city_search import city_search_service
from src.infrastructure.database import Base, get_db
from src.infrastructure.models import CityModel


@pytest.fixture
async def cities_app():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def _override_get_db():
        async with session_factory() as session:
            yield session

    app = FastAPI()
    app.include_router(cities_router, prefix="/api")
    app.dependency_overrides[get_db] = _override_get_db

    city_search_service.clear_cache()
    async with session_factory() as session:
        session.add_all(
            [
                CityModel(
                    geoname_id=3369157,
                    name="Cape Town",
                    name_ascii="Cape Town",
                    alternate_names=["Cape Town", "Кейптаун"],
                    country_code="ZA",
                    country_name="South Africa",
                    latitude=-33.92584,
                    longitude=18.42322,
                    population=433688,
                    timezone="Africa/Johannesburg",
                ),
                CityModel(
                    geoname_id=3435910,
                    name="Buenos Aires",
                    name_ascii="Buenos Aires",
                    alternate_names=["Buenos Aires", "Буэнос-Айрес"],
                    country_code="AR",
                    country_name="Argentina",
                    latitude=-34.61315,
                    longitude=-58.37723,
                    population=2891082,
                    timezone="America/Argentina/Buenos_Aires",
                ),
                CityModel(
                    geoname_id=524901,
                    name="Moscow",
                    name_ascii="Moscow",
                    alternate_names=["Москва", "Moskva"],
                    country_code="RU",
                    country_name="Russia",
                    latitude=55.75222,
                    longitude=37.61556,
                    population=10381222,
                    timezone="Europe/Moscow",
                ),
                CityModel(
                    geoname_id=5128581,
                    name="New York City",
                    name_ascii="New York City",
                    alternate_names=["New York", "Нью-Йорк"],
                    country_code="US",
                    country_name="United States",
                    latitude=40.71427,
                    longitude=-74.00597,
                    population=8175133,
                    timezone="America/New_York",
                ),
                CityModel(
                    geoname_id=2542997,
                    name="Marrakesh",
                    name_ascii="Marrakesh",
                    alternate_names=["Marrakech", "Марракеш", "Marrakesh"],
                    country_code="MA",
                    country_name="Morocco",
                    latitude=31.63148,
                    longitude=-8.00828,
                    population=839296,
                    timezone="Africa/Casablanca",
                ),
                CityModel(
                    geoname_id=3413829,
                    name="Reykjavik",
                    name_ascii="Reykjavik",
                    alternate_names=["Reykjavík", "Рейкьявик"],
                    country_code="IS",
                    country_name="Iceland",
                    latitude=64.13548,
                    longitude=-21.89541,
                    population=118918,
                    timezone="Atlantic/Reykjavik",
                ),
                CityModel(
                    geoname_id=3687238,
                    name="Cartagena",
                    name_ascii="Cartagena",
                    alternate_names=["Cartagena", "Картахена"],
                    country_code="CO",
                    country_name="Colombia",
                    latitude=10.39972,
                    longitude=-75.51444,
                    population=914552,
                    timezone="America/Bogota",
                ),
                CityModel(
                    geoname_id=2988507,
                    name="Paris",
                    name_ascii="Paris",
                    alternate_names=["Paris", "Парис", "Париж"],
                    country_code="FR",
                    country_name="France",
                    latitude=48.85341,
                    longitude=2.3488,
                    population=2138551,
                    timezone="Europe/Paris",
                ),
                CityModel(
                    geoname_id=4717560,
                    name="Paris",
                    name_ascii="Paris",
                    alternate_names=["Paris", "Париж"],
                    country_code="US",
                    country_name="United States",
                    latitude=33.66094,
                    longitude=-95.55551,
                    population=24782,
                    timezone="America/Chicago",
                ),
                CityModel(
                    geoname_id=3393008,
                    name="Pari",
                    name_ascii="Pari",
                    alternate_names=["Pari"],
                    country_code="BR",
                    country_name="Brazil",
                    latitude=-7.22667,
                    longitude=-35.59778,
                    population=17359,
                    timezone="America/Fortaleza",
                ),
            ]
        )
        await session.commit()

    try:
        yield app
    finally:
        city_search_service.clear_cache()
        await engine.dispose()


@pytest.mark.asyncio
async def test_search_cape_returns_cape_town_first(cities_app: FastAPI):
    async with AsyncClient(transport=ASGITransport(app=cities_app), base_url="http://test") as client:
        response = await client.get("/api/cities/search", params={"query": "cape"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["results"]
    assert payload["results"][0]["name"] == "Cape Town"


@pytest.mark.asyncio
async def test_search_ru_query_returns_localized_name(cities_app: FastAPI):
    async with AsyncClient(transport=ASGITransport(app=cities_app), base_url="http://test") as client:
        response = await client.get("/api/cities/search", params={"query": "кейпт", "lang": "ru"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["results"][0]["localizedName"] == "Кейптаун"


@pytest.mark.asyncio
async def test_search_cyrillic_query_overrides_en_to_ru_localized_name(cities_app: FastAPI):
    async with AsyncClient(transport=ASGITransport(app=cities_app), base_url="http://test") as client:
        response = await client.get("/api/cities/search", params={"query": "кейпт", "lang": "en"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["results"][0]["localizedName"] == "Кейптаун"


@pytest.mark.asyncio
async def test_search_cyrillic_query_overrides_non_ru_locale_to_ru(cities_app: FastAPI):
    async with AsyncClient(transport=ASGITransport(app=cities_app), base_url="http://test") as client:
        response = await client.get("/api/cities/search", params={"query": "кейпт", "lang": "fr"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["results"][0]["localizedName"] == "Кейптаун"


@pytest.mark.asyncio
async def test_search_buenos_queries(cities_app: FastAPI):
    async with AsyncClient(transport=ASGITransport(app=cities_app), base_url="http://test") as client:
        en = await client.get("/api/cities/search", params={"query": "buenos"})
        ru = await client.get("/api/cities/search", params={"query": "буэнос", "lang": "ru"})
    assert en.status_code == 200
    assert ru.status_code == 200
    assert en.json()["results"][0]["name"] == "Buenos Aires"
    assert ru.json()["results"][0]["localizedName"] == "Буэнос-Айрес"


@pytest.mark.asyncio
async def test_search_parizh_ranks_paris_france_first(cities_app: FastAPI):
    async with AsyncClient(transport=ASGITransport(app=cities_app), base_url="http://test") as client:
        response = await client.get("/api/cities/search", params={"query": "париж", "lang": "ru"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["results"]
    assert payload["results"][0]["name"] == "Paris"
    assert payload["results"][0]["country"] == "France"
    assert payload["results"][0]["localizedName"] == "Париж"


@pytest.mark.asyncio
async def test_search_min_length_and_normalization(cities_app: FastAPI):
    async with AsyncClient(transport=ASGITransport(app=cities_app), base_url="http://test") as client:
        too_short = await client.get("/api/cities/search", params={"query": "a"})
        normalized = await client.get("/api/cities/search", params={"query": "   cape   "})
    assert too_short.status_code == 200
    assert too_short.json()["results"] == []
    assert normalized.status_code == 200
    assert normalized.json()["results"][0]["name"] == "Cape Town"


@pytest.mark.asyncio
async def test_search_nonexistent_and_injection_like_query(cities_app: FastAPI):
    async with AsyncClient(transport=ASGITransport(app=cities_app), base_url="http://test") as client:
        missing = await client.get("/api/cities/search", params={"query": "xyznonexistent"})
        strange = await client.get("/api/cities/search", params={"query": "'; DROP TABLE cities; --"})
        emoji = await client.get("/api/cities/search", params={"query": "🛫🛬"})
        arabic = await client.get("/api/cities/search", params={"query": "الرياض"})
    assert missing.status_code == 200
    assert missing.json()["results"] == []
    assert strange.status_code == 200
    assert "results" in strange.json()
    assert emoji.status_code == 200
    assert arabic.status_code == 200


@pytest.mark.asyncio
async def test_search_mo_ranks_moscow_first(cities_app: FastAPI):
    async with AsyncClient(transport=ASGITransport(app=cities_app), base_url="http://test") as client:
        response = await client.get("/api/cities/search", params={"query": "mo", "lang": "en"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["results"]
    assert payload["results"][0]["name"] == "Moscow"
    ids = [item["id"] for item in payload["results"]]
    assert len(ids) == len(set(ids))


@pytest.mark.asyncio
async def test_popular_sorted_by_population(cities_app: FastAPI):
    async with AsyncClient(transport=ASGITransport(app=cities_app), base_url="http://test") as client:
        response = await client.get("/api/cities/popular", params={"limit": 3})
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["results"]) == 3
    populations = [item["population"] for item in payload["results"]]
    assert populations == sorted(populations, reverse=True)


@pytest.mark.asyncio
async def test_log_selection_endpoint(cities_app: FastAPI):
    async with AsyncClient(transport=ASGITransport(app=cities_app), base_url="http://test") as client:
        response = await client.post(
            "/api/cities/selection",
            json={"query": "buenos", "selectedCityId": 3435910, "lang": "en"},
        )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_problem_cities_are_searchable(cities_app: FastAPI):
    async with AsyncClient(transport=ASGITransport(app=cities_app), base_url="http://test") as client:
        cases = [
            ("cape", "Cape Town"),
            ("buenos", "Buenos Aires"),
            ("marr", "Marrakesh"),
            ("рейк", "Reykjavik"),
            ("cart", "Cartagena"),
        ]
        for query, expected in cases:
            response = await client.get("/api/cities/search", params={"query": query, "lang": "ru"})
            assert response.status_code == 200
            payload = response.json()
            assert payload["results"]
            assert payload["results"][0]["name"] == expected


@pytest.mark.asyncio
async def test_long_query_two_symbols_and_one_symbol(cities_app: FastAPI):
    async with AsyncClient(transport=ASGITransport(app=cities_app), base_url="http://test") as client:
        one_symbol = await client.get("/api/cities/search", params={"query": "m"})
        two_symbols = await client.get("/api/cities/search", params={"query": "ma"})
        very_long = await client.get("/api/cities/search", params={"query": "a" * 100})

    assert one_symbol.status_code == 200
    assert one_symbol.json()["results"] == []
    assert two_symbols.status_code == 200
    assert "results" in two_symbols.json()
    assert very_long.status_code == 200
    assert "results" in very_long.json()


@pytest.mark.asyncio
async def test_concurrent_requests_100(cities_app: FastAPI):
    async with AsyncClient(transport=ASGITransport(app=cities_app), base_url="http://test") as client:
        async def do_call() -> tuple[int, dict]:
            resp = await client.get("/api/cities/search", params={"query": "cape", "lang": "en"})
            return resp.status_code, resp.json()

        results = await asyncio.gather(*[do_call() for _ in range(100)])

    assert len(results) == 100
    for status_code, payload in results:
        assert status_code == 200
        assert payload["results"]
        assert payload["results"][0]["name"] == "Cape Town"


@pytest.mark.asyncio
async def test_response_time_uncached_and_cached(cities_app: FastAPI):
    async with AsyncClient(transport=ASGITransport(app=cities_app), base_url="http://test") as client:
        started_uncached = time.perf_counter()
        first = await client.get("/api/cities/search", params={"query": "buenos", "lang": "ru"})
        uncached_elapsed = time.perf_counter() - started_uncached

        started_cached = time.perf_counter()
        second = await client.get("/api/cities/search", params={"query": "buenos", "lang": "ru"})
        cached_elapsed = time.perf_counter() - started_cached

    assert first.status_code == 200
    assert second.status_code == 200
    assert uncached_elapsed < 0.3
    assert cached_elapsed < 0.1
