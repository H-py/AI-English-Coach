"""AI 模块的业务逻辑层。

该服务层位于 HTTP 路由与仓库层之间，负责领域规则：校验文章是否存在、
构建带正确上下文的 LLM 提示词、将 AI 响应流式回传给调用方，以及持久化
对话消息和触发记忆摘要。

AI 交互方法（``explain_word``、``analyze_sentence``、
``paragraph_summary``、``chat``）是异步生成器，从 LLM 提供方的流式
端点 yield ``str`` 分块。路由层会将其封装为 Server-Sent Events。
``chat`` 方法还会在流式结束后持久化用户消息和完整的助手回复。

阅读总结和练习题功能使用非流式 LLM 调用，因为需要完整的 JSON 或
文本响应进行后续处理。
"""

import json
import logging
from collections.abc import AsyncGenerator
from typing import Optional

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai.cache import (
    cache_key,
    get_cached_response,
    set_cached_response,
)
from app.core.ai.factory import get_llm_provider_for_user
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
    QuizSubmitRequest,
    QuizSubmitResponse,
    QuizAnswerResult,
    ReadingSummaryOut,
    ReadingQuizOut,
    SentenceTranslationRequest,
    SummaryRequest,
    QuizRequest,
)
from app.modules.article.models import Article
from app.modules.article.repository import get_article_by_id
from app.modules.reading import repository as reading_repo
from app.modules.users.models import User
from app.modules.word_bank.labels import WORD_LEVEL_LABELS
from app.modules.word_bank.repository import lookup_word

logger = logging.getLogger(__name__)

# ---- 业务错误码 -------------------------------------------------------------
# 文章未找到（与文章模块的错误码共用）。
ARTICLE_NOT_FOUND_CODE = 90002
# 阅读历史未找到。
HISTORY_NOT_FOUND_CODE = 90005
# 练习题未找到。
QUIZ_NOT_FOUND_CODE = 90006
# 练习题 JSON 解析失败。
QUIZ_PARSE_ERROR_CODE = 50003

# ---- 各端点的 LLM 参数 ------------------------------------------------------
# temperature 和 max_tokens 按端点根据期望的输出风格调优：翻译/分析
# 偏确定性，聊天偏创造性。
_TEMP_EXPLAIN_WORD = 0.5      # 均衡 —— 举例时需要一些多样性
_TEMP_ANALYZE_SENTENCE = 0.3  # 确定性 —— 语法分析应当稳定
_TEMP_TRANSLATE_SENTENCE = 0.3  # 确定性 —— 翻译应当一致
_TEMP_PARAGRAPH_SUMMARY = 0.5  # 较为确定性 —— 摘要应当稳定
_TEMP_CHAT = 0.8              # 更具创造性 —— 对话风格，答案灵活
_TEMP_READING_SUMMARY = 0.5   # 阅读总结 —— 较为确定性
_TEMP_QUIZ = 0.3              # 练习题 —— 确定性，保证题目质量

_MAX_TOKENS_EXPLAIN_WORD = 500
_MAX_TOKENS_ANALYZE_SENTENCE = 800
_MAX_TOKENS_TRANSLATE_SENTENCE = 600
_MAX_TOKENS_PARAGRAPH_SUMMARY = 400
_MAX_TOKENS_CHAT = 1000
_MAX_TOKENS_READING_SUMMARY = 800
_MAX_TOKENS_QUIZ = 2000


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
        raise BizException("文章不存在", code=ARTICLE_NOT_FOUND_CODE)
    return article


async def _log_activity(
    db: AsyncSession,
    user_id: int,
    article_id: int,
    history_id: Optional[int],
    activity_type: str,
    content: str,
) -> None:
    """记录 AI 交互活动日志（仅在 history_id 存在时）。

    Args:
        db: 当前活跃的异步会话。
        user_id: 所属用户的 id。
        article_id: 关联的文章 id。
        history_id: 阅读历史记录 id（为 None 时跳过记录）。
        activity_type: 活动类型。
        content: 用户输入的原始文本。
    """
    if history_id is None:
        return
    await repo.create_activity(
        db, user_id, article_id, history_id, activity_type, content
    )


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

    # 记录活动日志。
    await _log_activity(
        db, user.id, data.article_id, data.history_id,
        "explain_word", data.word,
    )

    level = user.english_level.value
    provider = await get_llm_provider_for_user(db, user.id)
    ckey = cache_key("explain-word", level, data.word, data.context, model=provider.model)

    # 缓存命中 —— 作为单个分块回放。
    cached = await get_cached_response(redis, ckey)
    if cached is not None:
        yield cached
        return

    # 缓存未命中 —— 从 LLM 流式获取并缓存完整响应。
    # 查询分级词库，标注词汇等级（如四级/六级/考研）；未命中则为 None。
    word_info = await lookup_word(db, data.word)
    word_levels = None
    if word_info and word_info["levels"]:
        word_levels = "、".join(
            WORD_LEVEL_LABELS.get(lv, lv) for lv in word_info["levels"]
        )

    system_prompt = load_system_prompt("coach")
    user_prompt = load_reading_prompt(
        "explain_word",
        word=data.word,
        context=data.context,
        level=level,
        word_levels=word_levels,
    )
    messages = [
        ChatMessage("system", system_prompt),
        ChatMessage("user", user_prompt),
    ]

    collected: list[str] = []
    async for chunk in provider.chat_stream(
        messages, temperature=_TEMP_EXPLAIN_WORD,
        max_tokens=_MAX_TOKENS_EXPLAIN_WORD,
    ):
        collected.append(chunk)
        yield chunk

    # 仅在响应非空时缓存，避免网络异常导致的空响应被永久缓存。
    full_response = "".join(collected)
    if full_response.strip():
        await set_cached_response(redis, ckey, full_response)


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

    # 记录活动日志。
    await _log_activity(
        db, user.id, data.article_id, data.history_id,
        "analyze_sentence", data.sentence,
    )

    level = user.english_level.value
    provider = await get_llm_provider_for_user(db, user.id)
    ckey = cache_key("analyze-sentence", level, data.sentence, model=provider.model)

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

    collected: list[str] = []
    async for chunk in provider.chat_stream(
        messages, temperature=_TEMP_ANALYZE_SENTENCE,
        max_tokens=_MAX_TOKENS_ANALYZE_SENTENCE,
    ):
        collected.append(chunk)
        yield chunk

    # 仅在响应非空时缓存，避免网络异常导致的空响应被永久缓存。
    full_response = "".join(collected)
    if full_response.strip():
        await set_cached_response(redis, ckey, full_response)


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

    # 记录活动日志。
    await _log_activity(
        db, user.id, data.article_id, data.history_id,
        "translate_sentence", data.sentence,
    )

    level = user.english_level.value
    provider = await get_llm_provider_for_user(db, user.id)
    ckey = cache_key("translate-sentence", level, data.sentence, model=provider.model)

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

    collected: list[str] = []
    async for chunk in provider.chat_stream(
        messages, temperature=_TEMP_TRANSLATE_SENTENCE,
        max_tokens=_MAX_TOKENS_TRANSLATE_SENTENCE,
    ):
        collected.append(chunk)
        yield chunk

    # 仅在响应非空时缓存，避免网络异常导致的空响应被永久缓存。
    full_response = "".join(collected)
    if full_response.strip():
        await set_cached_response(redis, ckey, full_response)


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

    # 记录活动日志。
    await _log_activity(
        db, user.id, data.article_id, data.history_id,
        "paragraph_summary", data.paragraph,
    )

    level = user.english_level.value
    provider = await get_llm_provider_for_user(db, user.id)
    ckey = cache_key("paragraph-summary", level, data.paragraph, model=provider.model)

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

    collected: list[str] = []
    async for chunk in provider.chat_stream(
        messages, temperature=_TEMP_PARAGRAPH_SUMMARY,
        max_tokens=_MAX_TOKENS_PARAGRAPH_SUMMARY,
    ):
        collected.append(chunk)
        yield chunk

    # 仅在响应非空时缓存，避免网络异常导致的空响应被永久缓存。
    full_response = "".join(collected)
    if full_response.strip():
        await set_cached_response(redis, ckey, full_response)


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

    # 记录活动日志。
    await _log_activity(
        db, user.id, data.article_id, data.history_id,
        "chat", data.message,
    )

    # 用三层记忆构建完整上下文。
    messages = await build_chat_context(
        db, redis, user, article, data.message
    )

    provider = await get_llm_provider_for_user(db, user.id)
    collected: list[str] = []
    async for chunk in provider.chat_stream(
        messages, temperature=_TEMP_CHAT, max_tokens=_MAX_TOKENS_CHAT,
    ):
        collected.append(chunk)
        yield chunk

    # 流式结束后持久化完整对话。
    await repo.save_message(
        db, user.id, data.article_id, "user", data.message,
        history_id=data.history_id,
    )
    await repo.save_message(
        db, user.id, data.article_id, "assistant", "".join(collected),
        history_id=data.history_id,
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


# ---- 阅读总结服务 -----------------------------------------------------------


async def generate_summary(
    db: AsyncSession, user: User, data: SummaryRequest
) -> ReadingSummaryOut:
    """生成某次阅读会话的总结。

    收集该阅读会话中的所有 AI 交互活动（查词、分析句子、问答等）和
    阅读时长，构建提示词发送给 LLM 生成总结。总结会持久化到数据库
    （同一会话重新生成会覆盖旧的）。

    Args:
        db: 当前活跃的异步会话。
        user: 已认证的用户。
        data: 总结请求载荷（包含 ``history_id``）。

    Returns:
        包含总结内容的 :class:`ReadingSummaryOut`。

    Raises:
        BizException: 若阅读历史不存在（错误码 ``90005``）。
    """
    # 获取阅读历史记录。
    history = await reading_repo.get_history(db, user.id, data.history_id)
    if history is None:
        raise BizException("阅读记录不存在", code=HISTORY_NOT_FOUND_CODE)

    article = await _get_article_or_raise(db, history.article_id)

    # 收集本次阅读的活动数据（按 started_at 过滤，隔离每次会话）。
    activities = await repo.get_activities_by_history(
        db, user.id, data.history_id, history.started_at
    )
    conversations = await repo.get_conversations_by_history(
        db, user.id, data.history_id, history.started_at
    )

    # 统计活动数据。
    word_count = sum(
        1 for a in activities if a.activity_type == "explain_word"
    )
    sentence_count = sum(
        1 for a in activities
        if a.activity_type in ("analyze_sentence", "translate_sentence")
    )
    chat_count = len(conversations)
    duration_seconds = history.duration_seconds

    activity_stats = {
        "word_count": word_count,
        "sentence_count": sentence_count,
        "chat_count": chat_count,
        "duration_seconds": duration_seconds,
    }

    # 构建活动详情文本。
    activity_details: list[str] = []
    for a in activities:
        if a.activity_type == "explain_word":
            activity_details.append(f"- 查询单词：{a.content}")
        elif a.activity_type == "analyze_sentence":
            activity_details.append(f"- 分析句子：{a.content[:80]}")
        elif a.activity_type == "translate_sentence":
            activity_details.append(f"- 翻译句子：{a.content[:80]}")
        elif a.activity_type == "paragraph_summary":
            activity_details.append(f"- 段落总结：{a.content[:80]}")
    activity_text = "\n".join(activity_details) if activity_details else "（无活动记录）"

    # 构建问答记录文本。
    chat_details: list[str] = []
    for msg in conversations:
        role_label = "用户" if msg.role == "user" else "AI"
        chat_details.append(f"{role_label}：{msg.content[:200]}")
    chat_text = "\n".join(chat_details) if chat_details else "（无问答记录）"

    # 计算阅读时长（分钟）。
    duration_minutes = (
        round(duration_seconds / 60) if duration_seconds else 0
    )

    # 构建提示词并调用 LLM。
    system_prompt = load_system_prompt("coach")
    user_prompt = load_reading_prompt(
        "reading_summary",
        article_title=article.title,
        duration_minutes=duration_minutes,
        word_count=word_count,
        sentence_count=sentence_count,
        chat_count=chat_count,
        activity_details=activity_text,
        chat_records=chat_text,
    )

    provider = await get_llm_provider_for_user(db, user.id)
    response = await provider.chat(
        messages=[
            ChatMessage("system", system_prompt),
            ChatMessage("user", user_prompt),
        ],
        temperature=_TEMP_READING_SUMMARY,
        max_tokens=_MAX_TOKENS_READING_SUMMARY,
    )

    summary_content = response.content.strip()

    # 持久化总结。
    summary = await repo.upsert_summary(
        db, user.id, article.id, data.history_id,
        summary_content, activity_stats,
    )

    return ReadingSummaryOut.model_validate(summary)


async def get_summary(
    db: AsyncSession, user_id: int, history_id: int
) -> Optional[ReadingSummaryOut]:
    """获取某次阅读会话的已有总结。

    Args:
        db: 当前活跃的异步会话。
        user_id: 所属用户的 id。
        history_id: 阅读历史记录 id。

    Returns:
        :class:`ReadingSummaryOut`，未找到时返回 ``None``。
    """
    summary = await repo.get_summary(db, user_id, history_id)
    if summary is None:
        return None
    return ReadingSummaryOut.model_validate(summary)


# ---- 阅读练习题服务 ---------------------------------------------------------


async def generate_quiz(
    db: AsyncSession, user: User, data: QuizRequest
) -> ReadingQuizOut:
    """基于文章生成练习题。

    使用 LLM 生成 3-5 道阅读理解选择题，每道题包含题目、选项、正确
    答案和解析。题目以 JSON 格式返回，解析后持久化到数据库。

    Args:
        db: 当前活跃的异步会话。
        user: 已认证的用户。
        data: 练习题请求载荷（包含 ``article_id`` 和 ``history_id``）。

    Returns:
        包含题目列表的 :class:`ReadingQuizOut`。

    Raises:
        BizException: 若文章不存在（错误码 ``90002``）或 JSON 解析
            失败（错误码 ``50003``）。
    """
    article = await _get_article_or_raise(db, data.article_id)

    # 校验阅读历史存在。
    history = await reading_repo.get_history(db, user.id, data.history_id)
    if history is None:
        raise BizException("阅读记录不存在", code=HISTORY_NOT_FOUND_CODE)

    # 构建提示词并调用 LLM。
    system_prompt = load_system_prompt("coach")
    user_prompt = load_reading_prompt(
        "reading_quiz",
        article_title=article.title,
        article_content=article.content[:4000],
        level=user.english_level.value,
    )

    provider = await get_llm_provider_for_user(db, user.id)
    response = await provider.chat(
        messages=[
            ChatMessage("system", system_prompt),
            ChatMessage("user", user_prompt),
        ],
        temperature=_TEMP_QUIZ,
        max_tokens=_MAX_TOKENS_QUIZ,
    )

    raw_output = response.content.strip()

    # 去除可能的 markdown 代码围栏。
    if raw_output.startswith("```"):
        lines = raw_output.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        raw_output = "\n".join(lines)

    # 解析 JSON。
    try:
        questions = json.loads(raw_output)
    except json.JSONDecodeError:
        logger.warning(
            "Quiz generation returned invalid JSON for article=%s",
            data.article_id,
        )
        raise BizException(
            "测验题目解析失败", code=QUIZ_PARSE_ERROR_CODE
        )

    # 确保是列表格式。
    if not isinstance(questions, list) or not questions:
        raise BizException(
            "测验题目内容为空或格式错误", code=QUIZ_PARSE_ERROR_CODE
        )

    # 持久化练习题。
    quiz = await repo.create_quiz(
        db, user.id, article.id, data.history_id, questions,
    )

    return ReadingQuizOut.model_validate(quiz)


async def get_latest_quiz(
    db: AsyncSession, user_id: int, history_id: int
) -> Optional[ReadingQuizOut]:
    """获取某次阅读会话的最新一份练习题。

    Args:
        db: 当前活跃的异步会话。
        user_id: 所属用户的 id。
        history_id: 阅读历史记录 id。

    Returns:
        :class:`ReadingQuizOut`，未找到时返回 ``None``。
    """
    quiz = await repo.get_latest_quiz(db, user_id, history_id)
    if quiz is None:
        return None
    return ReadingQuizOut.model_validate(quiz)


async def submit_quiz(
    db: AsyncSession, user_id: int, quiz_id: int,
    data: QuizSubmitRequest,
) -> QuizSubmitResponse:
    """提交练习题答案并判分。

    将用户的答案与正确答案逐题比对，计算得分，并将判分结果持久化。

    Args:
        db: 当前活跃的异步会话。
        user_id: 所属用户的 id。
        quiz_id: 练习题的主键。
        data: 包含用户答案的请求载荷。

    Returns:
        包含得分和逐题判分结果的 :class:`QuizSubmitResponse`。

    Raises:
        BizException: 若练习题不存在（错误码 ``90006``）。
    """
    quiz = await repo.get_quiz(db, user_id, quiz_id)
    if quiz is None:
        raise BizException("测验不存在", code=QUIZ_NOT_FOUND_CODE)

    # 构建题目 id -> 题目的映射。
    question_map: dict[int, dict] = {}
    for q in quiz.questions:
        qid = q.get("id")
        if qid is not None:
            question_map[qid] = q

    # 逐题判分。
    results: list[QuizAnswerResult] = []
    user_answers_with_results: list[dict] = []
    score = 0

    for answer in data.answers:
        question = question_map.get(answer.question_id)
        if question is None:
            continue

        correct_answer = question.get("correct_answer", "")
        is_correct = answer.user_answer == correct_answer
        if is_correct:
            score += 1

        result = QuizAnswerResult(
            question_id=answer.question_id,
            user_answer=answer.user_answer,
            correct_answer=correct_answer,
            is_correct=is_correct,
            explanation=question.get("explanation", ""),
        )
        results.append(result)

        user_answers_with_results.append({
            "question_id": answer.question_id,
            "user_answer": answer.user_answer,
            "is_correct": is_correct,
        })

    # 持久化判分结果。
    await repo.update_quiz_answers(
        db, quiz, user_answers_with_results, score,
    )

    return QuizSubmitResponse(
        quiz_id=quiz.id,
        score=score,
        total=quiz.total,
        results=results,
    )
