"""生词背诵规划 Agent（独立于 ReAct agent 架构）。

本模块与 ``base.py`` / ``reading_coach.py`` 那套 ReAct 对话 agent 完全
隔离，与文章推荐 Agent（``recommender.py``）同构：通过调用数据工具收集
用户上下文（画像 + 收藏单词），再用单次 LLM 调用生成一次背诵方案（选词
+ 顺序 + 背诵建议），失败时降级为纯规则选词。

职责边界：
- 本模块（Agent）负责"AI 智能"：编排工具调用、构建 prompt、调用 LLM、
  解析/校验/补足、规则降级、选词排序。
- 数据获取在 ``app/agents/tools/study_plan.py`` 的
  :class:`~app.agents.tools.study_plan.ListSavedWordsTool` 与
  ``app/agents/tools/profile.py`` 的
  :class:`~app.agents.tools.profile.GetUserProfileTool`。
- 响应 schema 组装由 ``app/modules/reading/service.py`` 负责，它消费
  :class:`VocabularyPlanResult`（含有序单词 id 与序列化单词数据）。
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Literal, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tools.base import ToolResult
from app.agents.tools.profile import GetUserProfileTool
from app.agents.tools.study_plan import ListSavedWordsTool
from app.core.ai.factory import get_llm_provider_for_user
from app.core.ai.prompt_manager import load_prompt, load_reading_prompt
from app.core.ai.provider import ChatMessage, LLMProvider
from app.modules.users.models import User

logger = logging.getLogger(__name__)

# LLM 采样温度与最大输出 token。
PLAN_TEMP = 0.3
PLAN_MAX_TOKENS = 1000

# 掌握程度排序（越靠前越优先背诵）。
_MASTERY_ORDER = {
    "new": 0,
    "learning": 1,
    "familiar": 2,
    "mastered": 3,
}


@dataclass
class VocabularyPlanResult:
    """一次背诵方案：有序单词 id + 背诵建议 + 来源标记 + 序列化单词数据。

    ``words_by_id`` 映射单词 id → 序列化后的单词字典（含
    ``WordCollectionOut`` 全部字段），供 service 组装响应，无需再查库。
    """

    word_ids: list[int]
    note: Optional[str]
    generated_by: Literal["agent", "rule"]
    words_by_id: dict[int, dict] = field(default_factory=dict)


class VocabularyPlanner:
    """生词背诵规划 Agent。

    通过调用数据工具收集上下文，再做单次 LLM 调用选出本次要背诵的
    单词并安排顺序。LLM 任何失败都会静默降级为规则选词，绝不抛异常。
    """

    def __init__(self, provider: Optional[LLMProvider] = None) -> None:
        """初始化背诵规划 Agent。

        Args:
            provider: 可选，预先解析好的 LLM 提供方；为空时在
                :meth:`plan` 内按用户解析。
        """
        self._provider = provider

    async def plan(
        self, db: AsyncSession, user: User, count: int
    ) -> VocabularyPlanResult:
        """生成一次背诵方案（有序选词 + 建议）。

        Args:
            db: 当前活跃的异步会话。
            user: 已认证用户（提供英语水平与 id）。
            count: 本次要背诵的单词数量。

        Returns:
            :class:`VocabularyPlanResult`。
        """
        profile_result, words_result = await self._gather(db, user.id)
        words = words_result.data.get("words", [])
        if not words:
            return VocabularyPlanResult(
                word_ids=[], note=None, generated_by="rule", words_by_id={}
            )

        words_by_id = {w["id"]: w for w in words}
        level = user.english_level.value
        profile_data = profile_result.data

        try:
            system_prompt = load_prompt("system/coach", user_level=level)
            user_prompt = load_reading_prompt(
                "vocabulary_study_plan",
                user_level=level,
                profile_summary=profile_data.get("profile_summary") or "",
                interests="、".join(profile_data.get("interests") or []),
                weaknesses="、".join(profile_data.get("weaknesses") or []),
                saved_words=words_result.content,
                count=count,
            )
            provider = self._provider or await get_llm_provider_for_user(
                db, user.id
            )
            response = await provider.chat(
                messages=[
                    ChatMessage("system", system_prompt),
                    ChatMessage("user", user_prompt),
                ],
                temperature=PLAN_TEMP,
                max_tokens=PLAN_MAX_TOKENS,
            )
            word_ids, note = self._parse_payload(
                response.content, set(words_by_id.keys()), count
            )
            word_ids = self._backfill(word_ids, words_by_id, count)
            return VocabularyPlanResult(
                word_ids=word_ids,
                note=note,
                generated_by="agent",
                words_by_id=words_by_id,
            )
        except Exception as exc:
            logger.warning(
                "Vocabulary plan LLM failed for user=%s: %s", user.id, exc
            )
            return self.rule_based(level, words_by_id, count)

    async def rule_only(
        self, db: AsyncSession, user: User, count: int
    ) -> VocabularyPlanResult:
        """只走规则选词（负缓存命中时用），跳过 LLM 调用。"""
        _, words_result = await self._gather(db, user.id)
        words = words_result.data.get("words", [])
        if not words:
            return VocabularyPlanResult(
                word_ids=[], note=None, generated_by="rule", words_by_id={}
            )
        words_by_id = {w["id"]: w for w in words}
        return self.rule_based(user.english_level.value, words_by_id, count)

    async def _gather(
        self, db: AsyncSession, user_id: int
    ) -> tuple[ToolResult, ToolResult]:
        """调用数据工具收集上下文（画像 + 收藏单词）。"""
        profile_result = await GetUserProfileTool().execute(
            db=db, user_id=user_id
        )
        words_result = await ListSavedWordsTool().execute(
            db=db, user_id=user_id
        )
        return profile_result, words_result

    # ------------------------------------------------------------------ #
    # 内部辅助
    # ------------------------------------------------------------------ #

    def rule_based(
        self,
        level: str,
        words_by_id: dict[int, dict],
        count: int,
    ) -> VocabularyPlanResult:
        """纯规则选词：未掌握优先 → 久未学习优先 → 学习次数少优先。"""
        sorted_words = sorted(
            words_by_id.values(),
            key=lambda w: (
                _MASTERY_ORDER.get(w["mastery_level"], 0),
                w["last_studied_at"] is not None,  # 从未学习（None）排前
                w["last_studied_at"] or "",
                w["study_count"],
            ),
        )
        word_ids = [w["id"] for w in sorted_words[:count]]
        return VocabularyPlanResult(
            word_ids=word_ids,
            note=None,
            generated_by="rule",
            words_by_id=words_by_id,
        )

    def _parse_payload(
        self, raw: str, word_ids_set: set[int], count: int
    ) -> tuple[list[int], Optional[str]]:
        """解析 LLM 返回的背诵方案 JSON，返回 ``(word_ids, note)``。

        校验：必须为对象；``word_ids`` 为列表且元素都在收藏清单内、
        去重、至多 ``count`` 个；``note`` 为可选字符串。结构不合法时抛
        :class:`ValueError`（由调用方降级为规则选词）。
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
            raise ValueError("vocabulary plan payload is not valid JSON")
        if not isinstance(payload, dict):
            raise ValueError("vocabulary plan payload is not an object")

        raw_ids = payload.get("word_ids")
        if not isinstance(raw_ids, list):
            raise ValueError("plan 'word_ids' is not a list")

        word_ids: list[int] = []
        used: set[int] = set()
        for item in raw_ids:
            if len(word_ids) >= count:
                break
            if isinstance(item, int) and item in word_ids_set and item not in used:
                word_ids.append(item)
                used.add(item)

        note_raw = payload.get("note")
        note = str(note_raw)[:200] if isinstance(note_raw, str) else None
        return word_ids, note

    def _backfill(
        self, word_ids: list[int], words_by_id: dict[int, dict], count: int
    ) -> list[int]:
        """用规则排序补齐 LLM 遗漏的单词，保证恰好 ``count`` 个。"""
        if len(word_ids) >= count:
            return word_ids
        used = set(word_ids)
        rule_result = self.rule_based("intermediate", words_by_id, count)
        for wid in rule_result.word_ids:
            if len(word_ids) >= count:
                break
            if wid not in used:
                word_ids.append(wid)
                used.add(wid)
        return word_ids
