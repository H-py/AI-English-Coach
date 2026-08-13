"""用户自定义大模型配置的 HTTP 路由。

提供模型配置的增删改查与使用状态管理，全部限定在已认证用户范围内：

* ``GET /llm-config``            —— 列出用户的全部模型配置及当前激活 id。
* ``POST /llm-config``           —— 新增一条模型配置（首个自动激活）。
* ``PUT /llm-config/{id}``       —— 更新配置（空 Key 保留原值）。
* ``DELETE /llm-config/{id}``    —— 删除配置。
* ``POST /llm-config/{id}/activate`` —— 把该配置设为当前使用中的模型。
* ``POST /llm-config/deactivate``    —— 停用全部配置，回到默认模型。
* ``POST /llm-config/test``      —— 用指定配置（或内联值）测试连通性。
"""

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.core.response import ResponseModel, success
from app.modules.llm_config.schemas import (
    LlmConfigListOut,
    LlmConfigTestRequest,
    LlmConfigTestResponse,
    UserLlmConfigCreate,
    UserLlmConfigOut,
    UserLlmConfigUpdate,
)
from app.modules.llm_config.service import (
    activate_config,
    create_config,
    deactivate_all,
    delete_config,
    list_configs,
    test_config,
    update_config,
)

router = APIRouter(prefix="/llm-config", tags=["llm-config"])


@router.get("", response_model=ResponseModel[LlmConfigListOut])
async def get_my_llm_configs(
    db: DbSession, current_user: CurrentUser
) -> dict:
    """返回当前用户的全部模型配置及当前激活的配置 id。"""
    return success(await list_configs(db, current_user.id))


@router.post("", response_model=ResponseModel[UserLlmConfigOut])
async def create_my_llm_config(
    data: UserLlmConfigCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """新增一条模型配置（用户的首个配置会自动激活）。"""
    return success(await create_config(db, current_user.id, data))


@router.put("/{config_id}", response_model=ResponseModel[UserLlmConfigOut])
async def update_my_llm_config(
    config_id: int,
    data: UserLlmConfigUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """更新指定模型配置；``api_key`` 为空则保留已保存的密钥。"""
    return success(await update_config(db, current_user.id, config_id, data))


@router.delete("/{config_id}", response_model=ResponseModel[dict])
async def delete_my_llm_config(
    config_id: int,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """删除指定模型配置；若其为激活配置，则调用回落到默认模型。"""
    await delete_config(db, current_user.id, config_id)
    return success({"ok": True})


@router.post("/{config_id}/activate", response_model=ResponseModel[UserLlmConfigOut])
async def activate_my_llm_config(
    config_id: int,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """把指定配置设为当前使用中的模型。"""
    return success(await activate_config(db, current_user.id, config_id))


@router.post("/deactivate", response_model=ResponseModel[dict])
async def deactivate_my_llm_configs(
    db: DbSession, current_user: CurrentUser
) -> dict:
    """停用全部配置，恢复使用默认模型。"""
    await deactivate_all(db, current_user.id)
    return success({"ok": True})


@router.post("/test", response_model=ResponseModel[LlmConfigTestResponse])
async def test_my_llm_config(
    data: LlmConfigTestRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """用指定配置（或内联值）发起一次极简调用验证连通性。"""
    return success(await test_config(db, current_user.id, data))
