"""
Health check API endpoint.
"""
from fastapi import APIRouter
from src.application.health import get_health_status, HealthStatus

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthStatus)
async def health_check():
    """
    Health check endpoint.
    Returns the current status of the application.
    """
    return await get_health_status()
