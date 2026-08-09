"""AI 模块的对话数据库访问层。

所有函数均为异步函数，并操作共享的 :class:`AsyncSession`。
它们负责持久化机制（``add`` / ``flush`` / ``refresh`` / ``execute``），
而事务的提交/回滚则交由 ``get_db`` 依赖完成，该依赖会将每个请求
包裹在单个事务中。
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai.models import AiConversation


# ---- AI 对话 ----------------------------------------------------------------


async def save_message(
    db: AsyncSession,
    user_id: int,
    article_id: int,
    role: str,
    content: str,
) -> AiConversation:
    """持久化单条聊天消息（用户或助手）。

    Args:
        db: 当前活跃的异步会话。
        user_id: 发起聊天的用户 id。
        article_id: 对话所围绕的文章。
        role: 消息角色 —— ``"user"`` 或 ``"assistant"``。
        content: 消息文本。

    Returns:
        新创建的 :class:`AiConversation`。
    """
    message = AiConversation(
        user_id=user_id,
        article_id=article_id,
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
