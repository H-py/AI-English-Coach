"""AI 响应缓存与 token 预算工具。

本模块包含三个关注点：

1. **Redis 缓存**，用于确定性的 AI 端点（单词解释、句子分析、翻译、
   段落摘要）。相同的输入始终产生相同的输出，因此我们缓存*完整*响应，
   并在命中缓存时作为单个 SSE 数据块回放——零 API 成本。

   缓存键组成：``ai:cache:{endpoint}:{level}:{input_hash}``
   - ``endpoint`` —— ``explain-word`` / ``analyze-sentence`` / …
   - ``level``    —— 用户的英语水平（影响提示词输出）
   - ``input_hash`` —— 主输入（单词+上下文、句子或段落文本）的 SHA-256

   TTL：24 小时。缓存未命中时会回退到实时 LLM 调用；流式数据块会被
   累积并在流结束后存储。

2. **画像与记忆缓存**，用于三层记忆系统。用户画像和长期记忆被缓存到
   Redis 中，以避免每次聊天请求都访问数据库。画像的 TTL 为 1 小时；
   记忆的 TTL 为 30 分钟。当底层数据变更时，二者都会被失效。

3. **Token 估算**，用于聊天上下文预算。使用一个粗略的启发式规则
   （英文约 1 token ≈ 4 字符，中文约 ≈ 1.5 字符）来判断完整的文章
   文本是否能连同对话历史一起放入模型的上下文窗口，并在需要时进行截断。
"""

import hashlib
import json
from typing import Any, Optional

import redis.asyncio as aioredis

# 缓存 TTL：24 小时（秒）。
CACHE_TTL = 86400
# 画像缓存 TTL：1 小时。
PROFILE_CACHE_TTL = 3600
# 记忆缓存 TTL：30 分钟。
MEMORY_CACHE_TTL = 1800

# ---- DeepSeek 上下文窗口常量 -----------------------------------------------
# deepseek-chat 的上下文窗口为 64K。我们为系统提示词、对话历史、用户新消息
# 以及响应预留空间。
_MODEL_CONTEXT_WINDOW = 64000
# 为系统提示词 + 响应生成预留的 token 数。
_RESERVED_TOKENS = 2000
# 聊天系统提示词中文章内容的最大 token 数。
_MAX_ARTICLE_TOKENS = 4000


def _hash_input(*parts: str) -> str:
    """返回拼接后输入部分的短 SHA-256 十六进制摘要。

    Args:
        *parts: 共同标识一个唯一请求的字符串组成部分。

    Returns:
        一个 16 字符的十六进制字符串（摘要的前 8 个字节）。
    """
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def cache_key(endpoint: str, level: str, *input_parts: str) -> str:
    """为确定性的 AI 请求构建 Redis 缓存键。

    Args:
        endpoint: AI 端点名称，例如 ``"explain-word"``。
        level: 用户的英语水平（``"beginner"`` / …）。
        *input_parts: 主输入值（单词、上下文、句子……）。

    Returns:
        形如 ``ai:cache:{endpoint}:{level}:{hash}`` 的 Redis 键字符串。
    """
    return f"ai:cache:{endpoint}:{level}:{_hash_input(*input_parts)}"


async def get_cached_response(
    redis: aioredis.Redis, key: str
) -> Optional[str]:
    """从 Redis 中获取缓存的完整 AI 响应。

    Args:
        redis: 共享的异步 Redis 客户端。
        key: 由 :func:`cache_key` 生成的缓存键。

    Returns:
        缓存的响应字符串；缓存未命中时返回 ``None``。
    """
    return await redis.get(key)


async def set_cached_response(
    redis: aioredis.Redis, key: str, response: str
) -> None:
    """以标准 TTL 将完整的 AI 响应存储到 Redis。

    Args:
        redis: 共享的异步 Redis 客户端。
        key: 由 :func:`cache_key` 生成的缓存键。
        response: 要缓存的完整 AI 响应文本。
    """
    await redis.set(key, response, ex=CACHE_TTL)


# ---- 画像与记忆缓存 ---------------------------------------------------------


def profile_cache_key(user_id: int) -> str:
    """构建用户画像的 Redis 缓存键。

    Args:
        user_id: 用户 id。

    Returns:
        形如 ``ai:profile:{user_id}`` 的 Redis 键字符串。
    """
    return f"ai:profile:{user_id}"


async def get_cached_profile(
    redis: aioredis.Redis, user_id: int
) -> Optional[dict[str, Any]]:
    """从 Redis 中获取缓存的用户画像。

    Args:
        redis: 共享的异步 Redis 客户端。
        user_id: 用户 id。

    Returns:
        以字典形式返回的缓存画像；缓存未命中时返回 ``None``。
    """
    raw = await redis.get(profile_cache_key(user_id))
    if raw is None:
        return None
    return json.loads(raw)


async def set_cached_profile(
    redis: aioredis.Redis, user_id: int, profile: dict[str, Any]
) -> None:
    """以画像 TTL 将用户画像存储到 Redis。

    Args:
        redis: 共享的异步 Redis 客户端。
        user_id: 用户 id。
        profile: 以字典形式表示的画像数据。
    """
    await redis.set(
        profile_cache_key(user_id),
        json.dumps(profile, ensure_ascii=False),
        ex=PROFILE_CACHE_TTL,
    )


async def invalidate_profile_cache(
    redis: aioredis.Redis, user_id: int
) -> None:
    """删除用户的缓存画像。

    在画像更新后调用，以确保下一次请求从数据库获取最新数据。

    Args:
        redis: 共享的异步 Redis 客户端。
        user_id: 用户 id。
    """
    await redis.delete(profile_cache_key(user_id))


# ---- 全局记忆缓存（article_id IS NULL）-------------------------------------


def global_memories_cache_key(user_id: int) -> str:
    """构建用户全局（跨文章）记忆的 Redis 缓存键。

    全局记忆的 ``article_id IS NULL``，在所有文章间共享。它们与特定文章的
    记忆分开缓存，使得更新其中一方不会使另一方失效。

    Args:
        user_id: 用户 id。

    Returns:
        形如 ``ai:memories:global:{user_id}`` 的 Redis 键字符串。
    """
    return f"ai:memories:global:{user_id}"


async def get_cached_global_memories(
    redis: aioredis.Redis, user_id: int
) -> Optional[list[dict[str, Any]]]:
    """从 Redis 中获取缓存的全局记忆。

    Args:
        redis: 共享的异步 Redis 客户端。
        user_id: 用户 id。

    Returns:
        记忆字典列表；缓存未命中时返回 ``None``。
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
    """以记忆 TTL 将全局记忆存储到 Redis。

    Args:
        redis: 共享的异步 Redis 客户端。
        user_id: 用户 id。
        memories: 以字典列表形式表示的记忆条目。
    """
    await redis.set(
        global_memories_cache_key(user_id),
        json.dumps(memories, ensure_ascii=False),
        ex=MEMORY_CACHE_TTL,
    )


async def invalidate_global_memories_cache(
    redis: aioredis.Redis, user_id: int
) -> None:
    """删除用户的缓存全局记忆。

    在创建新的全局记忆后调用（例如摘要生成过程中提取的用户特质），
    以确保下一次请求从数据库获取最新数据。

    Args:
        redis: 共享的异步 Redis 客户端。
        user_id: 用户 id。
    """
    await redis.delete(global_memories_cache_key(user_id))


# ---- 文章记忆缓存（article_id = 特定文章）----------------------------------


def article_memories_cache_key(user_id: int, article_id: int) -> str:
    """构建用户特定文章记忆的 Redis 缓存键。

    文章记忆仅作用于单篇文章，并独立缓存，使得切换文章时不会返回来自
    另一篇文章缓存的过期数据。

    Args:
        user_id: 用户 id。
        article_id: 文章 id。

    Returns:
        形如 ``ai:memories:article:{user_id}:{article_id}`` 的 Redis 键。
    """
    return f"ai:memories:article:{user_id}:{article_id}"


async def get_cached_article_memories(
    redis: aioredis.Redis, user_id: int, article_id: int
) -> Optional[list[dict[str, Any]]]:
    """从 Redis 中获取缓存的特定文章记忆。

    Args:
        redis: 共享的异步 Redis 客户端。
        user_id: 用户 id。
        article_id: 文章 id。

    Returns:
        记忆字典列表；缓存未命中时返回 ``None``。
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
    """以记忆 TTL 将特定文章记忆存储到 Redis。

    Args:
        redis: 共享的异步 Redis 客户端。
        user_id: 用户 id。
        article_id: 文章 id。
        memories: 以字典列表形式表示的记忆条目。
    """
    await redis.set(
        article_memories_cache_key(user_id, article_id),
        json.dumps(memories, ensure_ascii=False),
        ex=MEMORY_CACHE_TTL,
    )


async def invalidate_article_memories_cache(
    redis: aioredis.Redis, user_id: int, article_id: int
) -> None:
    """删除某个用户-文章对的缓存特定文章记忆。

    在创建新的文章记忆后调用（例如摘要生成过程中产生的文章摘要），
    以确保下一次请求从数据库获取最新数据。

    Args:
        redis: 共享的异步 Redis 客户端。
        user_id: 用户 id。
        article_id: 文章 id。
    """
    await redis.delete(article_memories_cache_key(user_id, article_id))


# ---- Token 估算 -------------------------------------------------------------


def estimate_tokens(text: str) -> int:
    """估算文本字符串的 token 数量。

    使用一个粗略的启发式规则：英文平均约 4 个字符对应一个 token，
    中文字符更密集，约 1.5 个字符对应一个 token。该函数会检测 CJK 字符
    的比例并混合两种估算值。

    这里刻意不做精确——它只需足够准确以判断是否需要截断即可，不用于
    精确计费。

    Args:
        text: 输入文本。

    Returns:
        估算的 token 数量。
    """
    if not text:
        return 0

    total_chars = len(text)
    cjk_count = sum(
        1
        for ch in text
        if "\u4e00" <= ch <= "\u9fff"  # CJK 统一表意文字
        or "\u3000" <= ch <= "\u303f"  # CJK 符号和标点
    )
    latin_count = total_chars - cjk_count

    # 英文：约 4 字符/token；中文：约 1.5 字符/token
    return int(latin_count / 4 + cjk_count / 1.5)


def truncate_for_context(
    content: str, max_tokens: int = _MAX_ARTICLE_TOKENS
) -> str:
    """将文章内容截断以适应 token 预算。

    保留文章的开头和结尾（标题、引言和结论通常位于此处），同时舍弃
    中间部分。在截断处插入一个省略号标记。

    Args:
        content: 完整的文章内容。
        max_tokens: 内容的最大 token 预算。

    Returns:
        若内容能放下则返回原文，否则返回保留开头 + 结尾的截断版本。
    """
    estimated = estimate_tokens(content)
    if estimated <= max_tokens:
        return content

    # 将 token 预算转换为字符预算（加权平均值）。
    # 假设中英文混合；使用约 3 字符/token 作为保守的折中值。
    char_budget = max_tokens * 3

    # 保留 60% 开头，40% 结尾——引言通常更为重要。
    head_chars = int(char_budget * 0.6)
    tail_chars = char_budget - head_chars

    head = content[:head_chars]
    tail = content[-tail_chars:] if tail_chars > 0 else ""

    return f"{head}\n\n...(中间内容已省略)...\n\n{tail}"
