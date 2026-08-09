"""health 模块的 Pydantic schemas。"""

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """健康检查端点返回的载荷。"""

    status: str = Field(default="ok", description="Overall service status.")
    version: str | None = Field(default=None, description="Application version.")
