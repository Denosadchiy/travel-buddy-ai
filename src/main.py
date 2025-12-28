"""
Main FastAPI application entrypoint.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from src.config import settings
from src.api.health import router as health_router
from src.api.trips import router as trips_router
from src.api.trip_chat import router as trip_chat_router
from src.api.macro_plan import router as macro_plan_router
from src.api.poi_plan import router as poi_plan_router
from src.api.itinerary import router as itinerary_router
from src.api.critique import router as critique_router
from src.api.fast_draft import router as fast_draft_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan event handler for startup and shutdown.
    """
    # Startup
    print(f"Starting Trip Planning API on {settings.host}:{settings.port}")
    print(f"Debug mode: {settings.debug}")

    yield

    # Shutdown
    print("Shutting down Trip Planning API")


# Create FastAPI app
app = FastAPI(
    title="Trip Planning API",
    description="Backend API for AI-powered trip planning",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware for mobile app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(health_router, prefix="/api")
app.include_router(trips_router, prefix="/api")
app.include_router(trip_chat_router, prefix="/api")
app.include_router(macro_plan_router, prefix="/api")
app.include_router(poi_plan_router, prefix="/api")
app.include_router(itinerary_router, prefix="/api")
app.include_router(critique_router, prefix="/api")
app.include_router(fast_draft_router, prefix="/api")


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": "Trip Planning API",
        "version": "0.1.0",
        "status": "running",
        "docs": "/docs",
    }
