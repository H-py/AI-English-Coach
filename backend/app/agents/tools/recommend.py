"""个性化文章推荐专用的数据获取工具。

这些工具供 :class:`~app.agents.recommender.ArticleRecommender` 调用，
只负责从数据库取数并渲染成 LLM 可读文本（``content``）与结构化数据
（``data``），不包含任何 AI 决策逻辑。

- :class:`ListArticlesTool`：获取分层采样的候选文章清单（含难度/标签/摘要）。
- :class:`GetReadArticleDifficultyTool`：获取用户最近阅读文章及难度。

推荐 Agent 调用这些工具收集上下文，再把上下文喂给单次 LLM 调用。
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tools.base import BaseTool, ToolParameter, ToolResult
from app.modules.article.repository import list_articles_for_recommendation
from app.modules.reading.repository import get_read_article_difficulties

# 候选文章上限（token 预算）。
RECOMMEND_CATALOG_CAP = 60
# 阅读历史参与推荐的条数。
RECOMMEND_HISTORY_LIMIT = 20


def _serialize_article(article) -> dict:
    """把 ORM Article 序列化为 ArticleListItem 所需字段的字典。"""
    return {
        "id": article.id,
        "title": article.title,
        "summary": article.summary,
        "difficulty": article.difficulty.value,
        "cet_type": article.cet_type,
        "word_count": article.word_count,
        "reading_time": article.reading_time,
        "cover_url": article.cover_url,
        "tags": article.tags,
        "created_at": str(article.created_at),
    }


class ListArticlesTool(BaseTool):
    """获取分层采样的候选文章清单（含难度 / 标签 / 摘要）。"""

    @property
    def name(self) -> str:
        return "list_articles"

    @property
    def description(self) -> str:
        return (
            "获取用于推荐的候选文章清单，包含文章标题、难度星级、标签和摘要。"
            "当需要为用户推荐文章、按难度挑选文章时使用。"
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return []

    async def execute(self, **kwargs: Any) -> ToolResult:
        """执行候选文章查询。

        Args:
            **kwargs: 包含 ``db``、``user_id``（隐式注入），无显式参数。

        Returns:
            :class:`ToolResult`，``content`` 为候选文章清单文本，
            ``data`` 包含每篇序列化后的文章字典。
        """
        db: AsyncSession = kwargs["db"]

        catalog = await list_articles_for_recommendation(
            db, RECOMMEND_CATALOG_CAP
        )
        if not catalog:
            return ToolResult(
                success=True,
                content="当前没有可推荐的文章。",
                data={"articles": []},
            )

        lines: list[str] = [f"共 {len(catalog)} 篇候选文章：\n"]
        articles: list[dict] = []
        for article in catalog:
            tags = "、".join(article.tags[:3]) or "无标签"
            summary = (article.summary or "")[:50]
            lines.append(
                f"{article.id}. {article.title}"
                f"（难度{article.difficulty.value}星）[{tags}] 摘要：{summary}"
            )
            articles.append(_serialize_article(article))

        return ToolResult(
            success=True,
            content="\n".join(lines),
            data={"articles": articles},
        )


class GetReadArticleDifficultyTool(BaseTool):
    """获取用户最近阅读的文章及其难度星级。"""

    @property
    def name(self) -> str:
        return "get_read_article_difficulty"

    @property
    def description(self) -> str:
        return (
            "获取用户最近阅读的文章及其难度星级。"
            "当需要了解用户读过的文章难度、判断已读/未读以做个性化推荐时使用。"
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return []

    async def execute(self, **kwargs: Any) -> ToolResult:
        """执行已读文章难度查询。

        Args:
            **kwargs: 包含 ``db``、``user_id``（隐式注入），无显式参数。

        Returns:
            :class:`ToolResult`，``content`` 为阅读历史难度文本，
            ``data`` 包含 ``read_articles`` 列表。
        """
        db: AsyncSession = kwargs["db"]
        user_id: int = kwargs["user_id"]

        read_diffs = await get_read_article_difficulties(
            db, user_id, limit=RECOMMEND_HISTORY_LIMIT
        )
        if not read_diffs:
            return ToolResult(
                success=True,
                content="该用户暂无阅读历史。",
                data={"read_articles": []},
            )

        lines: list[str] = [
            f"该用户最近读过 {len(read_diffs)} 篇文章（难度星级）："
        ]
        lines += [
            f"- {title}（{diff.value}星）" for _, title, diff in read_diffs
        ]

        return ToolResult(
            success=True,
            content="\n".join(lines),
            data={
                "read_articles": [
                    {
                        "article_id": aid,
                        "title": title,
                        "difficulty": diff.value,
                    }
                    for aid, title, diff in read_diffs
                ]
            },
        )
