"""Integration test fixtures — engine created per-test to match event loop."""
from __future__ import annotations
import uuid
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.config import settings

ZONE_ID = "04bb6ef2-3914-4920-b721-432c8502a1c8"
POI_1_LAT, POI_1_LNG = 55.7381, 37.6112
POI_2_LAT, POI_2_LNG = 55.7341, 37.6065
VOICE_ID: str = ""


@pytest_asyncio.fixture
async def db():
    """Fresh engine + session per test — guarantees same event loop."""
    global VOICE_ID
    engine = create_async_engine(settings.database_url, echo=False)
    SL = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with SL() as session:
        # Lazy init VOICE_ID
        if not VOICE_ID:
            r = await session.execute(text(
                "SELECT id FROM guide_voices WHERE style_group='academic' AND language='ru'"
            ))
            VOICE_ID = str(r.scalar())
        yield session
    await engine.dispose()
