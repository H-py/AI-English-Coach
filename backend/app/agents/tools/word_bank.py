"""分级词库查询工具。

提供 :class:`LookupWordLevelTool`，让 Agent 查询某个单词在分级词库
（四级 / 六级 / 考研）中的归属等级与词库释义。词库为只读参考数据，
由 ``app.modules.word_bank.repository`` 提供访问。
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tools.base import BaseTool, ToolParameter, ToolResult
from app.modules.word_bank.labels import WORD_LEVEL_LABELS
from app.modules.word_bank.repository import lookup_word


class LookupWordLevelTool(BaseTool):
    """查询单词在分级词库中的归属等级与中文释义。

    当用户询问某个单词属于哪个词汇等级（如"这是四级词汇吗"）、
    是否收录于四级/六级/考研词表，或想了解词库释义时使用。
    """

    @property
    def name(self) -> str:
        return "lookup_word_level"

    @property
    def description(self) -> str:
        return (
            "查询某个单词在分级词库（四级/六级/考研）中的归属等级与中文释义。"
            "当用户询问单词属于哪个词汇等级、是否是四级/六级/考研词汇，"
            "或想了解词库释义时使用。"
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="word",
                type="string",
                description="要查询的单词",
                required=True,
            ),
        ]

    async def execute(self, **kwargs: Any) -> ToolResult:
        """执行词库查询。

        Args:
            **kwargs: 包含 ``db``、``user_id``（隐式注入）以及
                ``word``（显式参数）。

        Returns:
            :class:`ToolResult`，``content`` 为给 LLM 阅读的等级与释义文本，
            ``data`` 包含结构化的词库信息。
        """
        db: AsyncSession = kwargs["db"]
        word: str = kwargs.get("word", "")

        if not word or not word.strip():
            return ToolResult(
                success=False,
                content="查询单词不能为空。",
            )

        info = await lookup_word(db, word)
        if info is None or not info["levels"]:
            return ToolResult(
                success=True,
                content=f"分级词库中未收录 '{word}'，暂无等级标注。",
                data={"word": word, "levels": [], "found": False},
            )

        labels = "、".join(
            WORD_LEVEL_LABELS.get(lv, lv) for lv in info["levels"]
        )
        lines = [
            f"单词: {info['word']}",
            f"词汇等级: {labels}",
        ]
        if info["phonetic"]:
            lines.append(f"音标: {info['phonetic']}")
        if info["meaning"]:
            lines.append(f"词库释义: {info['meaning']}")

        return ToolResult(
            success=True,
            content="\n".join(lines),
            data={
                "word": info["word"],
                "levels": info["levels"],
                "phonetic": info["phonetic"],
                "meaning": info["meaning"],
                "found": True,
            },
        )
