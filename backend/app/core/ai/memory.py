"""Three-layer memory system for AI chat context management.

This module implements the memory strategy discussed in the architecture
plan:

1. **Short-term memory** — unsummarized conversation messages loaded from
   ``ai_conversations`` (``is_summarized=False``). These are the most
   recent, verbatim exchanges.

2. **Long-term memory** — compressed summaries stored in ``ai_memories``.
   When short-term messages exceed the token threshold, the oldest batch
   is sent to the LLM for summarization. The summary replaces those
   messages in the context window.

3. **User profile** — a natural-language learner profile stored in
   ``user_profiles`` and derived from accumulated memories. Injected
   into the system prompt so all AI endpoints can personalize responses.

Redis caching is used for profiles (1h TTL) and memories (30min TTL) to
avoid hitting the database on every chat request.
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
from app.modules.reading import memory_repository as mem_repo
from app.modules.users.models import User

logger = logging.getLogger(__name__)

# ---- Memory system constants ------------------------------------------------

# Trigger summarization when unsummarized messages exceed this many tokens. 6000
_SUMMARIZE_TOKEN_THRESHOLD = 200

# Amount of oldest messages (in tokens) to summarize in one batch.
_SUMMARIZE_BATCH_TOKENS = 3000

# Token budgets for loading memories into context.
_MAX_GLOBAL_MEMORIES_TOKENS = 2000
_MAX_ARTICLE_MEMORIES_TOKENS = 1000
# Token budget for loading ALL memories into the profile generator.
_MAX_PROFILE_MEMORIES_TOKENS = 4000

# Update the user profile every N summarization cycles.
_PROFILE_UPDATE_INTERVAL = 3

# LLM parameters for internal operations.
_TEMP_SUMMARIZE = 0.3
_TEMP_PROFILE = 0.4
_MAX_TOKENS_SUMMARIZE = 500
_MAX_TOKENS_PROFILE = 800

# DeepSeek context window.
_CHAT_CONTEXT_WINDOW = 64000
_CHAT_RESERVED_TOKENS = 2000


# ---- Context assembly -------------------------------------------------------


async def build_chat_context(
    db: AsyncSession,
    redis: aioredis.Redis,
    user: User,
    article: Article,
    user_message: str,
) -> list[ChatMessage]:
    """Assemble the full chat context with three-layer memory.

    The assembled message list follows this order:
    1. System prompt (article title + truncated content + profile + memories)
    2. Short-term memory (recent unsummarized messages, token-budgeted)
    3. The user's new message

    Args:
        db: The active async session.
        redis: The shared Redis client.
        user: The authenticated user.
        article: The article being read.
        user_message: The user's new chat message.

    Returns:
        A list of :class:`ChatMessage` ready to send to the LLM.
    """
    # Layer 3: Load user profile (Redis-cached).
    profile_text = await _load_profile_text(db, redis, user.id)

    # Layer 2: Load long-term memories (Redis-cached).
    memories_text = await _load_memories_text(db, redis, user.id, article.id)

    # Build the system prompt with profile and memories injected.
    truncated_content = truncate_for_context(article.content)
    system_prompt = load_prompt(
        "reading/chat",
        title=article.title,
        content=truncated_content,
        profile=profile_text or "",
        memories=memories_text or "",
    )

    # Layer 1: Load short-term memory (unsummarized messages).
    recent = await mem_repo.get_unsummarized_messages(
        db, user.id, article.id
    )

    # Token-budget-aware history trimming.
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
    """Load the user's profile summary text, using Redis cache.

    Args:
        db: The active async session.
        redis: The shared Redis client.
        user_id: The user's id.

    Returns:
        The profile summary text, or ``None`` if no profile exists.
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
    """Load long-term memories as text, using Redis cache.

    Combines global memories (``article_id IS NULL``) and article-specific
    memories into a single text block. Each category is cached independently
    so that updating one does not invalidate the other.

    Args:
        db: The active async session.
        redis: The shared Redis client.
        user_id: The user's id.
        article_id: The current article's id.

    Returns:
        A text block of memory summaries, or ``None`` if no memories exist.
    """
    # --- Global memories (cached separately) ---
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

    # --- Article-specific memories (cached separately) ---
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

    # --- Combine and format ---
    all_memories = global_dicts + article_dicts
    if not all_memories:
        return None
    return _format_memories(all_memories)


def _format_memories(memories: list[dict]) -> str:
    """Format memory dicts into a text block for the system prompt.

    Args:
        memories: A list of memory dicts with ``memory_type``,
            ``content``, and ``importance`` keys.

    Returns:
        A formatted text block.
    """
    lines: list[str] = []
    for mem in memories:
        lines.append(f"- [{mem['memory_type']}] {mem['content']}")
    return "\n".join(lines)


# ---- Summarization (short-term → long-term) ---------------------------------


async def maybe_summarize(
    db: AsyncSession,
    redis: aioredis.Redis,
    user_id: int,
    article_id: int,
) -> None:
    """Check if summarization should be triggered, and do it if so.

    After each chat turn, this function checks whether the total tokens
    of unsummarized messages exceed ``_SUMMARIZE_TOKEN_THRESHOLD``. If
    so, the oldest batch (up to ``_SUMMARIZE_BATCH_TOKENS`` tokens) is
    sent to the LLM for summarization, the summary is stored as an
    :class:`AiMemory`, and the original messages are marked as summarized.

    After summarization, the profile update check is also triggered.

    Args:
        db: The active async session.
        redis: The shared Redis client.
        user_id: The chatting user's id.
        article_id: The article the conversation is about.
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

        # Select the oldest batch to summarize (up to _SUMMARIZE_BATCH_TOKENS).
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

        # Check if a profile update should be triggered.
        await maybe_update_profile(db, redis, user_id)

    except Exception:
        # Summarization is a background optimization — it should never
        # break the chat flow. Log and move on.
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
    """Send a batch of messages to the LLM for summarization.

    The LLM outputs two sections:
    - **Article summary** — stored as an :class:`AiMemory` with
      ``memory_type='summary'`` and the current ``article_id``.
    - **User traits** — stored as a global :class:`AiMemory` with
      ``memory_type='fact'`` and ``article_id=None``, so it is available
      across all articles.

    The original messages are marked as ``is_summarized=True``. Both the
    article and global Redis memories caches are invalidated.

    Args:
        db: The active async session.
        redis: The shared Redis client.
        user_id: The chatting user's id.
        article_id: The article the conversation is about.
        messages: The messages to summarize (oldest batch).
    """
    # Build the conversation text for the summarizer.
    conv_lines: list[str] = []
    for msg in messages:
        role_label = "用户" if msg.role == "user" else "AI教练"
        conv_lines.append(f"{role_label}: {msg.content}")
    conversation_text = "\n\n".join(conv_lines)

    # The summarizer template includes both role description and task,
    # so we send it as a single user message.
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

    # Parse the two sections from the LLM output.
    article_summary, user_traits = _parse_summary_output(raw_output)

    # --- Store article-specific summary ---
    if article_summary:
        summary_tokens = estimate_tokens(article_summary)

        # Detect weakness/mistake markers to set importance.
        importance = 0.5
        if "【弱点】" in article_summary or "【错误】" in article_summary:
            importance = 0.8

        # Deactivate old article summaries before adding the new one.
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

        # Invalidate the article-specific cache.
        await invalidate_article_memories_cache(redis, user_id, article_id)

    # --- Store global user traits (article_id=None) ---
    if user_traits and user_traits != "无":
        traits_tokens = estimate_tokens(user_traits)

        # User traits are always high-value for personalization.
        traits_importance = 0.7
        if "【弱点】" in user_traits or "【错误】" in user_traits:
            traits_importance = 0.9

        # Deactivate old global facts so only the latest traits remain
        # active — prevents duplicate user trait records from accumulating.
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

        # Invalidate the global cache so the next request reloads.
        await invalidate_global_memories_cache(redis, user_id)

    # Mark the summarized messages.
    await mem_repo.mark_messages_summarized(db, [m.id for m in messages])


def _parse_summary_output(raw: str) -> tuple[str, str]:
    """Parse the summarizer LLM output into article summary and user traits.

    Expected format::

        【文章摘要】
        (article summary text)

        【用户特质】
        (user traits text)

    If the format is not matched, the entire output is treated as the
    article summary and user traits is left empty.

    Args:
        raw: The raw LLM response text.

    Returns:
        A ``(article_summary, user_traits)`` tuple.
    """
    if "【文章摘要】" in raw and "【用户特质】" in raw:
        parts = raw.split("【用户特质】", 1)
        article_part = parts[0]
        traits_part = parts[1] if len(parts) > 1 else ""

        # Remove the 【文章摘要】 header from the article part.
        article_summary = article_part.replace("【文章摘要】", "").strip()
        user_traits = traits_part.strip()
        return article_summary, user_traits

    # Fallback: treat entire output as article summary.
    return raw.strip(), ""


# ---- Profile generation -----------------------------------------------------


async def maybe_update_profile(
    db: AsyncSession,
    redis: aioredis.Redis,
    user_id: int,
) -> None:
    """Check if a profile update should be triggered, and do it if so.

    The profile is refreshed every ``_PROFILE_UPDATE_INTERVAL``
    summarization cycles. The LLM receives the current profile (if any)
    and recent memories, then outputs an updated profile.

    Args:
        db: The active async session.
        redis: The shared Redis client.
        user_id: The user's id.
    """
    try:
        # Count total active memories to determine if an update is due.
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
    """Generate or update a user's profile using the LLM.

    Loads the current profile and recent memories, sends them to the LLM
    with the profile generator prompt, parses the JSON response, and
    persists the updated profile. The Redis profile cache is invalidated.

    Args:
        db: The active async session.
        redis: The shared Redis client.
        user_id: The user's id.
    """
    current_profile = await mem_repo.get_profile(db, user_id)
    memories = await mem_repo.get_all_active_memories(
        db, user_id, max_tokens=_MAX_PROFILE_MEMORIES_TOKENS
    )

    if not memories:
        return

    # Format current profile as text.
    if current_profile and current_profile.profile_summary:
        current_profile_text = current_profile.profile_summary
    else:
        current_profile_text = "（暂无画像）"

    # Format memories as text.
    memories_text = "\n".join(
        f"- [{m.memory_type}] {m.content}" for m in memories
    )

    # The profile generator template includes both role description and
    # task, so we send it as a single user message.
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

    # Strip markdown code fences if present.
    if raw_output.startswith("```"):
        lines = raw_output.split("\n")
        # Remove first line (```json or ```) and last line (```).
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
