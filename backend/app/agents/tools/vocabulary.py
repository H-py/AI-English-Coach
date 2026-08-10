"""词汇收藏查询工具。

提供两个工具供 Agent 查询用户的词汇收藏数据：

- :class:`SearchVocabularyTool`：按关键词搜索用户收藏的单词。
- :class:`GetWordDetailTool`：获取单个收藏单词的详细信息。

这两个工具均通过 ``app.modules.reading.repository`` 中的函数访问
数据库，并由 :class:`~app.agents.base.BaseAgent` 注入 ``db`` 和
``user_id`` 作为隐式上下文参数。
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tools.base import BaseTool, ToolParameter, ToolResult
from app.modules.reading.repository import get_word, list_words


# AI 解释在返回给 LLM 时的最大字符数。
_EXPLANATION_MAX_CHARS = 100


class SearchVocabularyTool(BaseTool):
    """按关键词搜索用户收藏的单词。

    调用 :func:`list_words` 进行不区分大小写的模糊搜索，返回匹配的
    单词列表，包含掌握程度和 AI 解释（截断到 100 字符以内）。
    """

    @property
    def name(self) -> str:
        return "search_vocabulary"

    @property
    def description(self) -> str:
        return (
            "按关键词搜索用户收藏的单词，返回匹配的单词、掌握程度和 AI 解释。"
            "当用户询问某个单词是否已收藏、掌握程度如何时使用。"
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="keyword",
                type="string",
                description="要搜索的单词或关键词",
                required=True,
            ),
        ]

    async def execute(self, **kwargs: Any) -> ToolResult:
        """执行词汇搜索。

        Args:
            **kwargs: 包含 ``db``、``user_id``（隐式注入）以及
                ``keyword``（显式参数）。

        Returns:
            :class:`ToolResult`，``content`` 为格式化的单词列表文本，
            ``data`` 包含原始单词数据。
        """
        db: AsyncSession = kwargs["db"]
        user_id: int = kwargs["user_id"]
        keyword: str = kwargs.get("keyword", "")

        if not keyword or not keyword.strip():
            return ToolResult(
                success=False,
                content="搜索关键词不能为空。",
            )

        words, total = await list_words(
            db, user_id, page=1, page_size=20, search=keyword.strip()
        )

        if not words:
            return ToolResult(
                success=True,
                content=f"未找到包含 '{keyword}' 的收藏单词。",
                data={"total": 0, "words": []},
            )

        lines: list[str] = [
            f"找到 {total} 个匹配的收藏单词（显示前 {len(words)} 个）：\n"
        ]
        word_data: list[dict] = []
        for w in words:
            # 截断 AI 解释到 100 字符以内。
            explanation = w.ai_explanation or "暂无解释"
            if len(explanation) > _EXPLANATION_MAX_CHARS:
                explanation = explanation[:_EXPLANATION_MAX_CHARS] + "..."

            mastery = (
                w.mastery_level.value if w.mastery_level else "unknown"
            )
            lines.append(f"- {w.word} [掌握程度: {mastery}]")
            lines.append(f"  解释: {explanation}")
            word_data.append(
                {
                    "id": w.id,
                    "word": w.word,
                    "mastery_level": mastery,
                    "explanation": explanation,
                }
            )

        return ToolResult(
            success=True,
            content="\n".join(lines),
            data={"total": total, "words": word_data},
        )


class GetWordDetailTool(BaseTool):
    """获取单个收藏单词的详细信息。

    根据单词收藏记录的 ID 查询单词详情，包括上下文、AI 解释、
    掌握程度和学习次数。
    """

    @property
    def name(self) -> str:
        return "get_word_detail"

    @property
    def description(self) -> str:
        return (
            "获取单个收藏单词的详细信息，包括上下文、AI 解释、"
            "掌握程度和学习次数。当用户想了解某个单词的详细收藏信息时使用。"
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="word_id",
                type="integer",
                description="单词收藏记录的 ID",
                required=True,
            ),
        ]

    async def execute(self, **kwargs: Any) -> ToolResult:
        """执行单词详情查询。

        Args:
            **kwargs: 包含 ``db``、``user_id``（隐式注入）以及
                ``word_id``（显式参数）。

        Returns:
            :class:`ToolResult`，``content`` 为格式化的单词详情文本，
            ``data`` 包含原始单词数据。
        """
        db: AsyncSession = kwargs["db"]
        user_id: int = kwargs["user_id"]
        word_id: int = kwargs.get("word_id", 0)

        word = await get_word(db, user_id, word_id)

        if word is None:
            return ToolResult(
                success=False,
                content=f"未找到 ID 为 {word_id} 的收藏单词。",
            )

        mastery = (
            word.mastery_level.value if word.mastery_level else "unknown"
        )
        lines = [
            f"单词: {word.word}",
            f"掌握程度: {mastery}",
            f"学习次数: {word.study_count}",
            f"上下文: {word.context}",
            f"AI 解释: {word.ai_explanation or '暂无解释'}",
            f"收藏时间: {word.created_at}",
        ]

        data = {
            "id": word.id,
            "word": word.word,
            "mastery_level": mastery,
            "study_count": word.study_count,
            "context": word.context,
            "ai_explanation": word.ai_explanation,
            "created_at": str(word.created_at),
        }

        return ToolResult(
            success=True,
            content="\n".join(lines),
            data=data,
        )
