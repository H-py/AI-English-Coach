"""article 模块的 HTTP 路由（对普通用户只读）。

提供列表、详情和标签列表端点。所有端点均需认证（``CurrentUser``）。
文章的创建、更新和删除由 admin 模块在 ``/admin/articles`` 下处理。

``/tags`` 路由声明在 ``/{article_id}`` 之前，以避免路径匹配冲突。
"""

from typing import Optional

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession, RedisClient
from app.core.response import ResponseModel, success
from app.modules.article.models import Difficulty
from app.modules.article.schemas import (
    ArticleListResponse,
    ArticleNeighborsOut,
    ArticleOut,
    ArticleQueryParams,
    ArticleRecommendationsOut,
)
from app.modules.article.service import (
    get_article_detail,
    get_article_list,
    get_article_neighbors,
    get_recommendations,
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
    cet_type: Optional[str] = Query(default=None),
    tag: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    """列出已发布文章，支持可选的筛选与分页。"""
    params = ArticleQueryParams(
        difficulty=difficulty,
        cet_type=cet_type,
        tag=tag,
        page=page,
        page_size=page_size,
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
    """返回已发布文章使用的所有唯一标签。"""
    tags = await get_tags(db)
    return success(tags)


@router.get(
    "/recommendations",
    response_model=ResponseModel[ArticleRecommendationsOut],
    summary="Get personalized article recommendations",
)
async def get_recommendations_endpoint(
    db: DbSession,
    redis: RedisClient,
    current_user: CurrentUser,
) -> dict:
    """根据用户水平/画像/阅读历史返回个性化三档文章推荐。

    由 LLM 单次调用生成；LLM 失败时自动降级为按难度的规则推荐，因此
    该接口通常不报错。
    """
    result = await get_recommendations(db, current_user, redis)
    return success(result)


@router.get(
    "/{article_id}/neighbors",
    response_model=ResponseModel[ArticleNeighborsOut],
    summary="Get article neighbors",
)
async def get_article_neighbors_endpoint(
    article_id: int,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """返回当前文章的上一篇 / 下一篇（按列表顺序循环）。"""
    neighbors = await get_article_neighbors(db, article_id)
    return success(neighbors)


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
    """返回单篇文章的完整详情（会增加浏览次数）。"""
    article = await get_article_detail(db, article_id)
    return success(article)
