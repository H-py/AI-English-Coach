"""词汇收藏查询工具。

提供三个工具供 Agent 查询用户的词汇收藏数据：

- :class:`SearchVocabularyTool`：按关键词搜索用户收藏的单词。
- :class:`GetWordDetailTool`：获取单个收藏单词的详细信息。
- :class:`GetAllVocabularyTool`：获取用户全部收藏单词（按掌握程度分组）。

这三个工具均通过 ``app.modules.reading.repository`` 中的函数访问
数据库，并由 :class:`~app.agents.base.BaseAgent` 注入 ``db`` 和
``user_id`` 作为隐式上下文参数。
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tools.base import BaseTool, ToolParameter, ToolResult
from app.modules.reading.models import MasteryLevel
from app.modules.reading.repository import get_word, list_words


# AI 解释在返回给 LLM 时的最大字符数。
_EXPLANATION_MAX_CHARS = 100

# 获取全部单词时的最大返回数量，避免 token 溢出。
_MAX_WORDS_RETURN = 200


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


class GetAllVocabularyTool(BaseTool):
    """获取用户全部收藏单词（按掌握程度分组）。

    调用 :func:`list_words` 分页获取用户所有收藏单词，按掌握程度
    （new / learning / familiar / mastered）分组返回。当用户询问
    "我都收藏了哪些单词"、"帮我制定背诵计划"时使用此工具获取完整
    的词汇列表，Agent 可据此生成个性化的学习建议。
    """

    @property
    def name(self) -> str:
        return "get_all_vocabulary"

    @property
    def description(self) -> str:
        return (
            "获取用户全部收藏单词，按掌握程度（new/learning/familiar/mastered）"
            "分组返回，包含单词、学习次数。当用户询问收藏了哪些单词、"
            "需要背诵计划或学习建议时使用。"
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="mastery_level",
                type="string",
                description=(
                    "可选，按掌握程度过滤。可选值："
                    "new（生词）、learning（学习中）、"
                    "familiar（熟悉）、mastered（已掌握）。"
                    "不传则返回全部。"
                ),
                required=False,
            ),
        ]

    async def execute(self, **kwargs: Any) -> ToolResult:
        """执行全部词汇查询。

        Args:
            **kwargs: 包含 ``db``、``user_id``（隐式注入）以及
                可选的 ``mastery_level``（显式参数）。

        Returns:
            :class:`ToolResult`，``content`` 为按掌握程度分组的
            单词列表文本，``data`` 包含分组统计和原始单词数据。
        """
        db: AsyncSession = kwargs["db"]
        user_id: int = kwargs["user_id"]
        mastery_filter: str | None = kwargs.get("mastery_level")

        # 解析可选的掌握程度过滤。
        level: MasteryLevel | None = None
        if mastery_filter:
            try:
                level = MasteryLevel(mastery_filter.strip().lower())
            except ValueError:
                return ToolResult(
                    success=False,
                    content=(
                        f"无效的掌握程度 '{mastery_filter}'。"
                        f"可选值：new、learning、familiar、mastered。"
                    ),
                )

        # 分页获取全部单词（单次最多 _MAX_WORDS_RETURN 条）。
        words, total = await list_words(
            db,
            user_id,
            page=1,
            page_size=_MAX_WORDS_RETURN,
            mastery_level=level,
        )

        if not words:
            if level:
                return ToolResult(
                    success=True,
                    content=f"用户没有掌握程度为 '{level.value}' 的收藏单词。",
                    data={"total": 0, "groups": {}},
                )
            return ToolResult(
                success=True,
                content="用户还没有收藏任何单词。",
                data={"total": 0, "groups": {}},
            )

        # 按掌握程度分组。
        groups: dict[str, list[dict]] = {
            "new": [],
            "learning": [],
            "familiar": [],
            "mastered": [],
        }
        for w in words:
            mastery = w.mastery_level.value if w.mastery_level else "unknown"
            if mastery not in groups:
                groups[mastery] = []
            groups[mastery].append(
                {
                    "id": w.id,
                    "word": w.word,
                    "mastery_level": mastery,
                    "study_count": w.study_count,
                }
            )

        # 构建给 LLM 阅读的文本摘要。
        lines: list[str] = [
            f"用户共收藏 {total} 个单词"
            + (f"（掌握程度: {level.value}）" if level else "")
            + f"，本次返回 {len(words)} 个：\n",
        ]

        level_labels = {
            "new": "生词（new）",
            "learning": "学习中（learning）",
            "familiar": "熟悉（familiar）",
            "mastered": "已掌握（mastered）",
        }

        for level_key, label in level_labels.items():
            group_words = groups.get(level_key, [])
            if not group_words:
                continue
            word_list = ", ".join(
                f"{w['word']}(学习{w['study_count']}次)"
                for w in group_words
            )
            lines.append(
                f"\n【{label}】共 {len(group_words)} 个：\n{word_list}"
            )

        # 处理 unknown 分组（理论不应出现，兜底）。
        unknown_words = groups.get("unknown", [])
        if unknown_words:
            word_list = ", ".join(w["word"] for w in unknown_words)
            lines.append(
                f"\n【未知状态】共 {len(unknown_words)} 个：\n{word_list}"
            )

        # 添加分组统计摘要。
        summary_parts = [
            f"{label}: {len(groups.get(k, []))}个"
            for k, label in level_labels.items()
            if groups.get(k)
        ]
        if summary_parts:
            lines.append(f"\n统计：{'，'.join(summary_parts)}")

        return ToolResult(
            success=True,
            content="\n".join(lines),
            data={
                "total": total,
                "returned": len(words),
                "groups": {
                    k: v for k, v in groups.items() if v
                },
            },
        )
