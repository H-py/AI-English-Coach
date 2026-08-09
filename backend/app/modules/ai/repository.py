"""AI 模块的数据库访问层。

所有函数均为异步函数，并操作共享的 :class:`AsyncSession`。
它们负责持久化机制（``add`` / ``flush`` / ``refresh`` / ``execute``），
而事务的提交/回滚则交由 ``get_db`` 依赖完成，该依赖会将每个请求
包裹在单个事务中。
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai.models import (
    AiActivity,
    AiConversation,
    ReadingQuiz,
    ReadingSummary,
)


# ---- AI 对话 ----------------------------------------------------------------


async def save_message(
    db: AsyncSession,
    user_id: int,
    article_id: int,
    role: str,
    content: str,
    history_id: Optional[int] = None,
) -> AiConversation:
    """持久化单条聊天消息（用户或助手）。

    Args:
        db: 当前活跃的异步会话。
        user_id: 发起聊天的用户 id。
        article_id: 对话所围绕的文章。
        role: 消息角色 —— ``"user"`` 或 ``"assistant"``。
        content: 消息文本。
        history_id: 阅读历史记录 id，用于关联到具体阅读会话。

    Returns:
        新创建的 :class:`AiConversation`。
    """
    message = AiConversation(
        user_id=user_id,
        article_id=article_id,
        history_id=history_id,
        role=role,
        content=content,
    )
    db.add(message)
    await db.flush()
    await db.refresh(message)
    return message


async def get_recent_messages(
    db: AsyncSession,
    user_id: int,
    article_id: int,
    limit: int = 20,
) -> list[AiConversation]:
    """返回最近的**未摘要**聊天消息，用作上下文。

    只加载 ``is_summarized=False`` 的消息 —— 已摘要的消息已被压缩进
    :class:`AiMemory` 条目，作为长期记忆单独加载。消息按 ``id`` 倒序
    获取，再反转使返回列表按时间顺序排列，便于直接作为 LLM 上下文。

    按 ``id`` 而非 ``created_at`` 排序，是因为 PostgreSQL 的 ``NOW()``
    对同一事务内插入的所有行返回相同时间戳。由于一轮对话的用户消息和
    助手消息在同一事务中保存，``created_at`` 无法区分它们的插入顺序。

    Args:
        db: 当前活跃的异步会话。
        user_id: 发起聊天的用户 id。
        article_id: 对话所围绕的文章。
        limit: 返回消息的最大数量。

    Returns:
        按时间顺序排列的 :class:`AiConversation` 列表。
    """
    stmt = (
        select(AiConversation)
        .where(
            AiConversation.user_id == user_id,
            AiConversation.article_id == article_id,
            AiConversation.is_summarized.is_(False),
        )
        .order_by(AiConversation.id.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(reversed(result.scalars().all()))


async def list_conversations(
    db: AsyncSession,
    user_id: int,
    article_id: int,
    limit: int = 50,
) -> list[AiConversation]:
    """返回某个用户与某篇文章之间的对话消息。

    与 :func:`get_recent_messages`（针对 LLM 上下文窗口调优，取 10 条
    消息）不同，本函数最多返回 ``limit`` 条消息，供前端在页面刷新后
    恢复完整的聊天会话。

    按 ``id`` 而非 ``created_at`` 排序，是因为 PostgreSQL 的 ``NOW()``
    对同一事务内插入的所有行返回相同时间戳。由于一轮对话的用户消息和
    助手消息在同一事务中保存，``created_at`` 无法区分它们的插入顺序。

    Args:
        db: 当前活跃的异步会话。
        user_id: 发起聊天的用户 id。
        article_id: 对话所围绕的文章。
        limit: 返回消息的最大数量（默认 50）。

    Returns:
        按时间顺序排列的 :class:`AiConversation` 列表。
    """
    stmt = (
        select(AiConversation)
        .where(
            AiConversation.user_id == user_id,
            AiConversation.article_id == article_id,
        )
        .order_by(AiConversation.id.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(reversed(result.scalars().all()))


async def get_conversations_by_history(
    db: AsyncSession,
    user_id: int,
    history_id: int,
    started_at: datetime,
) -> list[AiConversation]:
    """返回某次阅读会话中的所有对话消息。

    用于生成阅读总结时提取本次阅读的问答记录。除了按 ``history_id``
    过滤外，还按 ``created_at >= started_at`` 过滤，确保只返回本次
    阅读会话（从 ``started_at`` 时间点开始）的对话。这是因为
    ``reading_histories`` 表对 ``(user_id, article_id)`` 有唯一约束，
    同一篇文章的多次阅读共享同一条历史记录，需要通过时间戳来隔离每次
    会话的数据。按 ``id`` 正序排列，保证对话的时间顺序。

    Args:
        db: 当前活跃的异步会话。
        user_id: 所属用户的 id。
        history_id: 阅读历史记录 id。
        started_at: 本次阅读会话的开始时间，用于过滤历史会话数据。

    Returns:
        按时间顺序排列的 :class:`AiConversation` 列表。
    """
    stmt = (
        select(AiConversation)
        .where(
            AiConversation.user_id == user_id,
            AiConversation.history_id == history_id,
            AiConversation.created_at >= started_at,
        )
        .order_by(AiConversation.id.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


# ---- AI 活动日志 ------------------------------------------------------------


async def create_activity(
    db: AsyncSession,
    user_id: int,
    article_id: int,
    history_id: Optional[int],
    activity_type: str,
    content: str,
) -> AiActivity:
    """记录一条 AI 交互活动日志。

    Args:
        db: 当前活跃的异步会话。
        user_id: 所属用户的 id。
        article_id: 关联的文章 id。
        history_id: 阅读历史记录 id（可选）。
        activity_type: 活动类型（如 ``explain_word``、``chat``）。
        content: 用户输入的原始文本。

    Returns:
        新创建的 :class:`AiActivity`。
    """
    activity = AiActivity(
        user_id=user_id,
        article_id=article_id,
        history_id=history_id,
        activity_type=activity_type,
        content=content,
    )
    db.add(activity)
    await db.flush()
    await db.refresh(activity)
    return activity


async def get_activities_by_history(
    db: AsyncSession,
    user_id: int,
    history_id: int,
    started_at: datetime,
) -> list[AiActivity]:
    """返回某次阅读会话中的所有 AI 交互活动。

    除了按 ``history_id`` 过滤外，还按 ``created_at >= started_at``
    过滤，确保只返回本次阅读会话（从 ``started_at`` 时间点开始）的
    活动记录。这是因为 ``reading_histories`` 表对 ``(user_id, article_id)``
    有唯一约束，同一篇文章的多次阅读共享同一条历史记录，需要通过时间
    戳来隔离每次会话的数据。按 ``id`` 正序排列，保证活动的时间顺序。

    Args:
        db: 当前活跃的异步会话。
        user_id: 所属用户的 id。
        history_id: 阅读历史记录 id。
        started_at: 本次阅读会话的开始时间，用于过滤历史会话数据。

    Returns:
        按时间顺序排列的 :class:`AiActivity` 列表。
    """
    stmt = (
        select(AiActivity)
        .where(
            AiActivity.user_id == user_id,
            AiActivity.history_id == history_id,
            AiActivity.created_at >= started_at,
        )
        .order_by(AiActivity.id.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


# ---- 阅读总结 ----------------------------------------------------------------


async def get_summary(
    db: AsyncSession, user_id: int, history_id: int
) -> Optional[ReadingSummary]:
    """获取某次阅读会话的总结。

    Args:
        db: 当前活跃的异步会话。
        user_id: 所属用户的 id。
        history_id: 阅读历史记录 id。

    Returns:
        :class:`ReadingSummary`，未找到时返回 ``None``。
    """
    stmt = select(ReadingSummary).where(
        ReadingSummary.user_id == user_id,
        ReadingSummary.history_id == history_id,
    )
    result = await db.execute(stmt)
    return result.scalars().first()


async def upsert_summary(
    db: AsyncSession,
    user_id: int,
    article_id: int,
    history_id: int,
    content: str,
    activity_stats: dict,
) -> ReadingSummary:
    """新增或更新阅读总结。

    由于 ``reading_summaries`` 表对 ``history_id`` 有唯一约束，同一
    阅读会话只会保留一条总结——重新生成会覆盖旧的。

    Args:
        db: 当前活跃的异步会话。
        user_id: 所属用户的 id。
        article_id: 关联的文章 id。
        history_id: 阅读历史记录 id。
        content: 总结文本。
        activity_stats: 活动统计数据字典。

    Returns:
        新建或更新后的 :class:`ReadingSummary`。
    """
    existing = await get_summary(db, user_id, history_id)
    if existing is not None:
        existing.content = content
        existing.activity_stats = activity_stats
        await db.flush()
        await db.refresh(existing)
        return existing

    summary = ReadingSummary(
        user_id=user_id,
        article_id=article_id,
        history_id=history_id,
        content=content,
        activity_stats=activity_stats,
    )
    db.add(summary)
    await db.flush()
    await db.refresh(summary)
    return summary


# ---- 阅读练习题 --------------------------------------------------------------


async def create_quiz(
    db: AsyncSession,
    user_id: int,
    article_id: int,
    history_id: int,
    questions: list[dict],
) -> ReadingQuiz:
    """创建一份新的练习题。

    Args:
        db: 当前活跃的异步会话。
        user_id: 所属用户的 id。
        article_id: 关联的文章 id。
        history_id: 阅读历史记录 id。
        questions: 题目列表（JSON 兼容的字典列表）。

    Returns:
        新创建的 :class:`ReadingQuiz`。
    """
    quiz = ReadingQuiz(
        user_id=user_id,
        article_id=article_id,
        history_id=history_id,
        questions=questions,
        total=len(questions),
    )
    db.add(quiz)
    await db.flush()
    await db.refresh(quiz)
    return quiz


async def get_quiz(
    db: AsyncSession, user_id: int, quiz_id: int
) -> Optional[ReadingQuiz]:
    """获取单份练习题，限定在所属用户范围内。

    Args:
        db: 当前活跃的异步会话。
        user_id: 所属用户的 id。
        quiz_id: 练习题的主键。

    Returns:
        :class:`ReadingQuiz`，未找到时返回 ``None``。
    """
    stmt = select(ReadingQuiz).where(
        ReadingQuiz.id == quiz_id,
        ReadingQuiz.user_id == user_id,
    )
    result = await db.execute(stmt)
    return result.scalars().first()


async def get_latest_quiz(
    db: AsyncSession, user_id: int, history_id: int
) -> Optional[ReadingQuiz]:
    """获取某次阅读会话的最新一份练习题。

    Args:
        db: 当前活跃的异步会话。
        user_id: 所属用户的 id。
        history_id: 阅读历史记录 id。

    Returns:
        :class:`ReadingQuiz`，未找到时返回 ``None``。
    """
    stmt = (
        select(ReadingQuiz)
        .where(
            ReadingQuiz.user_id == user_id,
            ReadingQuiz.history_id == history_id,
        )
        .order_by(ReadingQuiz.id.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalars().first()


async def update_quiz_answers(
    db: AsyncSession,
    quiz: ReadingQuiz,
    user_answers: list[dict],
    score: int,
) -> ReadingQuiz:
    """更新练习题的用户答案和得分。

    Args:
        db: 当前活跃的异步会话。
        quiz: 待更新的 :class:`ReadingQuiz` 实例。
        user_answers: 用户答案列表（含判分信息）。
        score: 得分（答对题数）。

    Returns:
        更新后的 :class:`ReadingQuiz`。
    """
    quiz.user_answers = user_answers
    quiz.score = score
    await db.flush()
    await db.refresh(quiz)
    return quiz
