"""异步 Redis 客户端工具。

创建一个在应用范围内共享的 :class:`redis.asyncio.Redis` 客户端，并提供
``get_redis`` FastAPI 依赖。
"""

from collections.abc import AsyncGenerator

import redis.asyncio as redis

from app.core.config import settings

# 共享的异步 Redis 客户端，底层使用 hiredis 解析器以提升性能。
redis_client: redis.Redis = redis.from_url(
    settings.REDIS_URL,
    decode_responses=True,
    encoding="utf-8",
)


async def get_redis() -> AsyncGenerator[redis.Redis, None]:
    """产出共享 Redis 客户端的 FastAPI 依赖。

    客户端本身是一个长生命周期的连接池，因此直接产出，而不是按请求
    打开/关闭。
    """
    try:
        yield redis_client
    finally:
        # 连接会自动归还到连接池，无需关闭。
        pass


async def close_redis() -> None:
    """关闭 Redis 连接池（在应用关闭时调用）。"""
    await redis_client.aclose()
