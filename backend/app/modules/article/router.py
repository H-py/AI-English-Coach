"""HTTP routes for the article module.

Provides CRUD endpoints for reading articles plus a tag-list endpoint.
All endpoints require authentication (``CurrentUser``). The ``/tags`` route
is declared before ``/{article_id}`` to avoid path-matching conflicts.

Note: create, update, and delete operations currently require only an
authenticated user. Admin-level authorization will be added in a later
phase once the ``is_admin`` field is introduced on the ``User`` model.
"""

from typing import Optional

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.core.response import ResponseModel, success
from app.modules.article.models import Difficulty
from app.modules.article.schemas import (
    ArticleCreate,
    ArticleListResponse,
    ArticleOut,
    ArticleQueryParams,
    ArticleUpdate,
)
from app.modules.article.service import (
    create_article,
    delete_article,
    get_article_detail,
    get_article_list,
    get_tags,
    update_article,
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


@router.post(
    "",
    response_model=ResponseModel[ArticleOut],
    status_code=201,
    summary="Create article",
)
async def create_article_endpoint(
    data: ArticleCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Create a new article (word count is auto-calculated)."""
    article = await create_article(db, data)
    return success(article)


@router.put(
    "/{article_id}",
    response_model=ResponseModel[ArticleOut],
    summary="Update article",
)
async def update_article_endpoint(
    article_id: int,
    data: ArticleUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Partially update an existing article."""
    article = await update_article(db, article_id, data)
    return success(article)


@router.delete(
    "/{article_id}",
    response_model=ResponseModel[None],
    summary="Delete article",
)
async def delete_article_endpoint(
    article_id: int,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Delete an article by its id."""
    await delete_article(db, article_id)
    return success(None)
