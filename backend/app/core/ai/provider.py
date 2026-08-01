"""Abstract LLM provider interface.

All AI providers (DeepSeek, OpenAI, Claude, etc.) implement this interface.
Business code depends only on this abstraction, never on a specific provider.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ChatMessage:
    """A single message in a chat conversation."""

    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass
class LLMResponse:
    """Non-streaming LLM response."""

    content: str
    model: str
    usage: dict[str, Any] = field(default_factory=dict)


class LLMProvider(ABC):
    """Abstract base class for LLM providers.

    Subclasses implement the actual API calls to a specific LLM service.
    Business modules interact only with this interface, allowing providers
    to be swapped without touching business logic.
    """

    @abstractmethod
    async def chat(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Send a chat request and return the complete response."""
        ...

    @abstractmethod
    async def chat_stream(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> AsyncGenerator[str, None]:
        """Send a chat request and yield response chunks (SSE streaming)."""
        ...
        yield ""  # placeholder for type checking
