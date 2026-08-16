"""llm_config 模块的业务逻辑层。

负责领域规则：API Key 的加密/掩码、部分更新的语义（空 Key 保留原值、
旧明文自动重加密）、"首个配置自动激活"、以及连接测试时"已存配置值 >
内联覆盖 > 默认配置"的取值优先级。
"""
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai.crypto import (
    decrypt_api_key,
    encrypt_api_key,
    mask_api_key,
)
from app.core.ai.factory import build_deepseek_provider
from app.core.ai.provider import ChatMessage
from app.core.config import settings
from app.core.exceptions import BizException, CODE_VALIDATION_ERROR
from app.modules.llm_config import repository as repo
from app.modules.llm_config.models import UserLlmConfig
from app.modules.llm_config.schemas import (
    LlmConfigListOut,
    LlmConfigTestRequest,
    LlmConfigTestResponse,
    UserLlmConfigCreate,
    UserLlmConfigOut,
    UserLlmConfigUpdate,
)

CONFIG_NOT_FOUND_CODE = 90007


def _to_out(config: UserLlmConfig) -> UserLlmConfigOut:
    """将 ORM 配置转换为只含掩码 Key 的输出模式。"""
    return UserLlmConfigOut(
        id=config.id,
        user_id=config.user_id,
        provider_name=config.provider_name,
        base_url=config.base_url,
        model=config.model,
        masked_api_key=mask_api_key(decrypt_api_key(config.api_key)),
        is_active=config.is_active,
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


async def _get_or_raise(
    db: AsyncSession, config_id: int, user_id: int
) -> UserLlmConfig:
    """按 id + user_id 取配置，不存在时抛业务异常。"""
    config = await repo.get_config(db, config_id, user_id)
    if config is None:
        raise BizException("模型配置不存在", code=CONFIG_NOT_FOUND_CODE)
    return config


async def list_configs(
    db: AsyncSession, user_id: int
) -> LlmConfigListOut:
    """返回用户的全部模型配置及当前激活的配置 id。"""
    configs = await repo.list_configs(db, user_id)
    active = await repo.get_active_config(db, user_id)
    return LlmConfigListOut(
        items=[_to_out(c) for c in configs],
        active_id=active.id if active else None,
    )


async def create_config(
    db: AsyncSession, user_id: int, data: UserLlmConfigCreate
) -> UserLlmConfigOut:
    """创建一条模型配置；用户的首个配置会自动激活。"""
    existing_count = await repo.count_configs(db, user_id)
    is_active = existing_count == 0

    api_key = encrypt_api_key(data.api_key) if data.api_key else ""
    config = await repo.create_config(
        db,
        user_id,
        {
            "provider_name": data.provider_name.strip(),
            "base_url": data.base_url.strip().rstrip("/"),
            "model": data.model.strip(),
            "api_key": api_key,
        },
        is_active=is_active,
    )
    return _to_out(config)


async def update_config(
    db: AsyncSession,
    user_id: int,
    config_id: int,
    data: UserLlmConfigUpdate,
) -> UserLlmConfigOut:
    """更新配置字段；``api_key`` 为空保留原值（旧明文自动重加密）。"""
    config = await _get_or_raise(db, config_id, user_id)

    update_data = data.model_dump(exclude_unset=True)
    api_key_raw = update_data.pop("api_key", None)

    if api_key_raw:
        update_data["api_key"] = encrypt_api_key(api_key_raw)
    elif config.api_key and not config.api_key.startswith("gAAAA"):
        update_data["api_key"] = encrypt_api_key(config.api_key)

    if "base_url" in update_data:
        update_data["base_url"] = update_data["base_url"].strip().rstrip("/")
    if "model" in update_data:
        update_data["model"] = update_data["model"].strip()
    if "provider_name" in update_data:
        update_data["provider_name"] = update_data["provider_name"].strip()

    config = await repo.update_config(db, config, update_data)
    return _to_out(config)


async def delete_config(
    db: AsyncSession, user_id: int, config_id: int
) -> bool:
    """删除一条配置；若其为激活配置，则调用回落到默认模型。"""
    config = await _get_or_raise(db, config_id, user_id)
    await repo.delete_config(db, config)
    return True


async def activate_config(
    db: AsyncSession, user_id: int, config_id: int
) -> UserLlmConfigOut:
    """把指定配置设为当前使用中的模型。"""
    config = await repo.activate_config(db, config_id, user_id)
    if config is None:
        raise BizException("模型配置不存在", code=CONFIG_NOT_FOUND_CODE)
    return _to_out(config)


async def deactivate_all(db: AsyncSession, user_id: int) -> None:
    """停用全部配置，恢复使用默认模型。"""
    await repo.deactivate_all(db, user_id)


async def test_config(
    db: AsyncSession, user_id: int, data: LlmConfigTestRequest
) -> LlmConfigTestResponse:
    """用指定配置（或内联值）发起一次极简调用验证连通性。

    取值优先级：``config_id`` 指定的已存配置 > 请求内联值 > 默认配置；
    ``api_key`` 由内联值 > 已存配置（解密）> 默认配置决定。失败时抛出
    带具体原因的 :class:`BizException`（错误码 ``50004``）。
    """
    saved: Optional[UserLlmConfig] = None
    if data.config_id is not None:
        saved = await repo.get_config(db, data.config_id, user_id)

    base_url = (
        data.base_url
        or (saved.base_url if saved else None)
        or settings.DEEPSEEK_BASE_URL
    )
    model = (
        data.model
        or (saved.model if saved else None)
        or settings.DEEPSEEK_MODEL
    )
    api_key = data.api_key
    if not api_key and saved is not None and saved.api_key:
        api_key = decrypt_api_key(saved.api_key)
    if not api_key:
        api_key = settings.DEEPSEEK_API_KEY

    provider = build_deepseek_provider(
        api_key=api_key, base_url=base_url, model=model
    )
    await provider.chat(
        messages=[ChatMessage("user", "ping")],
        temperature=0,
        max_tokens=8,
    )
    return LlmConfigTestResponse(ok=True, model=provider.model)
