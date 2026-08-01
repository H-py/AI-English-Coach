"""Provider factory.

Returns the configured LLM provider instance. New providers are registered
here without touching business code.
"""

from functools import lru_cache

from app.core.ai.deepseek import DeepSeekProvider
from app.core.ai.provider import LLMProvider
from app.core.config import settings


@lru_cache
def get_llm_provider() -> LLMProvider:
    """Return the configured LLM provider singleton.

    The provider is selected based on ``settings.AI_DEFAULT_PROVIDER``.
    The result is cached with :func:`lru_cache` so that the same provider
    instance is reused across the application lifetime.

    Returns:
        The :class:`LLMProvider` implementation for the configured provider.

    Raises:
        ValueError: If the configured provider name is not recognised.
    """
    if settings.AI_DEFAULT_PROVIDER == "deepseek":
        return DeepSeekProvider()
    raise ValueError(f"Unknown AI provider: {settings.AI_DEFAULT_PROVIDER}")
