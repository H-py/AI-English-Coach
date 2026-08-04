"""AI response caching and token-budget utilities.

Three concerns live in this module:

1. **Redis caching** for deterministic AI endpoints (word explanation,
   sentence analysis, translation, paragraph summary). The same input
   always produces the same output, so we cache the *full* response and
   replay it as a single SSE chunk on cache hit — zero API cost.

   Cache key composition: ``ai:cache:{endpoint}:{level}:{input_hash}``
   - ``endpoint`` — ``explain-word`` / ``analyze-sentence`` / …
   - ``level``    — the user's English level (affects prompt output)
   - ``input_hash`` — SHA-256 of the primary input (word+context,
     sentence, or paragraph text)

   TTL: 24 hours. Cache misses fall through to the live LLM call; the
   streamed chunks are accumulated and stored after the stream completes.

2. **Profile & memory caching** for the three-layer memory system.
   User profiles and long-term memories are cached in Redis to avoid
   hitting the database on every chat request. Profiles have a 1-hour
   TTL; memories have a 30-minute TTL. Both are invalidated when the
   underlying data changes.

3. **Token estimation** for chat context budgeting. A rough heuristic
   (1 token ≈ 4 chars for English, ≈ 1.5 chars for Chinese) is used to
   decide whether the full article text fits inside the model's context
   window alongside the conversation history, and to truncate if needed.
"""

import hashlib
import json
from typing import Any, Optional

import redis.asyncio as aioredis

# Cache TTL: 24 hours in seconds.
CACHE_TTL = 86400
# Profile cache TTL: 1 hour.
PROFILE_CACHE_TTL = 3600
# Memory cache TTL: 30 minutes.
MEMORY_CACHE_TTL = 1800

# ---- DeepSeek context window constants -------------------------------------
# deepseek-chat has a 64K context window. We reserve room for the system
# prompt, conversation history, the user's new message, and the response.
_MODEL_CONTEXT_WINDOW = 64000
# Reserve tokens for system prompt + response generation.
_RESERVED_TOKENS = 2000
# Maximum tokens for article content inside the chat system prompt.
_MAX_ARTICLE_TOKENS = 4000


def _hash_input(*parts: str) -> str:
    """Return a short SHA-256 hex digest of the concatenated input parts.

    Args:
        *parts: String components that together identify a unique request.

    Returns:
        A 16-character hex string (first 8 bytes of the digest).
    """
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def cache_key(endpoint: str, level: str, *input_parts: str) -> str:
    """Build a Redis cache key for a deterministic AI request.

    Args:
        endpoint: The AI endpoint name, e.g. ``"explain-word"``.
        level: The user's English level (``"beginner"`` / …).
        *input_parts: The primary input values (word, context, sentence…).

    Returns:
        A Redis key string of the form ``ai:cache:{endpoint}:{level}:{hash}``.
    """
    return f"ai:cache:{endpoint}:{level}:{_hash_input(*input_parts)}"


async def get_cached_response(
    redis: aioredis.Redis, key: str
) -> Optional[str]:
    """Retrieve a cached full AI response from Redis.

    Args:
        redis: The shared async Redis client.
        key: The cache key produced by :func:`cache_key`.

    Returns:
        The cached response string, or ``None`` on cache miss.
    """
    return await redis.get(key)


async def set_cached_response(
    redis: aioredis.Redis, key: str, response: str
) -> None:
    """Store a full AI response in Redis with the standard TTL.

    Args:
        redis: The shared async Redis client.
        key: The cache key produced by :func:`cache_key`.
        response: The complete AI response text to cache.
    """
    await redis.set(key, response, ex=CACHE_TTL)


# ---- Profile & memory caching -----------------------------------------------


def profile_cache_key(user_id: int) -> str:
    """Build the Redis cache key for a user's profile.

    Args:
        user_id: The user's id.

    Returns:
        A Redis key string of the form ``ai:profile:{user_id}``.
    """
    return f"ai:profile:{user_id}"


async def get_cached_profile(
    redis: aioredis.Redis, user_id: int
) -> Optional[dict[str, Any]]:
    """Retrieve a cached user profile from Redis.

    Args:
        redis: The shared async Redis client.
        user_id: The user's id.

    Returns:
        The cached profile as a dict, or ``None`` on cache miss.
    """
    raw = await redis.get(profile_cache_key(user_id))
    if raw is None:
        return None
    return json.loads(raw)


async def set_cached_profile(
    redis: aioredis.Redis, user_id: int, profile: dict[str, Any]
) -> None:
    """Store a user profile in Redis with the profile TTL.

    Args:
        redis: The shared async Redis client.
        user_id: The user's id.
        profile: The profile data as a dict.
    """
    await redis.set(
        profile_cache_key(user_id),
        json.dumps(profile, ensure_ascii=False),
        ex=PROFILE_CACHE_TTL,
    )


async def invalidate_profile_cache(
    redis: aioredis.Redis, user_id: int
) -> None:
    """Delete the cached profile for a user.

    Called after a profile update to ensure the next request fetches
    fresh data from the database.

    Args:
        redis: The shared async Redis client.
        user_id: The user's id.
    """
    await redis.delete(profile_cache_key(user_id))


# ---- Global memories cache (article_id IS NULL) -----------------------------


def global_memories_cache_key(user_id: int) -> str:
    """Build the Redis cache key for a user's global (cross-article) memories.

    Global memories have ``article_id IS NULL`` and are shared across all
    articles. They are cached separately from article-specific memories so
    that updating one does not invalidate the other.

    Args:
        user_id: The user's id.

    Returns:
        A Redis key string of the form ``ai:memories:global:{user_id}``.
    """
    return f"ai:memories:global:{user_id}"


async def get_cached_global_memories(
    redis: aioredis.Redis, user_id: int
) -> Optional[list[dict[str, Any]]]:
    """Retrieve cached global memories from Redis.

    Args:
        redis: The shared async Redis client.
        user_id: The user's id.

    Returns:
        A list of memory dicts, or ``None`` on cache miss.
    """
    raw = await redis.get(global_memories_cache_key(user_id))
    if raw is None:
        return None
    return json.loads(raw)


async def set_cached_global_memories(
    redis: aioredis.Redis,
    user_id: int,
    memories: list[dict[str, Any]],
) -> None:
    """Store global memories in Redis with the memory TTL.

    Args:
        redis: The shared async Redis client.
        user_id: The user's id.
        memories: The memory entries as a list of dicts.
    """
    await redis.set(
        global_memories_cache_key(user_id),
        json.dumps(memories, ensure_ascii=False),
        ex=MEMORY_CACHE_TTL,
    )


async def invalidate_global_memories_cache(
    redis: aioredis.Redis, user_id: int
) -> None:
    """Delete the cached global memories for a user.

    Called after a new global memory is created (e.g., user traits
    extracted during summarization) so the next request fetches fresh
    data from the database.

    Args:
        redis: The shared async Redis client.
        user_id: The user's id.
    """
    await redis.delete(global_memories_cache_key(user_id))


# ---- Article memories cache (article_id = specific article) -----------------


def article_memories_cache_key(user_id: int, article_id: int) -> str:
    """Build the Redis cache key for a user's article-specific memories.

    Article memories are scoped to a single article and cached
    independently so that switching articles does not return stale data
    from a different article's cache.

    Args:
        user_id: The user's id.
        article_id: The article's id.

    Returns:
        A Redis key of the form ``ai:memories:article:{user_id}:{article_id}``.
    """
    return f"ai:memories:article:{user_id}:{article_id}"


async def get_cached_article_memories(
    redis: aioredis.Redis, user_id: int, article_id: int
) -> Optional[list[dict[str, Any]]]:
    """Retrieve cached article-specific memories from Redis.

    Args:
        redis: The shared async Redis client.
        user_id: The user's id.
        article_id: The article's id.

    Returns:
        A list of memory dicts, or ``None`` on cache miss.
    """
    raw = await redis.get(article_memories_cache_key(user_id, article_id))
    if raw is None:
        return None
    return json.loads(raw)


async def set_cached_article_memories(
    redis: aioredis.Redis,
    user_id: int,
    article_id: int,
    memories: list[dict[str, Any]],
) -> None:
    """Store article-specific memories in Redis with the memory TTL.

    Args:
        redis: The shared async Redis client.
        user_id: The user's id.
        article_id: The article's id.
        memories: The memory entries as a list of dicts.
    """
    await redis.set(
        article_memories_cache_key(user_id, article_id),
        json.dumps(memories, ensure_ascii=False),
        ex=MEMORY_CACHE_TTL,
    )


async def invalidate_article_memories_cache(
    redis: aioredis.Redis, user_id: int, article_id: int
) -> None:
    """Delete the cached article-specific memories for a user-article pair.

    Called after a new article memory is created (e.g., article summary
    generated during summarization) so the next request fetches fresh
    data from the database.

    Args:
        redis: The shared async Redis client.
        user_id: The user's id.
        article_id: The article's id.
    """
    await redis.delete(article_memories_cache_key(user_id, article_id))


# ---- Token estimation -------------------------------------------------------


def estimate_tokens(text: str) -> int:
    """Estimate the token count of a text string.

    Uses a rough heuristic: English averages ~4 characters per token,
    Chinese characters are denser at ~1.5 characters per token. The
    function detects the proportion of CJK characters and blends the two
    estimates.

    This is intentionally imprecise — it only needs to be accurate enough
    to decide whether truncation is necessary, not for exact billing.

    Args:
        text: The input text.

    Returns:
        An estimated token count.
    """
    if not text:
        return 0

    total_chars = len(text)
    cjk_count = sum(
        1
        for ch in text
        if "\u4e00" <= ch <= "\u9fff"  # CJK Unified Ideographs
        or "\u3000" <= ch <= "\u303f"  # CJK Symbols and Punctuation
    )
    latin_count = total_chars - cjk_count

    # English: ~4 chars/token; Chinese: ~1.5 chars/token
    return int(latin_count / 4 + cjk_count / 1.5)


def truncate_for_context(
    content: str, max_tokens: int = _MAX_ARTICLE_TOKENS
) -> str:
    """Truncate article content to fit within a token budget.

    Preserves the beginning and end of the article (where the title,
    introduction, and conclusion typically live) while dropping the
    middle. An ellipsis marker is inserted at the cut point.

    Args:
        content: The full article content.
        max_tokens: The maximum token budget for the content.

    Returns:
        The original content if it fits, or a truncated version with
        head + tail preserved.
    """
    estimated = estimate_tokens(content)
    if estimated <= max_tokens:
        return content

    # Convert token budget to a character budget (weighted average).
    # Assume a blend of English and Chinese; use ~3 chars/token as a
    # conservative middle ground.
    char_budget = max_tokens * 3

    # Keep 60% head, 40% tail — introductions are usually more important.
    head_chars = int(char_budget * 0.6)
    tail_chars = char_budget - head_chars

    head = content[:head_chars]
    tail = content[-tail_chars:] if tail_chars > 0 else ""

    return f"{head}\n\n...(中间内容已省略)...\n\n{tail}"
