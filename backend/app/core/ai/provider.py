"""抽象 LLM 提供方接口。

所有 AI 提供方（DeepSeek、OpenAI、Claude 等）都实现此接口。业务代码只
依赖此抽象，而不依赖具体的提供方。
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ChatMessage:
    """聊天对话中的单条消息。"""

    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass
class LLMResponse:
    """非流式 LLM 响应。"""

    content: str
    model: str
    usage: dict[str, Any] = field(default_factory=dict)


class LLMProvider(ABC):
    """LLM 提供方的抽象基类。

    子类实现对特定 LLM 服务的实际 API 调用。业务模块只与此接口交互，
    使得提供方可以在不影响业务逻辑的情况下被替换。
    """

    @property
    @abstractmethod
    def model(self) -> str:
        """当前提供方使用的模型名（用于缓存键区分与展示）。"""
        ...

    @abstractmethod
    async def chat(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """发送聊天请求并返回完整响应。"""
        ...

    @abstractmethod
    async def chat_stream(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> AsyncGenerator[str, None]:
        """发送聊天请求并产出响应分块（SSE 流式）。"""
        ...
        yield ""  # 用于类型检查的占位符
