"""Routes for the health module.

This module is the canonical template for the *vertical modular* layout: each
feature owns its own router, schemas and (later) services/models. The router
is mounted under ``/api/v1`` by the top-level ``app/api/router.py``.
"""

from fastapi import APIRouter

from app import __version__
from app.core.response import ResponseModel, success
from app.modules.health.schemas import HealthResponse

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=ResponseModel[HealthResponse], summary="Health check")
async def health_check() -> dict:
    """Return the service health status wrapped in the response envelope.

    Returns:
        ``{"code": 0, "message": "success", "data": {"status": "ok", ...}}``
    """
    data = HealthResponse(status="ok", version=__version__)
    return success(data=data)
