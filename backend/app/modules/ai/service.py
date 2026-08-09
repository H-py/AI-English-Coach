"""AI 模块的业务逻辑层。

该服务层位于 HTTP 路由与仓库层之间，负责领域规则：校验文章是否存在、
构建带正确上下文的 LLM 提示词、将 AI 响应流式回传给调用方，以及持久化
对话消息和触发记忆摘要。

AI 交互方法（``explain_word``、``analyze_sentence``、
``paragraph_summary``、``chat``）是异步生成器，从 LLM 提供方的流式
端点 yield ``str`` 分块。路由层会将其封装为 Server-Sent Events。
``chat`` 方法还会在流式结束后持久化用户消息和完整的助手回复。
"""

from collections.abc import AsyncGenerator

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai.cache import (
    cache_key,
    get_cached_response,
    set_cached_response,
)
from app.core.ai.factory import get_llm_provider
from app.core.ai.memory import build_chat_context, maybe_summarize
from app.core.ai.prompt_manager import load_reading_prompt, load_system_prompt
from app.core.ai.provider import ChatMessage
from app.core.exceptions import BizException
from app.modules.ai import memory_repository as mem_repo
from app.modules.ai import repository as repo
from app.modules.ai.schemas import (
    AnalyzeSentenceRequest,
    ChatRequest,
    ConversationListResponse,
    ConversationOut,
    ExplainWordRequest,
    ParagraphSummaryRequest,
    SentenceTranslationRequest,
)
from app.modules.article.models import Article
from app.modules.article.repository import get_article_by_id
from app.modules.users.models import User

# ---- 业务错误码 -------------------------------------------------------------
# 文章未找到（与文章模块的错误码共用）。
ARTICLE_NOT_FOUND_CODE = 90002

# ---- 各端点的 LLM 参数 ------------------------------------------------------
# temperature 和 max_tokens 按端点根据期望的输出风格调优：翻译/分析
# 偏确定性，聊天偏创造性。
_TEMP_EXPLAIN_WORD = 0.5      # 均衡 —— 举例时需要一些多样性
_TEMP_ANALYZE_SENTENCE = 0.3  # 确定性 —— 语法分析应当稳定
_TEMP_TRANSLATE_SENTENCE = 0.3  # 确定性 —— 翻译应当一致
_TEMP_PARAGRAPH_SUMMARY = 0.5  # 较为确定性 —— 摘要应当稳定
_TEMP_CHAT = 0.8              # 更具创造性 —— 对话风格，答案灵活

_MAX_TOKENS_EXPLAIN_WORD = 500
_MAX_TOKENS_ANALYZE_SENTENCE = 800
_MAX_TOKENS_TRANSLATE_SENTENCE = 600
_MAX_TOKENS_PARAGRAPH_SUMMARY = 400
_MAX_TOKENS_CHAT = 1000


async def _get_article_or_raise(
    db: AsyncSession, article_id: int
) -> Article:
    """按 id 获取文章，若不存在则抛出业务异常。

    Args:
        db: 当前活跃的异步会话。
        article_id: 文章的主键。

    Returns:
        :class:`~app.modules.article.models.Article` 实例。

    Raises:
        BizException: 若不存在指定 id 的文章
            （错误码 ``90002``）。
    """
    article = await get_article_by_id(db, article_id)
    if article is None:
        raise BizException("article not found", code=ARTICLE_NOT_FOUND_CODE)
    return article


# ---- AI 流式服务 ------------------------------------------------------------


async def explain_word(
    db: AsyncSession, user: User, data: ExplainWordRequest,
    redis: aioredis.Redis,
) -> AsyncGenerator[str, None]:
    """流式输出某单词在上下文中的 AI 解释。

    先检查 Redis 缓存 —— 相同英语水平下、相同上下文中的相同单词总是
    产生相同的解释，因此缓存命中时可以立即返回且无需任何 API 开销。
    缓存未命中时，从 LLM 流式获取响应，累加后存入 Redis 供后续请求使用。

    Args:
        db: 当前活跃的异步会话。
        user: 已认证的用户（用于获取英语水平）。
        data: 解释单词的请求载荷。
        redis: 用于响应缓存的共享 Redis 客户端。

    Yields:
        LLM 响应的 ``str`` 分块。
    """
    await _get_article_or_raise(db, data.article_id)

    level = user.english_level.value
    ckey = cache_key("explain-word", level, data.word, data.context)

    # 缓存命中 —— 作为单个分块回放。
    cached = await get_cached_response(redis, ckey)
    if cached is not None:
        yield cached
        return

    # 缓存未命中 —— 从 LLM 流式获取并缓存完整响应。
    system_prompt = load_system_prompt("coach")
    user_prompt = load_reading_prompt(
        "explain_word",
        word=data.word,
        context=data.context,
        level=level,
    )
    messages = [
        ChatMessage("system", system_prompt),
        ChatMessage("user", user_prompt),
    ]

    provider = get_llm_provider()
    collected: list[str] = []
    async for chunk in provider.chat_stream(
        messages, temperature=_TEMP_EXPLAIN_WORD,
        max_tokens=_MAX_TOKENS_EXPLAIN_WORD,
    ):
        collected.append(chunk)
        yield chunk

    await set_cached_response(redis, ckey, "".join(collected))


async def analyze_sentence(
    db: AsyncSession, user: User, data: AnalyzeSentenceRequest,
    redis: aioredis.Redis,
) -> AsyncGenerator[str, None]:
    """流式输出句子的 AI 结构分析。

    结果会缓存到 Redis —— 相同英语水平下的相同句子总是产生相同的
    分析结果。缓存命中时立即回放已存储的响应，无需调用 LLM。

    Args:
        db: 当前活跃的异步会话。
        user: 已认证的用户（用于获取英语水平）。
        data: 分析句子的请求载荷。
        redis: 用于响应缓存的共享 Redis 客户端。

    Yields:
        LLM 响应的 ``str`` 分块。
    """
    await _get_article_or_raise(db, data.article_id)

    level = user.english_level.value
    ckey = cache_key("analyze-sentence", level, data.sentence)

    cached = await get_cached_response(redis, ckey)
    if cached is not None:
        yield cached
        return

    system_prompt = load_system_prompt("coach")
    user_prompt = load_reading_prompt(
        "sentence_analysis",
        sentence=data.sentence,
        level=level,
    )
    messages = [
        ChatMessage("system", system_prompt),
        ChatMessage("user", user_prompt),
    ]

    provider = get_llm_provider()
    collected: list[str] = []
    async for chunk in provider.chat_stream(
        messages, temperature=_TEMP_ANALYZE_SENTENCE,
        max_tokens=_MAX_TOKENS_ANALYZE_SENTENCE,
    ):
        collected.append(chunk)
        yield chunk

    await set_cached_response(redis, ckey, "".join(collected))


async def translate_sentence(
    db: AsyncSession, user: User, data: SentenceTranslationRequest,
    redis: aioredis.Redis,
) -> AsyncGenerator[str, None]:
    """流式输出句子的 AI 中文翻译。

    结果会缓存到 Redis —— 相同英语水平下的相同句子总是产生相同的
    翻译。

    Args:
        db: 当前活跃的异步会话。
        user: 已认证的用户（用于获取英语水平）。
        data: 翻译请求载荷。
        redis: 用于响应缓存的共享 Redis 客户端。

    Yields:
        LLM 响应的 ``str`` 分块。
    """
    await _get_article_or_raise(db, data.article_id)

    level = user.english_level.value
    ckey = cache_key("translate-sentence", level, data.sentence)

    cached = await get_cached_response(redis, ckey)
    if cached is not None:
        yield cached
        return

    system_prompt = load_system_prompt("coach")
    user_prompt = load_reading_prompt(
        "sentence_translation",
        sentence=data.sentence,
        level=level,
    )
    messages = [
        ChatMessage("system", system_prompt),
        ChatMessage("user", user_prompt),
    ]

    provider = get_llm_provider()
    collected: list[str] = []
    async for chunk in provider.chat_stream(
        messages, temperature=_TEMP_TRANSLATE_SENTENCE,
        max_tokens=_MAX_TOKENS_TRANSLATE_SENTENCE,
    ):
        collected.append(chunk)
        yield chunk

    await set_cached_response(redis, ckey, "".join(collected))


async def paragraph_summary(
    db: AsyncSession, user: User, data: ParagraphSummaryRequest,
    redis: aioredis.Redis,
) -> AsyncGenerator[str, None]:
    """流式输出段落的 AI 摘要。

    结果会缓存到 Redis —— 相同英语水平下的相同段落总是产生相同的
    摘要。

    Args:
        db: 当前活跃的异步会话。
        user: 已认证的用户（用于获取英语水平）。
        data: 段落摘要的请求载荷。
        redis: 用于响应缓存的共享 Redis 客户端。

    Yields:
        LLM 响应的 ``str`` 分块。
    """
    await _get_article_or_raise(db, data.article_id)

    level = user.english_level.value
    ckey = cache_key("paragraph-summary", level, data.paragraph)

    cached = await get_cached_response(redis, ckey)
    if cached is not None:
        yield cached
        return

    system_prompt = load_system_prompt("coach")
    user_prompt = load_reading_prompt(
        "paragraph_summary",
        paragraph=data.paragraph,
        level=level,
    )
    messages = [
        ChatMessage("system", system_prompt),
        ChatMessage("user", user_prompt),
    ]

    provider = get_llm_provider()
    collected: list[str] = []
    async for chunk in provider.chat_stream(
        messages, temperature=_TEMP_PARAGRAPH_SUMMARY,
        max_tokens=_MAX_TOKENS_PARAGRAPH_SUMMARY,
    ):
        collected.append(chunk)
        yield chunk

    await set_cached_response(redis, ckey, "".join(collected))


async def chat(
    db: AsyncSession, user: User, data: ChatRequest,
    redis: aioredis.Redis,
) -> AsyncGenerator[str, None]:
    """流式输出围绕当前文章的 AI 聊天回复。

    使用三层记忆系统（:mod:`app.core.ai.memory`）组装上下文：

    - **长期记忆**（用户画像 + 压缩摘要）从 Redis 缓存（未命中则从
      数据库）加载，并注入到系统提示词中。
    - **短期记忆**（未摘要的对话消息）从数据库加载，并裁剪以适配剩余
      token 预算。
    - 用户新消息最后追加。

    流式结束后，会同时持久化用户消息和完整的助手回复。随后
    ``maybe_summarize`` 会检查最早的未摘要消息是否应被压缩为一条
    长期记忆条目。

    Args:
        db: 当前活跃的异步会话。
        user: 已认证的用户。
        data: 聊天请求载荷。
        redis: 用于记忆缓存的共享 Redis 客户端。

    Yields:
        LLM 响应的 ``str`` 分块。
    """
    article = await _get_article_or_raise(db, data.article_id)

    # 用三层记忆构建完整上下文。
    messages = await build_chat_context(
        db, redis, user, article, data.message
    )

    provider = get_llm_provider()
    collected: list[str] = []
    async for chunk in provider.chat_stream(
        messages, temperature=_TEMP_CHAT, max_tokens=_MAX_TOKENS_CHAT,
    ):
        collected.append(chunk)
        yield chunk

    # 流式结束后持久化完整对话。
    await repo.save_message(db, user.id, data.article_id, "user", data.message)
    await repo.save_message(
        db, user.id, data.article_id, "assistant", "".join(collected)
    )

    # 增加用户的消息计数，用于画像跟踪。
    await mem_repo.increment_message_count(db, user.id, delta=2)

    # 若未摘要消息超过阈值，则触发摘要。
    await maybe_summarize(db, redis, user.id, data.article_id)


# ---- AI 对话服务 -----------------------------------------------------------


async def list_conversations(
    db: AsyncSession, user_id: int, article_id: int
) -> ConversationListResponse:
    """返回用户针对某篇文章的 AI 聊天历史。

    最多加载 50 条最近的消息，按时间顺序排列，以便前端在页面刷新后
    恢复聊天会话。文章必须存在。

    Args:
        db: 当前活跃的异步会话。
        user_id: 发起聊天的用户 id。
        article_id: 要加载对话历史的文章。

    Returns:
        包含序列化消息的 :class:`ConversationListResponse`。

    Raises:
        BizException: 若文章不存在（错误码 ``90002``）。
    """
    await _get_article_or_raise(db, article_id)
    messages = await repo.list_conversations(db, user_id, article_id)
    return ConversationListResponse(
        items=[ConversationOut.model_validate(m) for m in messages],
        total=len(messages),
    )
