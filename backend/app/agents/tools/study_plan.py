"""生词背诵计划专用的数据获取工具。

这些工具供 :class:`~app.agents.vocabulary_planner.VocabularyPlanner`
调用，只负责从数据库取数并渲染成 LLM 可读文本（``content``）与结构化
数据（``data``），不包含任何 AI 决策逻辑。

- :class:`ListSavedWordsTool`：获取用户收藏的单词清单（含掌握度、学习次数、
  释义），供背诵规划 Agent 选词。

与文章推荐的数据工具（``recommend.py``）保持同一套结构。
"""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tools.base import BaseTool, ToolParameter, ToolResult
from app.modules.reading.repository import list_words
from app.modules.word_bank.repository import get_levels_for_words

# 参与背诵规划的单词上限（最新收藏优先）。
PLAN_WORDS_CAP = 200
# LLM 清单中释义的截断长度。
_PLAN_EXPLANATION_MAX_CHARS = 60


def _last_studied_label(word) -> str:
    """把上次学习时间整理成相对描述（N 天前 / 今天 / 从未学习），便于 LLM 判断。"""
    if not word.last_studied_at:
        return "从未学习"
    days = (datetime.now(timezone.utc) - word.last_studied_at).days
    if days <= 0:
        return "今天"
    return f"{days} 天前"


def _serialize_word(word) -> dict:
    """把 ORM WordCollection 序列化为 WordCollectionOut 所需字段的字典。"""
    return {
        "id": word.id,
        "user_id": word.user_id,
        "word": word.word,
        "context": word.context,
        "article_id": word.article_id,
        "ai_explanation": word.ai_explanation,
        "short_meaning": word.short_meaning,
        "mastery_level": word.mastery_level.value,
        "study_count": word.study_count,
        "last_studied_at": str(word.last_studied_at) if word.last_studied_at else None,
        "created_at": str(word.created_at),
        "updated_at": str(word.updated_at),
    }


class ListSavedWordsTool(BaseTool):
    """获取用户收藏的单词清单（含掌握度 / 学习次数 / 释义）。"""

    @property
    def name(self) -> str:
        return "list_saved_words"

    @property
    def description(self) -> str:
        return (
            "获取用户收藏的全部单词清单，包含单词、掌握程度、学习次数和简短释义。"
            "当需要为用户安排背诵、复习或规划学习内容时使用。"
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="level",
                type="string",
                description=(
                    "可选，按分级词库等级过滤收藏单词。可选值："
                    "cet4（四级）、cet6（六级）、kaoyan（考研）。"
                    "不传则返回全部收藏单词。"
                ),
                required=False,
            ),
        ]

    async def execute(self, **kwargs: Any) -> ToolResult:
        """执行收藏单词查询。

        Args:
            **kwargs: 包含 ``db``、``user_id``（隐式注入）以及可选的
                ``level``（显式参数，按分级词库等级过滤）。

        Returns:
            :class:`ToolResult`，``content`` 为单词清单文本，
            ``data`` 包含每篇序列化后的单词字典。
        """
        db: AsyncSession = kwargs["db"]
        user_id: int = kwargs["user_id"]
        level_filter: str | None = kwargs.get("level")

        items, total = await list_words(
            db, user_id, page=1, page_size=PLAN_WORDS_CAP
        )
        if not items:
            return ToolResult(
                success=True,
                content="用户还没有收藏任何单词。",
                data={"words": [], "total": 0},
            )

        # 按分级词库等级过滤（只保留命中该等级的收藏词）。
        if level_filter:
            items = await self._filter_by_level(db, items, level_filter)
            if not items:
                return ToolResult(
                    success=True,
                    content=(
                        f"用户收藏中没有属于等级 '{level_filter}' 的单词。"
                    ),
                    data={"words": [], "total": 0},
                )

        lines: list[str] = [
            f"用户共收藏 {total} 个单词（显示最新 {len(items)} 个）：\n"
        ]
        words: list[dict] = []
        for w in items:
            explanation = (w.short_meaning or w.ai_explanation or "")[
                :_PLAN_EXPLANATION_MAX_CHARS
            ]
            lines.append(
                f"{w.id}. {w.word}（学{w.study_count}次 · "
                f"上次学习{_last_studied_label(w)} · 掌握:{w.mastery_level.value}）"
                f"释义:{explanation}"
            )
            words.append(_serialize_word(w))

        return ToolResult(
            success=True,
            content="\n".join(lines),
            data={"words": words, "total": total},
        )

    @staticmethod
    async def _filter_by_level(
        db: AsyncSession, items: list, level: str
    ) -> list:
        """从收藏词中筛出分级词库中命中指定等级的单词。"""
        words = [w.word.strip().lower() for w in items]
        levels = await get_levels_for_words(db, words)
        return [w for w in items if level in levels.get(w.word.strip().lower(), [])]
