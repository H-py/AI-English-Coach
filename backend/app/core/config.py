"""Application configuration based on pydantic-settings.

All environment variables are read from the process environment (and the
``backend/.env`` file when present). The :class:`Settings` instance is the
single source of truth for configuration across the whole backend.
"""

from functools import lru_cache
from typing import List, Union

from pydantic import AnyHttpUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed application settings.

    Attributes mirror the variables documented in ``backend/.env.example``.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- Application ----
    APP_NAME: str = "AI Reading Coach"
    APP_ENV: str = "development"
    APP_DEBUG: bool = True
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000

    # ---- Database ----
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

    # ---- Admin (initial admin account for init script) ----
    ADMIN_EMAIL: str = "admin@example.com"
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin123456"

    # ---- CORS ----
    # Accepts a comma-separated list of origins in the env var.
    CORS_ORIGINS: Union[str, List[str]] = ["http://localhost:5173"]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> List[str]:
        """Allow ``CORS_ORIGINS`` to be a comma-separated string in the env."""
        if isinstance(value, str) and not value.startswith("["):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value  # type: ignore[return-value]

    @property
    def is_production(self) -> bool:
        """Whether the application runs in production mode."""
        return self.APP_ENV == "production"


@lru_cache
def get_settings() -> Settings:
    """Return a cached :class:`Settings` singleton."""
    return Settings()


settings = get_settings()
