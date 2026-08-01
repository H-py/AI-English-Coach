"""Pydantic schemas for the health module."""

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Payload returned by the health check endpoint."""

    status: str = Field(default="ok", description="Overall service status.")
    version: str | None = Field(default=None, description="Application version.")
