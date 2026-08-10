"""用户画像与学习统计工具。

提供两个工具供 Agent 查询用户的学习画像：

- :class:`GetUserProfileTool`：获取用户的 AI 生成学习画像。
- :class:`GetLearningStatsTool`：获取用户的学习数据汇总统计。

通过 ``app.modules.ai.memory_repository`` 获取用户画像，通过
``app.modules.reading.repository`` 获取各项学习数据的总数。
"""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tools.base import BaseTool, ToolParameter, ToolResult
from app.modules.ai.memory_repository import get_profile
from app.modules.reading.models import ReadingHistory
from app.modules.reading.repository import (
    list_histories,
    list_sentences,
    list_words,
)


class GetUserProfileTool(BaseTool):
    """获取用户的学习画像。

    返回 AI 生成的用户画像，包括画像摘要、优势、弱点、学习风格、
    兴趣和常见错误。
    """

    @property
    def name(self) -> str:
        return "get_user_profile"

    @property
    def description(self) -> str:
        return (
            "获取用户的学习画像，包括画像摘要、优势、弱点、学习风格和兴趣。"
            "当需要了解用户的学习特征以提供个性化建议时使用。"
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return []

    async def execute(self, **kwargs: Any) -> ToolResult:
        """执行用户画像查询。

        Args:
            **kwargs: 包含 ``db``、``user_id``（隐式注入），无显式参数。

        Returns:
            :class:`ToolResult`，``content`` 为格式化的画像文本，
            ``data`` 包含原始画像数据。
        """
        db: AsyncSession = kwargs["db"]
        user_id: int = kwargs["user_id"]

        profile = await get_profile(db, user_id)

        if profile is None:
            return ToolResult(
                success=True,
                content="用户尚未生成学习画像。",
                data={"has_profile": False},
            )

        strengths = profile.strengths or []
        weaknesses = profile.weaknesses or []
        interests = profile.interests or []
        common_mistakes = profile.common_mistakes or []

        lines = [
            f"画像摘要: {profile.profile_summary or '暂无'}",
            f"优势: {', '.join(strengths) if strengths else '暂无'}",
            f"弱点: {', '.join(weaknesses) if weaknesses else '暂无'}",
            f"学习风格: {profile.learning_style or '暂无'}",
            f"兴趣: {', '.join(interests) if interests else '暂无'}",
            f"常见错误: {', '.join(common_mistakes) if common_mistakes else '暂无'}",
            f"消息总数: {profile.message_count}",
        ]

        data = {
            "has_profile": True,
            "profile_summary": profile.profile_summary,
            "strengths": strengths,
            "weaknesses": weaknesses,
            "learning_style": profile.learning_style,
            "interests": interests,
            "common_mistakes": common_mistakes,
            "message_count": profile.message_count,
        }

        return ToolResult(
            success=True,
            content="\n".join(lines),
            data=data,
        )


class GetLearningStatsTool(BaseTool):
    """获取用户的学习数据汇总统计。

    聚合用户的收藏单词数、收藏句子数、阅读文章数和总阅读时长，
    以帮助 Agent 了解用户的整体学习进度。
    """

    @property
    def name(self) -> str:
        return "get_learning_stats"

    @property
    def description(self) -> str:
        return (
            "获取用户的学习数据汇总统计，包括收藏单词数、收藏句子数、"
            "阅读文章数和总阅读时长。当需要了解用户的整体学习进度时使用。"
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return []

    async def execute(self, **kwargs: Any) -> ToolResult:
        """执行学习统计聚合查询。

        使用 ``list_words``、``list_sentences``、``list_histories`` 以
        ``page_size=1`` 获取各项总数，再通过直接查询汇总总阅读时长。

        Args:
            **kwargs: 包含 ``db``、``user_id``（隐式注入），无显式参数。

        Returns:
            :class:`ToolResult`，``content`` 为格式化的统计文本，
            ``data`` 包含原始统计数据。
        """
        db: AsyncSession = kwargs["db"]
        user_id: int = kwargs["user_id"]

        # 使用 page_size=1 仅获取总数，不加载实际数据，减少数据库开销。
        _, total_words = await list_words(db, user_id, page=1, page_size=1)
        _, total_sentences = await list_sentences(
            db, user_id, page=1, page_size=1
        )
        _, total_articles = await list_histories(
            db, user_id, page=1, page_size=1
        )

        # 直接查询总阅读时长（秒），避免加载全部历史记录到内存。
        total_reading_seconds = (
            await db.execute(
                select(
                    func.coalesce(
                        func.sum(ReadingHistory.duration_seconds), 0
                    )
                ).where(ReadingHistory.user_id == user_id)
            )
        ).scalar() or 0

        total_reading_minutes = total_reading_seconds // 60

        lines = [
            f"收藏单词总数: {total_words}",
            f"收藏句子总数: {total_sentences}",
            f"阅读文章总数: {total_articles}",
            f"总阅读时长: {total_reading_minutes} 分钟"
            f"（{total_reading_seconds} 秒）",
        ]

        data = {
            "total_words": total_words,
            "total_sentences": total_sentences,
            "total_articles": total_articles,
            "total_reading_seconds": total_reading_seconds,
            "total_reading_minutes": total_reading_minutes,
        }

        return ToolResult(
            success=True,
            content="\n".join(lines),
            data=data,
        )
