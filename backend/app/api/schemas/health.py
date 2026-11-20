"""Health-check response schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ComponentStatus(BaseModel):
    """Status of an individual subsystem."""

    name: str
    status: Literal["ok", "degraded", "unavailable"]
    detail: str | None = None


class HealthResponse(BaseModel):
    """GET /api/v1/health response body."""

    status: Literal["ok", "degraded", "unavailable"] = "ok"
    service: str
    version: str
    environment: str
    timestamp: datetime = Field(description="UTC timestamp of the health check")
    components: list[ComponentStatus] = Field(default_factory=list)
