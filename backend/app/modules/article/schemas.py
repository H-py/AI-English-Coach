"""Pydantic schemas for the article module.

These schemas describe the wire shapes used by the article endpoints: the
shared base fields, the create/update payloads, the full read representation
(``ArticleOut``), a lightweight list item (``ArticleListItem``), the
paginated list response, and the query-parameter model. They are written in
the Pydantic v2 style with ``model_config`` / ``ConfigDict``.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.modules.article.models import Difficulty


class ArticleBase(BaseModel):
    """Shared article fields used by both request and response schemas."""

    title: str = Field(min_length=1, max_length=500)
    content: str
    difficulty: Difficulty = Difficulty.b1
    source: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    cover_url: Optional[str] = None


class ArticleCreate(ArticleBase):
    """Payload for creating a new article.

    Extends :class:`ArticleBase` with optional fields that the client may
    provide. ``word_count`` is intentionally absent — the service layer
    auto-calculates it from ``content``.
    """

    summary: Optional[str] = None
    reading_time: Optional[int] = None


class ArticleUpdate(BaseModel):
    """Partial-update payload for an existing article.

    All fields are optional so that clients can submit only the fields they
    wish to change. The service layer uses ``exclude_unset`` to apply only
    the provided values. If ``content`` is updated, ``word_count`` is
    recalculated automatically.
    """

    title: Optional[str] = Field(default=None, min_length=1, max_length=500)
    content: Optional[str] = None
    summary: Optional[str] = None
    source: Optional[str] = None
    difficulty: Optional[Difficulty] = None
    reading_time: Optional[int] = None
    cover_url: Optional[str] = None
    tags: Optional[list[str]] = None
    is_published: Optional[bool] = None


class ArticleOut(BaseModel):
    """Full article representation returned to clients.

    Includes all persisted fields. ``from_attributes`` is enabled so the
    model can be built directly from an ORM ``Article`` instance via
    :meth:`ArticleOut.model_validate`.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    content: str
    summary: Optional[str] = None
    source: Optional[str] = None
    difficulty: Difficulty
    word_count: int
    reading_time: Optional[int] = None
    cover_url: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    is_published: bool
    view_count: int
    created_at: datetime
    updated_at: datetime


class ArticleListItem(BaseModel):
    """Lightweight article representation for list views.

    Excludes the full ``content`` text to keep list responses small. The
    ``summary`` field provides a brief overview instead.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    summary: Optional[str] = None
    difficulty: Difficulty
    word_count: int
    reading_time: Optional[int] = None
    cover_url: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    created_at: datetime


class ArticleListResponse(BaseModel):
    """Paginated list of articles with total count and page metadata."""

    items: list[ArticleListItem]
    total: int
    page: int
    page_size: int


class ArticleQueryParams(BaseModel):
    """Query parameters for filtering and paginating the article list.

    Used as a structured representation of the query string parameters
    accepted by the list endpoint. The router constructs this model from
    individual ``Query`` parameters and passes it to the service layer.
    """

    difficulty: Optional[Difficulty] = None
    tag: Optional[str] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
