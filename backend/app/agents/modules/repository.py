"""Agent 模块的数据库访问层。

所有函数均为异步函数，并操作共享的 :class:`AsyncSession`。
它们负责持久化机制（``add`` / ``flush`` / ``refresh`` / ``execute``），
而事务的提交/回滚则交由 ``get_db`` 依赖完成，该依赖会将每个请求
包裹在单个事务中。
"""

from typing import Optional

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.modules.models import (
    AgentConversation,
    AgentSession,
    AgentStepRecord,
)


# ---- Agent 会话 -------------------------------------------------------------


async def create_session(
    db: AsyncSession,
    user_id: int,
    article_id: Optional[int],
    history_id: Optional[int],
    agent_type: str,
    user_message: str,
    conversation_id: Optional[int] = None,
) -> AgentSession:
    """创建一条 Agent 执行会话记录。

    在 Agent 开始执行前调用，以便尽早获得 ``session_id`` 供后续步骤
    记录引用。记录会被 flush（而非 commit），以便 ``id`` 等服务端默认
    值被填充并出现在返回的实例上，同时外层请求事务仍保留提交控制权。

    Args:
        db: 当前活跃的异步会话。
        user_id: 发起会话的用户 id。
        article_id: 关联的文章 id（可选）。
        history_id: 关联的阅读历史记录 id（可选）。
        agent_type: Agent 类型标识（如 ``"reading_coach"``）。
        user_message: 用户输入的原始消息文本。
        conversation_id: 所属对话 id（可选），用于多轮对话关联。

    Returns:
        新创建的 :class:`AgentSession`，属性已刷新。
    """
    session = AgentSession(
        user_id=user_id,
        article_id=article_id,
        history_id=history_id,
        agent_type=agent_type,
        user_message=user_message,
        conversation_id=conversation_id,
    )
    db.add(session)
    await db.flush()
    await db.refresh(session)
    return session


async def update_session(
    db: AsyncSession,
    session_id: int,
    final_answer: Optional[str],
    total_steps: int,
    status: str,
) -> None:
    """更新 Agent 会话的执行结果字段。

    在 Agent 执行完毕后调用，记录最终回答、总步数和执行状态。使用
    ``UPDATE`` 语句而非加载实体后修改，避免不必要的查询开销。

    Args:
        db: 当前活跃的异步会话。
        session_id: 待更新的会话 id。
        final_answer: Agent 生成的最终回答文本（执行失败时可能为
            ``None``）。
        total_steps: 本次会话的总执行步数。
        status: 执行状态 —— ``"completed"`` / ``"failed"`` /
            ``"max_iterations"``。
    """
    await db.execute(
        update(AgentSession)
        .where(AgentSession.id == session_id)
        .values(
            final_answer=final_answer,
            total_steps=total_steps,
            status=status,
        )
    )
    await db.flush()


async def create_steps(
    db: AsyncSession,
    session_id: int,
    steps_data: list[dict],
) -> None:
    """批量插入 Agent 执行步骤记录。

    在 Agent 执行完毕后一次性将所有步骤持久化，避免在流式输出过程中
    逐条插入导致的数据库往返开销。每个字典应包含 ``step_order``、
    ``step_type``、``content``、``tool_name``、``tool_arguments`` 和
    ``tool_result`` 键。

    Args:
        db: 当前活跃的异步会话。
        session_id: 所属的会话 id。
        steps_data: 步骤数据字典列表。
    """
    if not steps_data:
        return
    records = [
        AgentStepRecord(session_id=session_id, **step)
        for step in steps_data
    ]
    db.add_all(records)
    await db.flush()


async def get_session(
    db: AsyncSession,
    session_id: int,
    user_id: int,
) -> Optional[AgentSession]:
    """按主键获取单条 Agent 会话，限定在所属用户范围内。

    Args:
        db: 当前活跃的异步会话。
        session_id: 会话的主键。
        user_id: 所属用户的 id（用于权限隔离）。

    Returns:
        :class:`AgentSession`，未找到或不属于该用户时返回 ``None``。
    """
    stmt = select(AgentSession).where(
        AgentSession.id == session_id,
        AgentSession.user_id == user_id,
    )
    result = await db.execute(stmt)
    return result.scalars().first()


async def list_sessions(
    db: AsyncSession,
    user_id: int,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[AgentSession], int]:
    """分页列出某用户的 Agent 会话记录。

    结果按 ``created_at`` 倒序（最新优先）排列。返回总数用于前端
    分页展示。

    Args:
        db: 当前活跃的异步会话。
        user_id: 所属用户的 id。
        page: 从 1 开始的页码。
        page_size: 每页条数。

    Returns:
        一个 ``(items, total)`` 元组，其中 ``items`` 为请求页对应的
        :class:`AgentSession` 实例列表，``total`` 为该用户的会话总数。
    """
    # 统计总数。
    count_stmt = (
        select(func.count())
        .select_from(AgentSession)
        .where(AgentSession.user_id == user_id)
    )
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    # 带排序与分页的数据查询。
    offset = (page - 1) * page_size
    data_stmt = (
        select(AgentSession)
        .where(AgentSession.user_id == user_id)
        .order_by(AgentSession.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    data_result = await db.execute(data_stmt)
    items = list(data_result.scalars().all())

    return items, total


async def get_session_with_steps(
    db: AsyncSession,
    session_id: int,
    user_id: int,
) -> Optional[AgentSession]:
    """获取单条 Agent 会话及其所有步骤（按顺序排列）。

    使用 ``selectinload`` 预加载 ``steps`` 关系，避免 N+1 查询。
    结果限定在所属用户范围内，确保数据隔离。

    Args:
        db: 当前活跃的异步会话。
        session_id: 会话的主键。
        user_id: 所属用户的 id（用于权限隔离）。

    Returns:
        :class:`AgentSession`（含 ``steps`` 属性），未找到或不属于
        该用户时返回 ``None``。
    """
    stmt = (
        select(AgentSession)
        .options(selectinload(AgentSession.steps))
        .where(
            AgentSession.id == session_id,
            AgentSession.user_id == user_id,
        )
    )
    result = await db.execute(stmt)
    return result.scalars().first()


# ---- Agent 对话 -------------------------------------------------------------


async def create_conversation(
    db: AsyncSession,
    user_id: int,
    title: str = "新对话",
) -> AgentConversation:
    """创建一条 Agent 对话记录。

    在多轮对话首次发起时调用。记录会被 flush（而非 commit），
    以便 ``id`` 被填充并出现在返回的实例上。

    Args:
        db: 当前活跃的异步会话。
        user_id: 发起对话的用户 id。
        title: 对话标题，默认为 "新对话"。

    Returns:
        新创建的 :class:`AgentConversation`，属性已刷新。
    """
    conversation = AgentConversation(
        user_id=user_id,
        title=title,
    )
    db.add(conversation)
    await db.flush()
    await db.refresh(conversation)
    return conversation


async def list_conversations(
    db: AsyncSession,
    user_id: int,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[AgentConversation], int]:
    """分页列出某用户的 Agent 对话记录。

    结果按 ``updated_at`` 倒序（最近活跃优先）排列。

    Args:
        db: 当前活跃的异步会话。
        user_id: 所属用户的 id。
        page: 从 1 开始的页码。
        page_size: 每页条数。

    Returns:
        一个 ``(items, total)`` 元组。
    """
    count_stmt = (
        select(func.count())
        .select_from(AgentConversation)
        .where(AgentConversation.user_id == user_id)
    )
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    offset = (page - 1) * page_size
    data_stmt = (
        select(AgentConversation)
        .where(AgentConversation.user_id == user_id)
        .order_by(AgentConversation.updated_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    data_result = await db.execute(data_stmt)
    items = list(data_result.scalars().all())

    return items, total


async def get_conversation_with_sessions(
    db: AsyncSession,
    conversation_id: int,
    user_id: int,
) -> Optional[AgentConversation]:
    """获取单条对话及其所有会话（含步骤），限定在所属用户范围内。

    使用 ``selectinload`` 预加载 ``sessions`` 及 ``sessions.steps``
    关系，避免 N+1 查询。

    Args:
        db: 当前活跃的异步会话。
        conversation_id: 对话的主键。
        user_id: 所属用户的 id（用于权限隔离）。

    Returns:
        :class:`AgentConversation`（含 ``sessions`` 及步骤），
        未找到或不属于该用户时返回 ``None``。
    """
    stmt = (
        select(AgentConversation)
        .options(
            selectinload(AgentConversation.sessions).selectinload(
                AgentSession.steps
            )
        )
        .where(
            AgentConversation.id == conversation_id,
            AgentConversation.user_id == user_id,
        )
    )
    result = await db.execute(stmt)
    return result.scalars().first()


async def delete_conversation(
    db: AsyncSession,
    conversation_id: int,
    user_id: int,
) -> bool:
    """删除一条对话及其所有会话和步骤（级联删除）。

    Args:
        db: 当前活跃的异步会话。
        conversation_id: 对话的主键。
        user_id: 所属用户的 id（用于权限隔离）。

    Returns:
        是否删除成功（对话不存在或不属于该用户时返回 ``False``）。
    """
    # 先验证对话存在且属于该用户。
    stmt = select(AgentConversation.id).where(
        AgentConversation.id == conversation_id,
        AgentConversation.user_id == user_id,
    )
    result = await db.execute(stmt)
    if result.scalar() is None:
        return False

    # 级联删除会先删除关联的 sessions 和 steps（由 ORM cascade 或
    # 数据库外键 ON DELETE CASCADE 处理）。
    await db.execute(
        delete(AgentConversation).where(
            AgentConversation.id == conversation_id
        )
    )
    await db.flush()
    return True


async def get_conversation_messages(
    db: AsyncSession,
    conversation_id: int,
    user_id: int,
) -> list[AgentSession]:
    """获取对话下的所有会话（按创建时间升序），用于构建对话上下文。

    仅返回 ``user_message`` 和 ``final_answer`` 字段，避免加载
    不必要的数据。

    Args:
        db: 当前活跃的异步会话。
        conversation_id: 对话的主键。
        user_id: 所属用户的 id（用于权限隔离）。

    Returns:
        :class:`AgentSession` 列表，按 ``created_at`` 升序排列。
    """
    stmt = (
        select(AgentSession)
        .where(
            AgentSession.conversation_id == conversation_id,
            AgentSession.user_id == user_id,
        )
        .order_by(AgentSession.created_at.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_conversation_title(
    db: AsyncSession,
    conversation_id: int,
    title: str,
) -> None:
    """更新对话标题。

    Args:
        db: 当前活跃的异步会话。
        conversation_id: 对话的主键。
        title: 新标题。
    """
    await db.execute(
        update(AgentConversation)
        .where(AgentConversation.id == conversation_id)
        .values(title=title)
    )
    await db.flush()


async def touch_conversation(
    db: AsyncSession,
    conversation_id: int,
) -> None:
    """更新对话的 updated_at 时间戳为当前时间。

    在每次创建新会话时调用，使侧边栏对话列表按最近活跃排序。

    Args:
        db: 当前活跃的异步会话。
        conversation_id: 对话的主键。
    """
    await db.execute(
        update(AgentConversation)
        .where(AgentConversation.id == conversation_id)
        .values(updated_at=func.now())
    )
    await db.flush()
