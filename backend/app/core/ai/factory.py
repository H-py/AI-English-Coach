"""提供方工厂。

返回已配置的 LLM 提供方实例。新的提供方在此处注册，无需改动业务代码。

除全局默认提供方外，还提供按用户解析的
:func:`get_llm_provider_for_user`：当用户配置了自定义模型（且启用）时，
返回用户自己的提供方实例；否则回落全局默认提供方。**刻意不在**调用失败
时静默回退到默认模型——用户配置的模型出错应透出给用户。
"""

from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai.crypto import decrypt_api_key
from app.core.ai.deepseek import DeepSeekProvider
from app.core.ai.provider import LLMProvider
from app.core.config import settings
from app.modules.llm_config.repository import get_active_config


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


def build_deepseek_provider(
    api_key: str,
    base_url: str,
    model: str,
) -> DeepSeekProvider:
    """按显式参数构造一个用户配置来源的提供方实例。

    供连接测试等场景复用，使错误按用户配置语义（错误码 ``50004``）透出。
    """
    return DeepSeekProvider(
        api_key=api_key,
        base_url=base_url,
        model=model,
        from_user_config=True,
    )


async def get_llm_provider_for_user(
    db: AsyncSession, user_id: int
) -> LLMProvider:
    """按用户解析 LLM 提供方。

    用户存在已激活（使用中）的自定义配置时，返回基于该配置构造的提供方
    实例；否则返回全局默认提供方。用户配置的模型在调用时若出错，错误会
    以错误码 ``50004`` 透出，**不会**静默回退到默认模型。

    Args:
        db: 当前活跃的异步会话。
        user_id: 用户的 id。

    Returns:
        用户级或全局默认的 :class:`LLMProvider`。
    """
    config = await get_active_config(db, user_id)
    if config is not None:
        return DeepSeekProvider(
            api_key=decrypt_api_key(config.api_key),
            base_url=config.base_url,
            model=config.model,
            from_user_config=True,
        )
    return get_llm_provider()
