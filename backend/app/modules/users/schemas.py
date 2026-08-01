"""Pydantic schemas for the users module.

These schemas describe the wire shapes used by the user profile endpoints:
the shared base fields, the full read representation (``UserOut``), and the
partial update payload (``UserUpdate``). They are written in the Pydantic v2
style with ``model_config`` / ``ConfigDict``.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.modules.users.models import EnglishLevel


class UserBase(BaseModel):
    """Shared user fields used by both request and response schemas."""

    email: EmailStr
    username: str = Field(min_length=2, max_length=50)


class UserOut(UserBase):
    """Full user representation returned to clients.

    Includes the persisted identifiers and metadata. ``from_attributes`` is
    enabled so the model can be built directly from an ORM ``User`` instance
    via :meth:`UserOut.model_validate`.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    avatar_url: Optional[str] = None
    english_level: EnglishLevel
    is_active: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None


class UserUpdate(BaseModel):
    """Partial-update payload for the current user's profile.

    All fields are optional so that clients can submit only the fields they
    wish to change. The service layer uses ``exclude_unset`` to apply only
    the provided values.
    """

    avatar_url: Optional[str] = None
    english_level: Optional[EnglishLevel] = None
