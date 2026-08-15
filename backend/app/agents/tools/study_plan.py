"""生词背诵计划专用的数据获取工具。

这些工具供 :class:`~app.agents.vocabulary_planner.VocabularyPlanner`
调用，只负责从数据库取数并渲染成 LLM 可读文本（``content``）与结构化
数据（``data``），不包含任何 AI 决策逻辑。

- :class:`ListSavedWordsTool`：获取用户收藏的单词清单（含掌握度、学习次数、
  释义），供背诵规划 Agent 选词。

与文章推荐的数据工具（``recommend.py``）保持同一套结构。
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tools.base import BaseTool, ToolParameter, ToolResult
from app.modules.reading.repository import list_words

# 参与背诵规划的单词上限（最新收藏优先）。
PLAN_WORDS_CAP = 200
# LLM 清单中释义的截断长度。
_PLAN_EXPLANATION_MAX_CHARS = 60


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
        return []

    async def execute(self, **kwargs: Any) -> ToolResult:
        """执行收藏单词查询。

        Args:
            **kwargs: 包含 ``db``、``user_id``（隐式注入），无显式参数。

        Returns:
            :class:`ToolResult`，``content`` 为单词清单文本，
            ``data`` 包含每篇序列化后的单词字典。
        """
        db: AsyncSession = kwargs["db"]
        user_id: int = kwargs["user_id"]

        items, total = await list_words(
            db, user_id, page=1, page_size=PLAN_WORDS_CAP
        )
        if not items:
            return ToolResult(
                success=True,
                content="用户还没有收藏任何单词。",
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
            last_studied = (
                f"上次学习 {w.last_studied_at:%Y-%m-%d}"
                if w.last_studied_at
                else "从未学习"
            )
            lines.append(
                f"{w.id}. {w.word}（掌握:{w.mastery_level.value}，"
                f"学习{w.study_count}次，{last_studied}）释义:{explanation}"
            )
            words.append(_serialize_word(w))

        return ToolResult(
            success=True,
            content="\n".join(lines),
            data={"words": words, "total": total},
        )
