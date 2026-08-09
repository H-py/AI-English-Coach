"""基于 pydantic-settings 的应用配置。

所有环境变量均从进程环境中读取（当 ``backend/.env`` 文件存在时也从中读取）。
:class:`Settings` 实例是整个后端配置的唯一可信来源。
"""

from functools import lru_cache
from typing import List, Union

from pydantic import AnyHttpUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """强类型应用配置。

    属性与 ``backend/.env.example`` 中记录的变量一一对应。
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- 应用 ----
    APP_NAME: str = "AI Reading Coach"
    APP_ENV: str = "development"
    APP_DEBUG: bool = True
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000

    # ---- 数据库 ----
    DATABASE_URL: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/ai_reading_coach"
    )

    # ---- Redis ----
    REDIS_URL: str = "redis://localhost:6379/0"

    # ---- MinIO ----
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "ai-reading-coach"
    MINIO_SECURE: bool = False

    # ---- AI ----
    AI_DEFAULT_PROVIDER: str = "deepseek"
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = "deepseek-chat"

    # ---- JWT ----
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ---- 管理员（用于初始化脚本的初始管理员账号）----
    ADMIN_EMAIL: str = "admin@example.com"
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin123456"

    # ---- CORS ----
    # 接受环境变量中以逗号分隔的来源列表。
    CORS_ORIGINS: Union[str, List[str]] = ["http://localhost:5173"]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> List[str]:
        """允许 ``CORS_ORIGINS`` 在环境变量中以逗号分隔的字符串形式提供。"""
        if isinstance(value, str) and not value.startswith("["):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value  # type: ignore[return-value]

    @property
    def is_production(self) -> bool:
        """判断应用是否以生产模式运行。"""
        return self.APP_ENV == "production"


@lru_cache
def get_settings() -> Settings:
    """返回缓存的 :class:`Settings` 单例。"""
    return Settings()


settings = get_settings()
