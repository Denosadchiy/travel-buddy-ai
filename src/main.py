"""
Main FastAPI application entrypoint.
"""
import asyncio
from typing import Optional
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from src.config import settings
from src.infrastructure.database import init_db
from src.i18n import LocaleMiddleware, translation_queue_worker
from src.api.health import router as health_router
from src.api.trips import router as trips_router
from src.api.trip_chat import router as trip_chat_router
from src.api.macro_plan import router as macro_plan_router
from src.api.poi_plan import router as poi_plan_router
from src.api.itinerary import router as itinerary_router
from src.api.critique import router as critique_router
from src.api.fast_draft import router as fast_draft_router
from src.api.place_details import router as place_details_router
from src.api.auth import router as auth_router
from src.api.day_studio import router as day_studio_router, places_router
from src.api.saved_trips import router as saved_trips_router
from src.api.place_replacement import router as place_replacement_router
from src.api.contact import router as contact_router
from src.api.i18n import router as i18n_router
from src.api.cities import router as cities_router
from src.hotels.api.router import router as hotels_router
from src.guide.api.router import guide_router
from src.guide.api.admin_router import guide_admin_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan event handler for startup and shutdown.
    """
    # Startup
    print(f"Starting Trip Planning API on {settings.host}:{settings.port}")
    print(f"Debug mode: {settings.debug}")
    if settings.auto_init_db:
        print("Auto-init DB: creating tables if missing")
        await init_db()

    worker_task: Optional[asyncio.Task] = None
    if settings.i18n_translation_worker_enabled:
        print(
            "i18n worker: enabled "
            f"(provider={settings.i18n_translation_provider}, "
            f"poll={settings.i18n_translation_poll_interval_seconds}s)"
        )
        worker_task = asyncio.create_task(translation_queue_worker.run_forever())

    yield

    # Shutdown
    if worker_task is not None:
        await translation_queue_worker.stop()
        await worker_task
    print("Shutting down Trip Planning API")


# Create FastAPI app
app = FastAPI(
    title="Trip Planning API",
    description="Backend API for AI-powered trip planning",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware for mobile app
# Configure ALLOWED_ORIGINS environment variable in production
# Example: ALLOWED_ORIGINS="https://your-app.railway.app,https://custom-domain.com"
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Locale middleware for language detection
app.add_middleware(LocaleMiddleware)

# Register routers
app.include_router(health_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(trips_router, prefix="/api")
app.include_router(trip_chat_router, prefix="/api")
app.include_router(macro_plan_router, prefix="/api")
app.include_router(poi_plan_router, prefix="/api")
app.include_router(itinerary_router, prefix="/api")
app.include_router(critique_router, prefix="/api")
app.include_router(fast_draft_router, prefix="/api")
app.include_router(place_details_router, prefix="/api")
app.include_router(day_studio_router, prefix="/api")
app.include_router(places_router, prefix="/api")
app.include_router(saved_trips_router, prefix="/api")
app.include_router(place_replacement_router, prefix="/api")
app.include_router(contact_router, prefix="/api")
app.include_router(i18n_router, prefix="/api")
app.include_router(cities_router, prefix="/api")
app.include_router(hotels_router, prefix="/api")
app.include_router(guide_router, prefix="/api")
app.include_router(guide_admin_router, prefix="/api")

# Static file serving for guide audio (dev/staging — production uses S3/CDN)
import os
from pathlib import Path
_audio_dir = Path("data/audio")
if _audio_dir.exists():
    from fastapi.staticfiles import StaticFiles
    app.mount("/audio", StaticFiles(directory=str(_audio_dir)), name="guide-audio")


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": "Trip Planning API",
        "version": "0.1.0",
        "status": "running",
        "docs": "/docs",
    }
