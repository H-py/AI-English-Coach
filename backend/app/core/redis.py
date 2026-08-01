"""Async Redis client utilities.

Creates a single :class:`redis.asyncio.Redis` client shared across the
application and exposes a ``get_redis`` FastAPI dependency.
"""

from collections.abc import AsyncGenerator

import redis.asyncio as redis

from app.core.config import settings

# Shared async Redis client backed by the hiredis parser for performance.
redis_client: redis.Redis = redis.from_url(
    settings.REDIS_URL,
    decode_responses=True,
    encoding="utf-8",
)


async def get_redis() -> AsyncGenerator[redis.Redis, None]:
    """FastAPI dependency that yields the shared Redis client.

    The client itself is a long-lived connection pool, so it is yielded
    directly rather than opened/closed per request.
    """
    try:
        yield redis_client
    finally:
        # Connections are returned to the pool automatically; nothing to close.
        pass


async def close_redis() -> None:
    """Close the Redis connection pool (called on application shutdown)."""
    await redis_client.aclose()
