"""HTTP routes for authentication: register, login, refresh, and logout.

All auth endpoints are public except ``/auth/logout``, which requires an
authenticated user so that the caller is known (even though logout itself
is stateless on the server).
"""

from typing import Any

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.core.response import ResponseModel, success
from app.modules.auth.schemas import (
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from app.modules.auth.service import login, refresh_token, register

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=ResponseModel[LoginResponse])
async def register_endpoint(data: RegisterRequest, db: DbSession) -> dict:
    """Register a new account and return tokens plus the created user."""
    result = await register(db, data)
    return success(result)


@router.post("/login", response_model=ResponseModel[LoginResponse])
async def login_endpoint(data: LoginRequest, db: DbSession) -> dict:
    """Authenticate with email and password, returning tokens plus the user."""
    result = await login(db, data)
    return success(result)


@router.post("/refresh", response_model=ResponseModel[TokenResponse])
async def refresh_endpoint(data: RefreshRequest, db: DbSession) -> dict:
    """Exchange a refresh token for a new access token."""
    result = await refresh_token(db, data)
    return success(result)


@router.post("/logout", response_model=ResponseModel[Any])
async def logout_endpoint(current_user: CurrentUser) -> dict:
    """Stateless logout.

    The server keeps no session state, so logout is a no-op: clients simply
    discard their access and refresh tokens. The ``current_user`` dependency
    is still required so that only authenticated callers can reach this
    endpoint.
    """
    # current_user is resolved by the dependency; logout itself is stateless.
    _ = current_user
    return success(None)
