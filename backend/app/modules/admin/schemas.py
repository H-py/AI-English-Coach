"""Pydantic schemas for the admin module.

These schemas describe the wire shapes used by admin-only endpoints for
article and user management. They extend or compose the base schemas from
the article and users modules, adding fields that are only relevant to
administrators (e.g. ``is_published`` in the article list item, or the
ability to update ``role`` and ``is_active`` on users).
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.modules.article.models import Difficulty
from app.modules.article.schemas import ArticleListItem
from app.modules.users.models import EnglishLevel, UserRole


# ---------------------------------------------------------------------------
# Article schemas
# ---------------------------------------------------------------------------

class AdminArticleListItem(ArticleListItem):
    """Article list item with admin-specific fields.

    Extends :class:`ArticleListItem` with ``is_published``, ``view_count``,
    and ``updated_at`` so administrators can see publication status and
    engagement metrics at a glance.
    """

    is_published: bool
    view_count: int
    updated_at: datetime


class AdminArticleListResponse(BaseModel):
    """Paginated list of all articles (including unpublished) for admin."""

    items: list[AdminArticleListItem]
    total: int
    page: int
    page_size: int


class AdminArticleQueryParams(BaseModel):
    """Query parameters for the admin article list.

    Supports a case-insensitive title search, difficulty filter, tag filter,
    publication-status filter, and pagination.
    """

    search: Optional[str] = None
    difficulty: Optional[Difficulty] = None
    tag: Optional[str] = None
    is_published: Optional[bool] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


# ---------------------------------------------------------------------------
# User schemas
# ---------------------------------------------------------------------------

class AdminUserOut(BaseModel):
    """Full user representation for admin views.

    Mirrors :class:`UserOut` from the users module but is defined here to
    keep the admin module self-contained and allow future divergence.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    username: str
    avatar_url: Optional[str] = None
    english_level: EnglishLevel
    role: UserRole
    is_active: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None


class AdminUserListResponse(BaseModel):
    """Paginated list of users for admin."""

    items: list[AdminUserOut]
    total: int
    page: int
    page_size: int


class AdminUserUpdate(BaseModel):
    """Partial-update payload for admin user management.

    Allows updating the username, role, active status, and English level.
    Email is intentionally excluded — changing email requires a separate
    verification flow.
    """

    username: Optional[str] = Field(default=None, min_length=2, max_length=50)
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    english_level: Optional[EnglishLevel] = None


class AdminUserQueryParams(BaseModel):
    """Query parameters for the admin user list."""

    search: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


# ---------------------------------------------------------------------------
# Dashboard / overview schemas
# ---------------------------------------------------------------------------

class AdminDashboard(BaseModel):
    """High-level statistics for the admin overview page."""

    total_users: int
    total_articles: int
    published_articles: int
    total_views: int
