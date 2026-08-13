"""llm_config 模块的 Pydantic 模式（schema）。

描述用户自定义模型配置端点的传输结构：读取表示（``UserLlmConfigOut``，
只含掩码后的 API Key）、创建/更新载荷、列表输出以及连接测试的请求/响应。

采用 Pydantic v2 风格，使用 ``model_config`` / ``ConfigDict``。
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _validate_base_url(value: Optional[str]) -> Optional[str]:
    if value is None:
        return value
    value = value.strip().rstrip("/")
    if not (value.startswith("http://") or value.startswith("https://")):
        raise ValueError("Base URL 必须以 http:// 或 https:// 开头")
    return value


class UserLlmConfigOut(BaseModel):
    """返回给客户端的模型配置表示。

    只暴露掩码后的 API Key（如 ``sk-****abcd``），绝不包含明文。
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    provider_name: str
    base_url: str
    model: str
    masked_api_key: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class UserLlmConfigCreate(BaseModel):
    """创建模型配置的载荷。"""

    provider_name: str = Field(default="", max_length=100)
    base_url: str
    model: str = Field(min_length=1, max_length=100)
    api_key: str = ""

    @field_validator("base_url")
    @classmethod
    def _validate_base_url(cls, value: str) -> str:
        return _validate_base_url(value) or value


class UserLlmConfigUpdate(BaseModel):
    """模型配置的部分更新载荷。

    ``api_key`` 为空或省略表示保留已保存的密钥；非空则覆盖。
    """

    provider_name: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    api_key: Optional[str] = None

    @field_validator("base_url")
    @classmethod
    def _validate_base_url(cls, value: Optional[str]) -> Optional[str]:
        return _validate_base_url(value)


class LlmConfigListOut(BaseModel):
    """用户的全部模型配置及当前激活的配置 id。"""

    items: list[UserLlmConfigOut]
    active_id: Optional[int] = None


class LlmConfigTestRequest(BaseModel):
    """连接测试请求。

    ``config_id`` 指定要测试的已存配置；``base_url`` / ``model`` /
    ``api_key`` 为可选的覆盖值（允许测试尚未保存的值）。未提供
    ``config_id`` 时，只使用给定的内联值（缺失的字段回落到默认配置）。
    """

    config_id: Optional[int] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    api_key: Optional[str] = None

    @field_validator("base_url")
    @classmethod
    def _validate_test_base_url(cls, value: Optional[str]) -> Optional[str]:
        return _validate_base_url(value)


class LlmConfigTestResponse(BaseModel):
    """连接测试结果。"""

    ok: bool
    model: str
