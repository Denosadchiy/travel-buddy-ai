"""
Health check service.
"""
from datetime import datetime
from pydantic import BaseModel


class HealthStatus(BaseModel):
    """Health check response model."""
    status: str
    timestamp: datetime
    version: str = "0.1.0"


async def get_health_status() -> HealthStatus:
    """Get current health status of the application."""
    return HealthStatus(
        status="healthy",
        timestamp=datetime.utcnow(),
    )
