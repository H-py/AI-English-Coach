"""用于 AI 聊天上下文管理的三层记忆系统。

本模块实现了架构方案中讨论的记忆策略：

1. **短期记忆** —— 从 ``ai_conversations`` 中加载的未摘要对话消息
   （``is_summarized=False``）。这些是最近的、逐字记录的交流。

2. **长期记忆** —— 存储在 ``ai_memories`` 中的压缩摘要。当短期消息
   超过 token 阈值时，最旧的一批会被发送给 LLM 进行摘要。摘要会替换
   上下文窗口中的这些消息。

3. **用户画像** —— 存储在 ``user_profiles`` 中、由累积记忆推导而来的
   自然语言学习者画像。被注入到系统提示词中，使所有 AI 端点都能个性化
   响应。

画像（1 小时 TTL）和记忆（30 分钟 TTL）使用 Redis 缓存，以避免每次
聊天请求都访问数据库。
"""

import json
import logging
from typing import Optional

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai.cache import (
    estimate_tokens,
    get_cached_article_memories,
    get_cached_global_memories,
    get_cached_profile,
    invalidate_article_memories_cache,
    invalidate_global_memories_cache,
    invalidate_profile_cache,
    set_cached_article_memories,
    set_cached_global_memories,
    set_cached_profile,
    truncate_for_context,
)
from app.core.ai.factory import get_llm_provider
from app.core.ai.prompt_manager import load_prompt
from app.core.ai.provider import ChatMessage
from app.modules.article.models import Article
from app.modules.ai import memory_repository as mem_repo
from app.modules.users.models import User

logger = logging.getLogger(__name__)

# ---- 记忆系统常量 -----------------------------------------------------------

# 当未摘要消息的 token 数超过此值时触发摘要。6000
_SUMMARIZE_TOKEN_THRESHOLD = 200

# 单批次摘要的最旧消息 token 数量。
_SUMMARIZE_BATCH_TOKENS = 3000

# 将记忆加载到上下文中的 token 预算。
_MAX_GLOBAL_MEMORIES_TOKENS = 2000
_MAX_ARTICLE_MEMORIES_TOKENS = 1000
# 将所有记忆加载到画像生成器中的 token 预算。
_MAX_PROFILE_MEMORIES_TOKENS = 4000

# 每 N 个摘要周期更新一次用户画像。
_PROFILE_UPDATE_INTERVAL = 3

# 内部操作的 LLM 参数。
_TEMP_SUMMARIZE = 0.3
_TEMP_PROFILE = 0.4
_MAX_TOKENS_SUMMARIZE = 500
_MAX_TOKENS_PROFILE = 800

# DeepSeek 上下文窗口。
_CHAT_CONTEXT_WINDOW = 64000
_CHAT_RESERVED_TOKENS = 2000


# ---- 上下文组装 -------------------------------------------------------------


async def build_chat_context(
    db: AsyncSession,
    redis: aioredis.Redis,
    user: User,
    article: Article,
    user_message: str,
) -> list[ChatMessage]:
    """组装带三层记忆的完整聊天上下文。

    组装后的消息列表遵循以下顺序：
    1. 系统提示词（文章标题 + 截断后的内容 + 画像 + 记忆）
    2. 短期记忆（最近的未摘要消息，受 token 预算限制）
    3. 用户的新消息

    Args:
        db: 当前的异步会话。
        redis: 共享的 Redis 客户端。
        user: 已认证的用户。
        article: 正在阅读的文章。
        user_message: 用户的新聊天消息。

    Returns:
        可直接发送给 LLM 的 :class:`ChatMessage` 列表。
    """
    # 第 3 层：加载用户画像（Redis 缓存）。
    profile_text = await _load_profile_text(db, redis, user.id)

    # 第 2 层：加载长期记忆（Redis 缓存）。
    memories_text = await _load_memories_text(db, redis, user.id, article.id)

    # 构建注入画像与记忆的系统提示词。
    truncated_content = truncate_for_context(article.content)
    system_prompt = load_prompt(
        "reading/chat",
        title=article.title,
        content=truncated_content,
        profile=profile_text or "",
        memories=memories_text or "",
    )

    # 第 1 层：加载短期记忆（未摘要消息）。
    recent = await mem_repo.get_unsummarized_messages(
        db, user.id, article.id
    )

    # 基于 token 预算的对话历史裁剪。
    system_tokens = estimate_tokens(system_prompt)
    user_tokens = estimate_tokens(user_message)
    budget = (
        _CHAT_CONTEXT_WINDOW - _CHAT_RESERVED_TOKENS
        - system_tokens - user_tokens
    )

    messages: list[ChatMessage] = [ChatMessage("system", system_prompt)]
    kept: list[ChatMessage] = []
    for msg in reversed(recent):
        msg_tokens = estimate_tokens(msg.content)
        if budget - msg_tokens < 0:
            break
        budget -= msg_tokens
        kept.insert(0, ChatMessage(msg.role, msg.content))
    messages.extend(kept)
    messages.append(ChatMessage("user", user_message))

    return messages


async def _load_profile_text(
    db: AsyncSession, redis: aioredis.Redis, user_id: int
) -> Optional[str]:
    """加载用户画像摘要文本，使用 Redis 缓存。

    Args:
        db: 当前的异步会话。
        redis: 共享的 Redis 客户端。
        user_id: 用户 id。

    Returns:
        画像摘要文本；若不存在画像则返回 ``None``。
    """
    cached = await get_cached_profile(redis, user_id)
    if cached is not None:
        return cached.get("profile_summary")

    profile = await mem_repo.get_profile(db, user_id)
    if profile is None:
        return None

    profile_data = {
        "profile_summary": profile.profile_summary or "",
        "strengths": profile.strengths or [],
        "weaknesses": profile.weaknesses or [],
        "learning_style": profile.learning_style,
        "interests": profile.interests or [],
        "common_mistakes": profile.common_mistakes or [],
        "message_count": profile.message_count,
    }
    await set_cached_profile(redis, user_id, profile_data)
    return profile_data["profile_summary"] or None


async def _load_memories_text(
    db: AsyncSession,
    redis: aioredis.Redis,
    user_id: int,
    article_id: int,
) -> Optional[str]:
    """以文本形式加载长期记忆，使用 Redis 缓存。

    将全局记忆（``article_id IS NULL``）与特定文章记忆合并为一个文本块。
    每个类别独立缓存，使得更新其中一方不会使另一方失效。

    Args:
        db: 当前的异步会话。
        redis: 共享的 Redis 客户端。
        user_id: 用户 id。
        article_id: 当前文章 id。

    Returns:
        由记忆摘要组成的文本块；若无记忆则返回 ``None``。
    """
    # --- 全局记忆（独立缓存）---
    global_cached = await get_cached_global_memories(redis, user_id)
    if global_cached is not None:
        global_dicts = global_cached
    else:
        global_memories = await mem_repo.get_active_memories(
            db, user_id, max_tokens=_MAX_GLOBAL_MEMORIES_TOKENS
        )
        global_dicts = [
            {
                "memory_type": m.memory_type,
                "content": m.content,
                "importance": m.importance,
            }
            for m in global_memories
        ]
        await set_cached_global_memories(redis, user_id, global_dicts)

    # --- 特定文章记忆（独立缓存）---
    article_cached = await get_cached_article_memories(
        redis, user_id, article_id
    )
    if article_cached is not None:
        article_dicts = article_cached
    else:
        article_memories = await mem_repo.get_active_article_memories(
            db, user_id, article_id, max_tokens=_MAX_ARTICLE_MEMORIES_TOKENS
        )
        article_dicts = [
            {
                "memory_type": m.memory_type,
                "content": m.content,
                "importance": m.importance,
            }
            for m in article_memories
        ]
        await set_cached_article_memories(
            redis, user_id, article_id, article_dicts
        )

    # --- 合并并格式化 ---
    all_memories = global_dicts + article_dicts
    if not all_memories:
        return None
    return _format_memories(all_memories)


def _format_memories(memories: list[dict]) -> str:
    """将记忆字典格式化为用于系统提示词的文本块。

    Args:
        memories: 包含 ``memory_type``、``content`` 和 ``importance`` 键的
            记忆字典列表。

    Returns:
        格式化后的文本块。
    """
    lines: list[str] = []
    for mem in memories:
        lines.append(f"- [{mem['memory_type']}] {mem['content']}")
    return "\n".join(lines)


# ---- 摘要（短期 -> 长期）----------------------------------------------------


async def maybe_summarize(
    db: AsyncSession,
    redis: aioredis.Redis,
    user_id: int,
    article_id: int,
) -> None:
    """检查是否应触发摘要，若需要则执行。

    在每个聊天回合后，该函数会检查未摘要消息的总 token 数是否超过
    ``_SUMMARIZE_TOKEN_THRESHOLD``。若超过，则将最旧的一批（最多
    ``_SUMMARIZE_BATCH_TOKENS`` 个 token）发送给 LLM 进行摘要，摘要会以
    :class:`AiMemory` 形式存储，原始消息则被标记为已摘要。

    摘要完成后，还会触发画像更新检查。

    Args:
        db: 当前的异步会话。
        redis: 共享的 Redis 客户端。
        user_id: 进行聊天的用户 id。
        article_id: 对话所围绕的文章。
    """
    try:
        unsummarized = await mem_repo.get_unsummarized_messages(
            db, user_id, article_id
        )
        if not unsummarized:
            return

        total_tokens = sum(estimate_tokens(m.content) for m in unsummarized)
        if total_tokens <= _SUMMARIZE_TOKEN_THRESHOLD:
            return

        # 选择最旧的一批进行摘要（最多 _SUMMARIZE_BATCH_TOKENS）。
        batch: list = []
        batch_tokens = 0
        for msg in unsummarized:
            msg_tokens = estimate_tokens(msg.content)
            if batch_tokens + msg_tokens > _SUMMARIZE_BATCH_TOKENS and batch:
                break
            batch.append(msg)
            batch_tokens += msg_tokens

        if not batch:
            return

        await _summarize_messages(db, redis, user_id, article_id, batch)

        # 检查是否应触发画像更新。
        await maybe_update_profile(db, redis, user_id)

    except Exception:
        # 摘要是一项后台优化——它绝不应中断聊天流程。记录日志后继续。
        logger.exception(
            "Summarization failed for user=%s article=%s",
            user_id, article_id,
        )


async def _summarize_messages(
    db: AsyncSession,
    redis: aioredis.Redis,
    user_id: int,
    article_id: int,
    messages: list,
) -> None:
    """将一批消息发送给 LLM 进行摘要。

    LLM 输出两个部分：
    - **文章摘要** —— 以 :class:`AiMemory` 形式存储，
      ``memory_type='summary'`` 并带上当前 ``article_id``。
    - **用户特质** —— 以全局 :class:`AiMemory` 形式存储，
      ``memory_type='fact'`` 且 ``article_id=None``，使其在所有文章中都可用。

    原始消息会被标记为 ``is_summarized=True``。文章和全局的 Redis 记忆缓存
    都会被失效。

    Args:
        db: 当前的异步会话。
        redis: 共享的 Redis 客户端。
        user_id: 进行聊天的用户 id。
        article_id: 对话所围绕的文章。
        messages: 要摘要的消息（最旧的一批）。
    """
    # 为摘要器构建对话文本。
    conv_lines: list[str] = []
    for msg in messages:
        role_label = "用户" if msg.role == "user" else "AI教练"
        conv_lines.append(f"{role_label}: {msg.content}")
    conversation_text = "\n\n".join(conv_lines)

    # 摘要器模板同时包含角色描述和任务，因此我们将其作为单条用户消息发送。
    user_prompt = load_prompt(
        "system/memory_summarizer",
        conversation=conversation_text,
    )

    provider = get_llm_provider()
    response = await provider.chat(
        messages=[ChatMessage("user", user_prompt)],
        temperature=_TEMP_SUMMARIZE,
        max_tokens=_MAX_TOKENS_SUMMARIZE,
    )

    raw_output = response.content.strip()

    # 从 LLM 输出中解析两个部分。
    article_summary, user_traits = _parse_summary_output(raw_output)

    # --- 存储特定文章摘要 ---
    if article_summary:
        summary_tokens = estimate_tokens(article_summary)

        # 检测弱点/错误标记以设定重要性。
        importance = 0.5
        if "【弱点】" in article_summary or "【错误】" in article_summary:
            importance = 0.8

        # 在添加新摘要前停用旧的文章摘要。
        await mem_repo.deactivate_article_memories(db, user_id, article_id)

        await mem_repo.create_memory(
            db,
            user_id=user_id,
            article_id=article_id,
            memory_type="summary",
            content=article_summary,
            importance=importance,
            token_count=summary_tokens,
        )

        # 失效特定文章缓存。
        await invalidate_article_memories_cache(redis, user_id, article_id)

    # --- 存储全局用户特质（article_id=None）---
    if user_traits and user_traits != "无":
        traits_tokens = estimate_tokens(user_traits)

        # 用户特质对个性化始终具有高价值。
        traits_importance = 0.7
        if "【弱点】" in user_traits or "【错误】" in user_traits:
            traits_importance = 0.9

        # 停用旧的全局事实，使只有最新的特质保持激活——
        # 避免重复的用户特质记录不断累积。
        await mem_repo.deactivate_global_facts(db, user_id)

        await mem_repo.create_memory(
            db,
            user_id=user_id,
            article_id=None,
            memory_type="fact",
            content=user_traits,
            importance=traits_importance,
            token_count=traits_tokens,
        )

        # 失效全局缓存，使下一次请求重新加载。
        await invalidate_global_memories_cache(redis, user_id)

    # 标记已摘要的消息。
    await mem_repo.mark_messages_summarized(db, [m.id for m in messages])


def _parse_summary_output(raw: str) -> tuple[str, str]:
    """将摘要器 LLM 输出解析为文章摘要和用户特质。

    预期格式::

        【文章摘要】
        (文章摘要文本)

        【用户特质】
        (用户特质文本)

    若格式不匹配，则将整个输出视为文章摘要，用户特质留空。

    Args:
        raw: 原始的 LLM 响应文本。

    Returns:
        一个 ``(article_summary, user_traits)`` 元组。
    """
    if "【文章摘要】" in raw and "【用户特质】" in raw:
        parts = raw.split("【用户特质】", 1)
        article_part = parts[0]
        traits_part = parts[1] if len(parts) > 1 else ""

        # 从文章部分移除 【文章摘要】 标题。
        article_summary = article_part.replace("【文章摘要】", "").strip()
        user_traits = traits_part.strip()
        return article_summary, user_traits

    # 兜底：将整个输出视为文章摘要。
    return raw.strip(), ""


# ---- 画像生成 ---------------------------------------------------------------


async def maybe_update_profile(
    db: AsyncSession,
    redis: aioredis.Redis,
    user_id: int,
) -> None:
    """检查是否应触发画像更新，若需要则执行。

    画像每 ``_PROFILE_UPDATE_INTERVAL`` 个摘要周期刷新一次。LLM 接收当前
    画像（若有）和最近的记忆，然后输出更新后的画像。

    Args:
        db: 当前的异步会话。
        redis: 共享的 Redis 客户端。
        user_id: 用户 id。
    """
    try:
        # 统计激活记忆总数以判断是否到更新时机。
        total_memories = await mem_repo.count_memories(db, user_id)
        if total_memories == 0 or total_memories % _PROFILE_UPDATE_INTERVAL != 0:
            return

        await _generate_profile(db, redis, user_id)

    except Exception:
        logger.exception(
            "Profile update failed for user=%s", user_id
        )


async def _generate_profile(
    db: AsyncSession,
    redis: aioredis.Redis,
    user_id: int,
) -> None:
    """使用 LLM 生成或更新用户画像。

    加载当前画像与最近记忆，连同画像生成器提示词一起发送给 LLM，解析
    JSON 响应，并持久化更新后的画像。Redis 画像缓存会被失效。

    Args:
        db: 当前的异步会话。
        redis: 共享的 Redis 客户端。
        user_id: 用户 id。
    """
    current_profile = await mem_repo.get_profile(db, user_id)
    memories = await mem_repo.get_all_active_memories(
        db, user_id, max_tokens=_MAX_PROFILE_MEMORIES_TOKENS
    )

    if not memories:
        return

    # 将当前画像格式化为文本。
    if current_profile and current_profile.profile_summary:
        current_profile_text = current_profile.profile_summary
    else:
        current_profile_text = "（暂无画像）"

    # 将记忆格式化为文本。
    memories_text = "\n".join(
        f"- [{m.memory_type}] {m.content}" for m in memories
    )

    # 画像生成器模板同时包含角色描述和任务，因此我们将其作为单条
    # 用户消息发送。
    user_prompt = load_prompt(
        "system/profile_generator",
        current_profile=current_profile_text,
        memories=memories_text,
    )

    provider = get_llm_provider()
    response = await provider.chat(
        messages=[ChatMessage("user", user_prompt)],
        temperature=_TEMP_PROFILE,
        max_tokens=_MAX_TOKENS_PROFILE,
    )

    raw_output = response.content.strip()

    # 若存在 markdown 代码围栏则去除。
    if raw_output.startswith("```"):
        lines = raw_output.split("\n")
        # 移除首行（```json 或 ```）和末行（```）。
        lines = [l for l in lines if not l.strip().startswith("```")]
        raw_output = "\n".join(lines)

    try:
        profile_data = json.loads(raw_output)
    except json.JSONDecodeError:
        logger.warning(
            "Profile generation returned invalid JSON for user=%s, "
            "saving raw text as summary",
            user_id,
        )
        profile_data = {
            "profile_summary": raw_output[:500],
            "strengths": [],
            "weaknesses": [],
            "learning_style": None,
            "interests": [],
            "common_mistakes": [],
        }

    message_count = current_profile.message_count if current_profile else 0

    await mem_repo.upsert_profile(
        db,
        user_id=user_id,
        profile_summary=profile_data.get("profile_summary", ""),
        strengths=profile_data.get("strengths", []),
        weaknesses=profile_data.get("weaknesses", []),
        learning_style=profile_data.get("learning_style"),
        interests=profile_data.get("interests", []),
        common_mistakes=profile_data.get("common_mistakes", []),
        message_count=message_count,
    )

    await invalidate_profile_cache(redis, user_id)
