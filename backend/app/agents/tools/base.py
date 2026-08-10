"""Agent 工具基类与注册表。

每个工具是一个可被 Agent 调用的异步函数，具有明确的名称、描述和
参数 schema。Agent 通过 ReAct 提示词中的 ``Action`` 声明要调用哪个
工具，系统侧解析后执行对应工具并将结果作为 ``Observation`` 返回
给 Agent。

工具的 ``execute`` 方法接收 ``db`` 和 ``user_id`` 作为隐式上下文
参数（由 Agent 执行循环注入），以及 LLM 解析出的显式参数。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolParameter:
    """工具参数描述。

    用于生成 ReAct 提示词中的工具签名，让 LLM 了解每个参数的
   类型和是否必填。
    """

    name: str
    type: str  # "string" | "integer" | "boolean"
    description: str
    required: bool = True
    default: Any = None


@dataclass
class ToolResult:
    """工具执行结果。

    Attributes:
        success: 执行是否成功。
        content: 返回给 LLM 的文本（作为 Observation）。
        data: 原始数据字典，用于前端展示（不发送给 LLM）。
    """

    success: bool
    content: str
    data: dict = field(default_factory=dict)


class BaseTool(ABC):
    """工具抽象基类。

    子类需实现 :attr:`name`、:attr:`description`、:attr:`parameters`
    和 :meth:`execute`。工具通过 :attr:`name` 在 ReAct 提示词中被
    引用，通过 :attr:`description` 让 LLM 理解何时使用。
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """工具的唯一标识名（snake_case）。"""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """工具功能描述（给 LLM 看的，应清晰说明何时使用）。"""
        ...

    @property
    @abstractmethod
    def parameters(self) -> list[ToolParameter]:
        """工具参数列表。"""
        ...

    @abstractmethod
    async def execute(self, **kwargs: Any) -> ToolResult:
        """执行工具逻辑。

        Args:
            **kwargs: 包含 ``db``（AsyncSession）、``user_id``（int）
                以及与 :attr:`parameters` 对应的显式参数。

        Returns:
            :class:`ToolResult` 包含文本结果和原始数据。
        """
        ...

    def to_prompt_string(self) -> str:
        """将工具描述格式化为 ReAct 提示词中的文本块。"""
        params_str = ", ".join(
            f'{p.name}: {p.type}'
            + (" (必填)" if p.required else " (可选)")
            for p in self.parameters
        )
        return f"- {self.name}({params_str}): {self.description}"


class ToolRegistry:
    """工具注册表，管理可用工具的注册与查找。"""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """注册一个工具实例。"""
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        """按名称查找工具，未找到返回 ``None``。"""
        return self._tools.get(name)

    def all_tools(self) -> list[BaseTool]:
        """返回所有已注册的工具列表。"""
        return list(self._tools.values())

    def to_prompt_string(self) -> str:
        """将所有工具格式化为 ReAct 提示词中的可用工具列表。"""
        return "\n".join(t.to_prompt_string() for t in self._tools.values())
