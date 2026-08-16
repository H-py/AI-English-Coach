"""article 模块的业务逻辑层。

服务层位于 HTTP 路由与 repository 之间，负责领域规则：将"未找到"转换为
:class:`BizException`、根据文章正文自动计算 ``word_count``、在详情读取时
编排浏览次数的自增，以及基于用户水平/画像/阅读历史的个性化文章推荐。
"""

import json
import logging
from datetime import datetime, timezone
from typing import Literal, Optional

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.recommender import ArticleRecommender
from app.core.ai.cache import (
    RECOMMENDATION_CACHE_TTL,
    recommendation_cache_key,
)
from app.core.exceptions import BizException
from app.modules.ai import memory_repository as mem_repo
from app.modules.article.repository import (
    create_article as repo_create_article,
    delete_article as repo_delete_article,
    get_all_tags as repo_get_all_tags,
    get_article_by_id as repo_get_article_by_id,
    get_article_neighbors as repo_get_article_neighbors,
    increment_view_count as repo_increment_view_count,
    list_articles as repo_list_articles,
    update_article as repo_update_article,
)
from app.modules.article.schemas import (
    ArticleCreate,
    ArticleListItem,
    ArticleListResponse,
    ArticleNeighborRef,
    ArticleNeighborsOut,
    ArticleOut,
    ArticleQueryParams,
    ArticleRecommendationsOut,
    ArticleUpdate,
    RecommendationTier,
)
from app.modules.users.models import User

logger = logging.getLogger(__name__)

# 业务错误码：请求的文章不存在。
ARTICLE_NOT_FOUND_CODE = 90002


def _calculate_word_count(content: str) -> int:
    """通过按空白字符拆分文本来计算单词数。

    Args:
        content: 文章正文。

    Returns:
        按空白字符拆分后的 token 数量。
    """
    return len(content.split())


async def get_article_list(
    db: AsyncSession, params: ArticleQueryParams
) -> ArticleListResponse:
    """返回已发布文章的分页、筛选列表。

    Args:
        db: 当前活跃的异步会话。
        params: 用于筛选（difficulty、tag）和分页（page、page_size）
            的查询参数。

    Returns:
        一个 :class:`ArticleListResponse`，包含列表项与分页元数据。
    """
    items, total = await repo_list_articles(
        db,
        difficulty=params.difficulty,
        cet_type=params.cet_type,
        tag=params.tag,
        page=params.page,
        page_size=params.page_size,
    )
    return ArticleListResponse(
        items=[ArticleListItem.model_validate(article) for article in items],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


async def get_article_detail(
    db: AsyncSession, article_id: int
) -> ArticleOut:
    """返回单篇文章的完整详情，并增加其浏览次数。

    Args:
        db: 当前活跃的异步会话。
        article_id: 文章的主键。

    Returns:
        由持久化文章构建的 :class:`ArticleOut`。

    Raises:
        BizException: 如果不存在指定 id 的文章
            （错误码 ``90002``）。
    """
    article = await repo_get_article_by_id(db, article_id)
    if article is None:
        raise BizException("文章不存在", code=ARTICLE_NOT_FOUND_CODE)

    # 在增加浏览次数之前先序列化文章。``increment_view_count`` repository
    # 方法会发出一条 Core ``UPDATE`` 语句，这会导致 SQLAlchemy 让会话中
    # 的 ``article`` ORM 实例过期。在过期实例上访问属性（正如
    # ``model_validate`` 所做的那样）会触发一次懒加载，而当事务状态不再
    # 干净时该懒加载可能会失败。先序列化可以完全规避这一问题；返回的
    # ``view_count`` 反映的是本次浏览之前的次数，这正是预期行为。
    result = ArticleOut.model_validate(article)

    await repo_increment_view_count(db, article_id)

    return result


async def get_article_neighbors(
    db: AsyncSession, article_id: int
) -> ArticleNeighborsOut:
    """返回当前文章的上一篇 / 下一篇（循环）。

    顺序与列表接口一致（``created_at`` 倒序）。循环规则：第一篇的
    上一篇是最后一篇，最后一篇的下一篇是第一篇。

    Args:
        db: 当前活跃的异步会话。
        article_id: 当前文章的主键。

    Returns:
        :class:`ArticleNeighborsOut`，包含 ``prev`` 与 ``next`` 的
        轻量引用（可能为 ``None``）。

    Raises:
        BizException: 如果不存在指定 id 的文章
            （错误码 ``90002``）。
    """
    article = await repo_get_article_by_id(db, article_id)
    if article is None:
        raise BizException("文章不存在", code=ARTICLE_NOT_FOUND_CODE)

    prev, nxt = await repo_get_article_neighbors(db, article_id)
    return ArticleNeighborsOut(
        prev=ArticleNeighborRef(id=prev[0], title=prev[1]) if prev else None,
        next=ArticleNeighborRef(id=nxt[0], title=nxt[1]) if nxt else None,
    )


async def create_article(
    db: AsyncSession, data: ArticleCreate
) -> ArticleOut:
    """创建新文章，并自动计算字数。

    Args:
        db: 当前活跃的异步会话。
        data: 已校验的创建载荷。

    Returns:
        新建文章对应的 :class:`ArticleOut`。
    """
    word_count = _calculate_word_count(data.content)
    article = await repo_create_article(db, data, word_count)
    return ArticleOut.model_validate(article)


async def update_article(
    db: AsyncSession, article_id: int, data: ArticleUpdate
) -> ArticleOut:
    """对已有文章应用部分更新。

    仅应用 ``data`` 中显式提供的字段（通过 ``exclude_unset``）。若
    ``content`` 被更新，``word_count`` 会自动重新计算。

    Args:
        db: 当前活跃的异步会话。
        article_id: 文章的主键。
        data: 部分更新载荷。

    Returns:
        反映更新后文章的 :class:`ArticleOut`。

    Raises:
        BizException: 如果不存在指定 id 的文章
            （错误码 ``90002``）。
    """
    article = await repo_get_article_by_id(db, article_id)
    if article is None:
        raise BizException("文章不存在", code=ARTICLE_NOT_FOUND_CODE)

    update_data = data.model_dump(exclude_unset=True)

    # 若正文正在更新，则重新计算字数。
    if "content" in update_data and update_data["content"] is not None:
        update_data["word_count"] = _calculate_word_count(
            update_data["content"]
        )

    if update_data:
        article = await repo_update_article(db, article, update_data)

    return ArticleOut.model_validate(article)


async def delete_article(db: AsyncSession, article_id: int) -> None:
    """根据 id 删除文章。

    Args:
        db: 当前活跃的异步会话。
        article_id: 文章的主键。

    Raises:
        BizException: 如果不存在指定 id 的文章
            （错误码 ``90002``）。
    """
    article = await repo_get_article_by_id(db, article_id)
    if article is None:
        raise BizException("文章不存在", code=ARTICLE_NOT_FOUND_CODE)

    await repo_delete_article(db, article)


async def get_tags(db: AsyncSession) -> list[str]:
    """返回已发布文章使用的所有唯一标签。

    Args:
        db: 当前活跃的异步会话。

    Returns:
        排好序的唯一标签字符串列表。
    """
    return await repo_get_all_tags(db)


# ============================================================================
#  个性化文章推荐
# ============================================================================
#
# 职责划分：
# - 本模块只做【编排】：Redis 缓存（正缓存 + 负缓存）、调用
#   :class:`ArticleRecommender`、把 Agent 返回的序列化文章数据组装为
#   响应 schema。不涉及任何 AI 逻辑。
# - 数据获取全部在 ``app/agents/tools/`` 的工具中（复用
#   ``get_user_profile``，新增 ``list_articles`` / ``get_read_article_difficulty``），
#   由 :class:`ArticleRecommender` 内部调用。
# - AI 智能（prompt 构建、LLM 调用、解析校验、规则降级）在
#   ``app/agents/recommender.py``。

# LLM 失败后的负缓存时长：避免坏配置/坏模型让首页每次都等待超时。
RECOMMEND_NEGATIVE_CACHE_TTL = 300


def _build_recommendation_response(
    articles_by_id: dict[int, dict],
    tier_ids: dict[str, list[int]],
    reasons: dict[str, str],
    generated_by: Literal["agent", "rule"],
) -> ArticleRecommendationsOut:
    """把 Agent 返回的档位 id 映射回序列化文章，组装响应。"""
    def build_tier(name: str) -> RecommendationTier:
        return RecommendationTier(
            items=[
                ArticleListItem.model_validate(articles_by_id[i])
                for i in tier_ids[name]
                if i in articles_by_id
            ],
            reason=reasons.get(name) or None,
        )

    return ArticleRecommendationsOut(
        easy=build_tier("easy"),
        matched=build_tier("matched"),
        challenging=build_tier("challenging"),
        generated_by=generated_by,
        generated_at=datetime.now(timezone.utc),
    )


def _empty_recommendations() -> ArticleRecommendationsOut:
    """候选文章为空时的空响应（三档为空，来源标记为 rule）。"""
    empty = RecommendationTier(items=[], reason=None)
    return ArticleRecommendationsOut(
        easy=empty,
        matched=empty,
        challenging=empty,
        generated_by="rule",
        generated_at=datetime.now(timezone.utc),
    )


async def _safe_redis_get(redis: aioredis.Redis, key: str) -> Optional[str]:
    """Best-effort 读取缓存；Redis 异常时返回 None 而非抛错。

    注意 Redis 客户端配置了 ``decode_responses=True``，``get`` 已返回
    字符串，无需额外解码。
    """
    try:
        return await redis.get(key)
    except Exception:
        logger.warning("Redis get failed for key=%s", key)
        return None


async def _safe_redis_set(
    redis: aioredis.Redis, key: str, value: str, ex: int
) -> None:
    """Best-effort 写入缓存；Redis 异常时静默忽略。"""
    try:
        await redis.set(key, value, ex=ex)
    except Exception:
        logger.warning("Redis set failed for key=%s", key)


async def get_recommendations(
    db: AsyncSession, user: User, redis: Optional[aioredis.Redis]
) -> ArticleRecommendationsOut:
    """生成个性化三档文章推荐。

    流程：查缓存 → 查负缓存 → 交给 :class:`ArticleRecommender`
    （内部调用数据工具 + 单次 LLM 调用，失败自动降级为规则）→ 缓存
    agent 结果 → 组装返回。首页永不因推荐而失败。
    """
    level = user.english_level.value
    profile = await mem_repo.get_profile(db, user.id)
    profile_ts = (
        profile.last_updated_at.isoformat()
        if profile and profile.last_updated_at
        else "none"
    )
    cache_key = recommendation_cache_key(user.id, level, profile_ts)
    negative_key = f"{cache_key}:neg"

    if redis is not None:
        cached = await _safe_redis_get(redis, cache_key)
        if cached:
            try:
                return ArticleRecommendationsOut.model_validate(json.loads(cached))
            except Exception:
                logger.warning("Invalid cached recommendation for user=%s", user.id)
        # 负缓存命中：LLM 近期失败过，直接走规则，避免反复等待坏模型。
        if await _safe_redis_get(redis, negative_key):
            recommender = ArticleRecommender()
            result = await recommender.rule_only(db, user)
            return _build_recommendation_response(
                result.articles_by_id,
                result.tier_ids,
                result.reasons,
                result.generated_by,
            )

    recommender = ArticleRecommender()
    result = await recommender.recommend(db, user)
    if not result.articles_by_id:
        return _empty_recommendations()

    if redis is not None:
        # 仅缓存 agent 结果；规则结果便宜，不缓存，但写负缓存避免反复打坏模型。
        if result.generated_by == "agent":
            response = _build_recommendation_response(
                result.articles_by_id,
                result.tier_ids,
                result.reasons,
                "agent",
            )
            await _safe_redis_set(
                redis,
                cache_key,
                json.dumps(response.model_dump(mode="json"), ensure_ascii=False),
                ex=RECOMMENDATION_CACHE_TTL,
            )
            return response
        await _safe_redis_set(
            redis, negative_key, "1", ex=RECOMMEND_NEGATIVE_CACHE_TTL
        )

    return _build_recommendation_response(
        result.articles_by_id,
        result.tier_ids,
        result.reasons,
        result.generated_by,
    )
