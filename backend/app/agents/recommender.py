"""个性化文章推荐 Agent（独立于 ReAct agent 架构）。

本模块与 ``base.py`` / ``reading_coach.py`` 那套 ReAct 对话 agent 完全
隔离：它不继承 :class:`BaseAgent`，不产出 SSE ``AgentStep``。它是一次性
调用的"推荐智能体"——通过调用一组数据工具（复用 ``get_user_profile``，
新增候选文章/已读难度工具）收集用户上下文，再用单次 LLM 调用把文章
分类为三档（适合快速学习 / 适合学习 / 适合挑战学习），失败时降级为
纯规则。

职责边界：
- 本模块（Agent）负责"AI 智能"：编排工具调用、构建 prompt、调用 LLM、
  解析/校验/回填、规则降级、水平→难度映射。
- 数据获取在 ``app/agents/tools/`` 的工具中（复用
  :class:`~app.agents.tools.profile.GetUserProfileTool`，新增
  ``app/agents/tools/recommend.py`` 的候选文章/已读难度工具）。
- 缓存编排与最终响应 schema 组装由 ``app/modules/article/service.py``
  负责，它消费 :class:`RecommendationResult`（含每档文章 id 与序列化
  文章数据）。
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Literal, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tools.base import ToolResult
from app.agents.tools.profile import GetUserProfileTool
from app.agents.tools.recommend import (
    GetReadArticleDifficultyTool,
    ListArticlesTool,
)
from app.core.ai.factory import get_llm_provider_for_user
from app.core.ai.prompt_manager import load_prompt, load_reading_prompt
from app.core.ai.provider import ChatMessage, LLMProvider
from app.modules.users.models import User

logger = logging.getLogger(__name__)

# 每档推荐文章数。
RECOMMEND_PER_TIER = 3
# LLM 采样温度与最大输出 token。
RECOMMEND_TEMP = 0.3
RECOMMEND_MAX_TOKENS = 1500

# 用户英语水平 → 三档难度星级区间（易 / 匹配 / 挑战）。
LEVEL_TO_DIFFICULTY_RANGES: dict[str, dict[str, tuple[int, int]]] = {
    "beginner": {"easy": (1, 2), "matched": (2, 3), "challenging": (3, 4)},
    "intermediate": {"easy": (2, 3), "matched": (3, 4), "challenging": (4, 5)},
    "advanced": {"easy": (3, 4), "matched": (4, 5), "challenging": (5, 5)},
}

# 三档顺序（保证遍历一致）。
_TIERS = ("easy", "matched", "challenging")


@dataclass
class RecommendationResult:
    """推荐结果：三档文章 id + 每档理由 + 来源标记 + 序列化文章数据。

    ``articles_by_id`` 映射文章 id → 序列化后的文章字典（含
    ``ArticleListItem`` 全部字段），供 service 组装响应，无需再查库。
    """

    tier_ids: dict[str, list[int]]
    reasons: dict[str, str]
    generated_by: Literal["agent", "rule"]
    articles_by_id: dict[int, dict] = field(default_factory=dict)


class ArticleRecommender:
    """个性化文章推荐 Agent。

    通过调用数据工具收集上下文，再做单次 LLM 调用把候选文章分为三档。
    LLM 任何失败（含用户配置模型错误、解析失败、超时等）都会静默降级为
    规则推荐，绝不向上抛异常。
    """

    def __init__(self, provider: Optional[LLMProvider] = None) -> None:
        """初始化推荐 Agent。

        Args:
            provider: 可选，预先解析好的 LLM 提供方；为空时在
                :meth:`recommend` 内按用户解析。
        """
        self._provider = provider

    async def recommend(
        self, db: AsyncSession, user: User
    ) -> RecommendationResult:
        """生成三档推荐。

        依次调用工具收集画像 / 已读难度 / 候选文章，再做一次 LLM 调用；
        任何异常降级为规则推荐。

        Args:
            db: 当前活跃的异步会话。
            user: 已认证用户（提供英语水平与 id）。

        Returns:
            :class:`RecommendationResult`。
        """
        profile_result, history_result, articles_result = await self._gather(
            db, user.id
        )
        articles = articles_result.data.get("articles", [])
        if not articles:
            return RecommendationResult(
                tier_ids={t: [] for t in _TIERS},
                reasons={t: "" for t in _TIERS},
                generated_by="rule",
                articles_by_id={},
            )

        articles_by_id = {a["id"]: a for a in articles}
        read_article_ids = {
            r["article_id"]
            for r in history_result.data.get("read_articles", [])
        }
        level = user.english_level.value
        profile_data = profile_result.data

        try:
            # 2) 构建 prompt 并做单次 LLM 调用。
            system_prompt = load_prompt("system/coach", user_level=level)
            user_prompt = load_reading_prompt(
                "article_recommendations",
                user_level=level,
                profile_summary=profile_data.get("profile_summary") or "",
                interests="、".join(profile_data.get("interests") or []),
                weaknesses="、".join(profile_data.get("weaknesses") or []),
                read_history_text=history_result.content,
                candidate_articles=articles_result.content,
            )
            provider = self._provider or await get_llm_provider_for_user(
                db, user.id
            )
            response = await provider.chat(
                messages=[
                    ChatMessage("system", system_prompt),
                    ChatMessage("user", user_prompt),
                ],
                temperature=RECOMMEND_TEMP,
                max_tokens=RECOMMEND_MAX_TOKENS,
            )

            # 3) 解析、校验、回填空档。
            tier_ids, reasons = self._parse_payload(
                response.content, set(articles_by_id.keys())
            )
            tier_ids = self._backfill_empty_tiers(
                tier_ids, articles_by_id, level, read_article_ids
            )
            return RecommendationResult(
                tier_ids=tier_ids,
                reasons=reasons,
                generated_by="agent",
                articles_by_id=articles_by_id,
            )
        except Exception as exc:
            logger.warning(
                "Recommendation LLM failed for user=%s: %s", user.id, exc
            )
            return self.rule_based(level, articles_by_id, read_article_ids)

    async def rule_only(
        self, db: AsyncSession, user: User
    ) -> RecommendationResult:
        """只走规则回退（负缓存命中时用），跳过 LLM 调用。

        仍会调用工具收集候选文章与已读信息，再按水平→星级区间分档。
        """
        _, history_result, articles_result = await self._gather(db, user.id)
        articles = articles_result.data.get("articles", [])
        if not articles:
            return RecommendationResult(
                tier_ids={t: [] for t in _TIERS},
                reasons={t: "" for t in _TIERS},
                generated_by="rule",
                articles_by_id={},
            )
        articles_by_id = {a["id"]: a for a in articles}
        read_article_ids = {
            r["article_id"]
            for r in history_result.data.get("read_articles", [])
        }
        return self.rule_based(
            user.english_level.value, articles_by_id, read_article_ids
        )

    async def _gather(
        self, db: AsyncSession, user_id: int
    ) -> tuple[ToolResult, ToolResult, ToolResult]:
        """调用数据工具收集推荐上下文（画像 / 已读难度 / 候选文章）。"""
        profile_result = await GetUserProfileTool().execute(
            db=db, user_id=user_id
        )
        history_result = await GetReadArticleDifficultyTool().execute(
            db=db, user_id=user_id
        )
        articles_result = await ListArticlesTool().execute(db=db, user_id=user_id)
        return profile_result, history_result, articles_result

    def rule_based(
        self,
        level: str,
        articles_by_id: dict[int, dict],
        read_article_ids: set[int],
    ) -> RecommendationResult:
        """纯规则回退：按水平→星级区间从候选文章中挑选三档。永不抛异常。"""
        ranges = LEVEL_TO_DIFFICULTY_RANGES.get(
            level, LEVEL_TO_DIFFICULTY_RANGES["intermediate"]
        )
        unread = [
            a for a in articles_by_id.values() if a["id"] not in read_article_ids
        ]
        pool = (
            sorted(unread, key=lambda a: a["id"])
            if len(unread) >= RECOMMEND_PER_TIER
            else sorted(articles_by_id.values(), key=lambda a: a["id"])
        )

        assigned: set[int] = set()
        tier_ids: dict[str, list[int]] = {t: [] for t in _TIERS}
        for name in _TIERS:
            lo, hi = ranges[name]
            for a in pool:
                if len(tier_ids[name]) >= RECOMMEND_PER_TIER:
                    break
                if a["id"] in assigned:
                    continue
                if lo <= int(a["difficulty"]) <= hi:
                    tier_ids[name].append(a["id"])
                    assigned.add(a["id"])

        # 兜底：某档仍不足用任意未分配文章补齐。
        for name in _TIERS:
            for a in pool:
                if len(tier_ids[name]) >= RECOMMEND_PER_TIER:
                    break
                if a["id"] in assigned:
                    continue
                tier_ids[name].append(a["id"])
                assigned.add(a["id"])

        return RecommendationResult(
            tier_ids=tier_ids,
            reasons={t: "" for t in _TIERS},
            generated_by="rule",
            articles_by_id=articles_by_id,
        )

    # ------------------------------------------------------------------ #
    # 内部辅助
    # ------------------------------------------------------------------ #

    def _parse_payload(
        self, raw: str, catalog_ids: set[int]
    ) -> tuple[dict[str, list[int]], dict[str, str]]:
        """解析 LLM 返回的推荐 JSON，返回 ``(tier_ids, reasons)``。

        校验：必须是对象；每档为列表；元素为候选清单内的 int；跨档去重
        （先到先得）；每档不超过 :data:`RECOMMEND_PER_TIER`；未知 id 丢弃。
        结构不合法时抛 :class:`ValueError`（由调用方降级为规则推荐）。
        """
        text = raw.strip()
        if text.startswith("```"):
            text = "\n".join(
                line
                for line in text.splitlines()
                if not line.strip().startswith("```")
            )
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            raise ValueError("recommendation payload is not valid JSON")
        if not isinstance(payload, dict):
            raise ValueError("recommendation payload is not an object")

        tier_ids: dict[str, list[int]] = {t: [] for t in _TIERS}
        used: set[int] = set()
        for name in tier_ids:
            raw_list = payload.get(name)
            if not isinstance(raw_list, list):
                raise ValueError(f"tier '{name}' is not a list")
            for item in raw_list:
                if len(tier_ids[name]) >= RECOMMEND_PER_TIER:
                    break
                if (
                    isinstance(item, int)
                    and item in catalog_ids
                    and item not in used
                ):
                    tier_ids[name].append(item)
                    used.add(item)

        reasons: dict[str, str] = {t: "" for t in _TIERS}
        reasons_raw = payload.get("reasons")
        if isinstance(reasons_raw, dict):
            for name in _TIERS:
                r = reasons_raw.get(name)
                if isinstance(r, str):
                    reasons[name] = r[:80]
        return tier_ids, reasons

    def _backfill_empty_tiers(
        self,
        tier_ids: dict[str, list[int]],
        articles_by_id: dict[int, dict],
        level: str,
        read_article_ids: set[int],
    ) -> dict[str, list[int]]:
        """用规则难度区间补齐 LLM 遗漏的空档，保证三档布局完整。"""
        ranges = LEVEL_TO_DIFFICULTY_RANGES.get(
            level, LEVEL_TO_DIFFICULTY_RANGES["intermediate"]
        )
        used = {i for ids in tier_ids.values() for i in ids}
        pool = sorted(articles_by_id.values(), key=lambda a: a["id"])

        for name in _TIERS:
            if len(tier_ids[name]) >= RECOMMEND_PER_TIER:
                continue
            lo, hi = ranges[name]
            for a in pool:
                if len(tier_ids[name]) >= RECOMMEND_PER_TIER:
                    break
                if a["id"] in used:
                    continue
                if lo <= int(a["difficulty"]) <= hi:
                    tier_ids[name].append(a["id"])
                    used.add(a["id"])

        # 兜底：仍不足则用任意未分配文章补齐。
        for name in _TIERS:
            for a in pool:
                if len(tier_ids[name]) >= RECOMMEND_PER_TIER:
                    break
                if a["id"] in used:
                    continue
                tier_ids[name].append(a["id"])
                used.add(a["id"])
        return tier_ids
