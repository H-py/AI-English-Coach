"""提供方工厂。

返回已配置的 LLM 提供方实例。新的提供方在此处注册，无需改动业务代码。
"""

from functools import lru_cache

from app.core.ai.deepseek import DeepSeekProvider
from app.core.ai.provider import LLMProvider
from app.core.config import settings


@lru_cache
def get_llm_provider() -> LLMProvider:
    """返回已配置的 LLM 提供方单例。

    提供方依据 ``settings.AI_DEFAULT_PROVIDER`` 进行选择。结果通过
    :func:`lru_cache` 缓存，使同一个提供方实例在应用整个生命周期中被复用。

    Returns:
        与已配置提供方对应的 :class:`LLMProvider` 实现。

    Raises:
        ValueError: 若配置的提供方名称无法识别。
    """
    if settings.AI_DEFAULT_PROVIDER == "deepseek":
        return DeepSeekProvider()
    raise ValueError(f"Unknown AI provider: {settings.AI_DEFAULT_PROVIDER}")
