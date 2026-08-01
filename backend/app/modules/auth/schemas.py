"""Pydantic schemas for the auth module.

Request schemas describe the payloads for register / login / refresh, while
the response schemas (:class:`TokenResponse`, :class:`LoginResponse`) define
what the client receives after a successful authentication flow.
"""

from pydantic import BaseModel, EmailStr, Field

from app.modules.users.schemas import UserOut


class RegisterRequest(BaseModel):
    """Payload for creating a new account."""

    email: EmailStr
    username: str = Field(min_length=2, max_length=50)
    password: str = Field(min_length=6, max_length=128)


class LoginRequest(BaseModel):
    """Payload for authenticating an existing account."""

    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    """Payload for exchanging a refresh token for a new access token."""

    refresh_token: str


class TokenResponse(BaseModel):
    """Token pair returned after a refresh operation."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class LoginResponse(TokenResponse):
    """Token pair plus the authenticated user, returned after register/login."""

    user: UserOut
