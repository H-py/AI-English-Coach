"""阅读数据查询工具。

提供三个工具供 Agent 查询用户的阅读相关数据：

- :class:`GetReadingHistoryTool`：获取最近的阅读历史。
- :class:`GetArticleContentTool`：获取文章内容（自动截断）。
- :class:`GetSentenceCollectionTool`：获取收藏的句子。

所有工具通过 ``app.modules.reading.repository`` 和
``app.modules.article.repository`` 中的函数访问数据库，并由
:class:`~app.agents.base.BaseAgent` 注入 ``db`` 和 ``user_id``
作为隐式上下文参数。
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tools.base import BaseTool, ToolParameter, ToolResult
from app.core.ai.cache import truncate_for_context
from app.modules.article.repository import get_article_by_id
from app.modules.reading.repository import (
    list_histories_with_article,
    list_sentences,
)

# 阅读历史默认返回的条数。
_HISTORY_PAGE_SIZE = 10
# 句子收藏默认返回的条数。
_SENTENCE_PAGE_SIZE = 20


class GetReadingHistoryTool(BaseTool):
    """获取用户最近的阅读历史。

    返回最近 10 条阅读历史记录，包含文章标题、阅读次数和阅读时长。
    """

    @property
    def name(self) -> str:
        return "get_reading_history"

    @property
    def description(self) -> str:
        return (
            "获取用户最近的阅读历史记录，包括文章标题、阅读次数和阅读时长。"
            "当用户询问阅读记录、阅读进度或最近读了什么时使用。"
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return []

    async def execute(self, **kwargs: Any) -> ToolResult:
        """执行阅读历史查询。

        Args:
            **kwargs: 包含 ``db``、``user_id``（隐式注入），无显式参数。

        Returns:
            :class:`ToolResult`，``content`` 为格式化的阅读历史列表文本，
            ``data`` 包含原始历史数据。
        """
        db: AsyncSession = kwargs["db"]
        user_id: int = kwargs["user_id"]

        items, total = await list_histories_with_article(
            db, user_id, page=1, page_size=_HISTORY_PAGE_SIZE
        )

        if not items:
            return ToolResult(
                success=True,
                content="用户还没有任何阅读历史记录。",
                data={"total": 0, "histories": []},
            )

        lines: list[str] = [
            f"用户共有 {total} 条阅读历史"
            f"（显示最近 {len(items)} 条）：\n"
        ]
        history_data: list[dict] = []
        for history, article_title in items:
            title = article_title or f"文章 #{history.article_id}"
            # 将秒数格式化为分钟，更易读。
            if history.duration_seconds:
                duration = f"{history.duration_seconds // 60} 分钟"
            else:
                duration = "未记录"
            lines.append(
                f"- {title} | 阅读次数: {history.read_count} | "
                f"时长: {duration} | 开始时间: {history.started_at}"
            )
            history_data.append(
                {
                    "article_id": history.article_id,
                    "article_title": title,
                    "read_count": history.read_count,
                    "duration_seconds": history.duration_seconds,
                    "started_at": str(history.started_at),
                }
            )

        return ToolResult(
            success=True,
            content="\n".join(lines),
            data={"total": total, "histories": history_data},
        )


class GetArticleContentTool(BaseTool):
    """获取文章内容。

    根据文章 ID 获取文章标题和正文。正文经过 :func:`truncate_for_context`
    截断以适应 LLM 的上下文窗口。
    """

    @property
    def name(self) -> str:
        return "get_article_content"

    @property
    def description(self) -> str:
        return (
            "获取文章的标题和正文内容。内容会自动截断以适应上下文窗口。"
            "当用户询问某篇文章的内容、或需要参考正在阅读的文章时使用。"
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="article_id",
                type="integer",
                description="文章的 ID",
                required=True,
            ),
        ]

    async def execute(self, **kwargs: Any) -> ToolResult:
        """执行文章内容查询。

        Args:
            **kwargs: 包含 ``db``、``user_id``（隐式注入）以及
                ``article_id``（显式参数）。

        Returns:
            :class:`ToolResult`，``content`` 为文章标题和截断后的正文，
            ``data`` 包含原始文章数据。
        """
        db: AsyncSession = kwargs["db"]
        user_id: int = kwargs["user_id"]
        article_id: int = kwargs.get("article_id", 0)

        article = await get_article_by_id(db, article_id)

        if article is None:
            return ToolResult(
                success=False,
                content=f"未找到 ID 为 {article_id} 的文章。",
            )

        truncated_content = truncate_for_context(article.content)

        lines = [
            f"文章标题: {article.title}",
            f"\n文章内容:\n{truncated_content}",
        ]

        data = {
            "article_id": article.id,
            "title": article.title,
            "content": truncated_content,
        }

        return ToolResult(
            success=True,
            content="\n".join(lines),
            data=data,
        )


class GetSentenceCollectionTool(BaseTool):
    """获取用户收藏的句子。

    返回用户收藏的句子列表，可选按关键词搜索。每条句子包含原文和个人备注。
    """

    @property
    def name(self) -> str:
        return "get_sentence_collection"

    @property
    def description(self) -> str:
        return (
            "获取用户收藏的句子，可选按关键词搜索。"
            "当用户询问收藏了哪些句子、想回顾某个表达时使用。"
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="search",
                type="string",
                description="可选的搜索关键词，用于过滤收藏的句子",
                required=False,
            ),
        ]

    async def execute(self, **kwargs: Any) -> ToolResult:
        """执行句子收藏查询。

        Args:
            **kwargs: 包含 ``db``、``user_id``（隐式注入）以及
                ``search``（可选显式参数）。

        Returns:
            :class:`ToolResult`，``content`` 为格式化的句子列表文本，
            ``data`` 包含原始句子数据。
        """
        db: AsyncSession = kwargs["db"]
        user_id: int = kwargs["user_id"]
        search: str = kwargs.get("search", "")

        # 去除首尾空白，空字符串转为 None（不过滤）。
        search_term = search.strip() if search and search.strip() else None

        items, total = await list_sentences(
            db, user_id, page=1, page_size=_SENTENCE_PAGE_SIZE,
            search=search_term,
        )

        if not items:
            search_hint = f"包含 '{search_term}' 的" if search_term else ""
            return ToolResult(
                success=True,
                content=f"未找到{search_hint}收藏句子。",
                data={"total": 0, "sentences": []},
            )

        search_hint = f"包含 '{search_term}' 的" if search_term else ""
        lines: list[str] = [
            f"找到 {total} 条{search_hint}收藏句子"
            f"（显示前 {len(items)} 条）：\n"
        ]
        sentence_data: list[dict] = []
        for s in items:
            note = s.note or "无备注"
            lines.append(f"- {s.sentence}")
            lines.append(f"  备注: {note}")
            sentence_data.append(
                {
                    "id": s.id,
                    "sentence": s.sentence,
                    "note": s.note,
                    "created_at": str(s.created_at),
                }
            )

        return ToolResult(
            success=True,
            content="\n".join(lines),
            data={"total": total, "sentences": sentence_data},
        )
