"""记忆检索工具。

提供工具供 Agent 检索用户的长期记忆（摘要、事实、错误、偏好），
使 Agent 能够参考用户过去的学习情况给出更个性化的回答。

通过 ``app.modules.ai.memory_repository`` 中的函数访问记忆数据，
并由 :class:`~app.agents.base.BaseAgent` 注入 ``db`` 和 ``user_id``
作为隐式上下文参数。
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tools.base import BaseTool, ToolParameter, ToolResult
from app.modules.ai.memory_repository import get_active_memories

# 记忆加载的最大 token 预算。
_MEMORY_MAX_TOKENS = 2000

# 记忆类型中文标签映射。
_MEMORY_TYPE_LABELS: dict[str, str] = {
    "summary": "摘要",
    "fact": "事实",
    "mistake": "错误",
    "preference": "偏好",
}


class SearchMemoriesTool(BaseTool):
    """搜索用户的长期记忆。

    加载用户的全局激活记忆，并按关键词过滤内容。返回匹配的记忆条目，
    包含记忆类型和内容。若不提供关键词，则返回所有记忆。
    """

    @property
    def name(self) -> str:
        return "search_memories"

    @property
    def description(self) -> str:
        return (
            "搜索用户的长期记忆（摘要、事实、错误、偏好）。"
            "当需要回顾用户过去的学习情况、常见错误或偏好时使用。"
            "可提供关键词进行过滤，不提供关键词则返回所有记忆。"
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="keyword",
                type="string",
                description="可选的搜索关键词，用于过滤记忆内容",
                required=False,
            ),
        ]

    async def execute(self, **kwargs: Any) -> ToolResult:
        """执行记忆检索。

        先通过 :func:`get_active_memories` 加载用户的全局激活记忆
        （按重要性排序），再在 Python 中按关键词进行不区分大小写的
        内容过滤。

        Args:
            **kwargs: 包含 ``db``、``user_id``（隐式注入）以及
                ``keyword``（可选显式参数）。

        Returns:
            :class:`ToolResult`，``content`` 为格式化的记忆列表文本，
            ``data`` 包含原始记忆数据。
        """
        db: AsyncSession = kwargs["db"]
        user_id: int = kwargs["user_id"]
        keyword: str = kwargs.get("keyword", "")

        # 规范化关键词：去除首尾空白并转小写，用于不区分大小写的匹配。
        keyword_lower = keyword.strip().lower() if keyword else ""

        memories = await get_active_memories(
            db, user_id, max_tokens=_MEMORY_MAX_TOKENS
        )

        if not memories:
            return ToolResult(
                success=True,
                content="用户还没有任何长期记忆记录。",
                data={"total": 0, "memories": []},
            )

        # 按关键词过滤记忆内容。
        if keyword_lower:
            filtered = [
                m for m in memories if keyword_lower in m.content.lower()
            ]
        else:
            filtered = memories

        if not filtered:
            return ToolResult(
                success=True,
                content=f"未找到包含 '{keyword}' 的记忆。",
                data={"total": 0, "memories": [], "keyword": keyword},
            )

        lines: list[str] = [f"找到 {len(filtered)} 条记忆：\n"]
        memory_data: list[dict] = []
        for m in filtered:
            type_label = _MEMORY_TYPE_LABELS.get(
                m.memory_type, m.memory_type
            )
            lines.append(f"- [{type_label}] (重要度: {m.importance:.1f})")
            lines.append(f"  {m.content}")
            memory_data.append(
                {
                    "memory_type": m.memory_type,
                    "content": m.content,
                    "importance": m.importance,
                }
            )

        return ToolResult(
            success=True,
            content="\n".join(lines),
            data={"total": len(filtered), "memories": memory_data},
        )
