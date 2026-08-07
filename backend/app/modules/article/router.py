"""HTTP routes for the article module (read-only for regular users).

Provides list, detail, and tag-list endpoints. All endpoints require
authentication (``CurrentUser``). Article creation, update, and deletion
are handled by the admin module under ``/admin/articles``.

The ``/tags`` route is declared before ``/{article_id}`` to avoid
path-matching conflicts.
"""

from typing import Optional

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.core.response import ResponseModel, success
from app.modules.article.models import Difficulty
from app.modules.article.schemas import (
    ArticleListResponse,
    ArticleOut,
    ArticleQueryParams,
)
from app.modules.article.service import (
    get_article_detail,
    get_article_list,
    get_tags,
)

router = APIRouter(prefix="/articles", tags=["articles"])


@router.get(
    "",
    response_model=ResponseModel[ArticleListResponse],
    summary="List articles",
)
async def list_articles_endpoint(
    db: DbSession,
    current_user: CurrentUser,
    difficulty: Optional[Difficulty] = Query(default=None),
    tag: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    """List published articles with optional filtering and pagination."""
    params = ArticleQueryParams(
        difficulty=difficulty, tag=tag, page=page, page_size=page_size
    )
    result = await get_article_list(db, params)
    return success(result)


@router.get(
    "/tags",
    response_model=ResponseModel[list[str]],
    summary="List all tags",
)
async def list_tags_endpoint(
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Return all unique tags used by published articles."""
    tags = await get_tags(db)
    return success(tags)


@router.get(
    "/{article_id}",
    response_model=ResponseModel[ArticleOut],
    summary="Get article detail",
)
async def get_article_endpoint(
    article_id: int,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Return the full detail of a single article (increments view count)."""
    article = await get_article_detail(db, article_id)
    return success(article)
