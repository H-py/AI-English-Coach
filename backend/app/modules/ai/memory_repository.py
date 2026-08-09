"""AI 记忆与用户画像表的数据库访问层。

所有函数均为异步函数，并操作共享的 :class:`AsyncSession`。
它们负责持久化机制（``add`` / ``flush`` / ``refresh`` / ``execute``），
而事务的提交/回滚则交由 ``get_db`` 依赖完成。
"""

from typing import Optional

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai.models import AiConversation, AiMemory, UserProfile


# ---- 未摘要消息（短期记忆来源） --------------------------------------------


async def get_unsummarized_messages(
    db: AsyncSession, user_id: int, article_id: int
) -> list[AiConversation]:
    """返回某用户与某篇文章之间所有未摘要的消息。

    消息按 ``id`` 升序（按时间顺序）排列，以便调用方轻松切分出最早的
    一批用于摘要。

    Args:
        db: 当前活跃的异步会话。
        user_id: 发起聊天的用户 id。
        article_id: 对话所围绕的文章。

    Returns:
        按时间顺序排列的未摘要 :class:`AiConversation` 消息列表。
    """
    stmt = (
        select(AiConversation)
        .where(
            AiConversation.user_id == user_id,
            AiConversation.article_id == article_id,
            AiConversation.is_summarized.is_(False),
        )
        .order_by(AiConversation.id.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def mark_messages_summarized(
    db: AsyncSession, message_ids: list[int]
) -> None:
    """将一批消息标记为已摘要。

    Args:
        db: 当前活跃的异步会话。
        message_ids: 待标记消息的 id 列表。
    """
    if not message_ids:
        return
    await db.execute(
        update(AiConversation)
        .where(AiConversation.id.in_(message_ids))
        .values(is_summarized=True)
    )
    await db.flush()


async def count_unsummarized_tokens(
    db: AsyncSession, user_id: int, article_id: int
) -> int:
    """统计未摘要消息的总 token 数。

    使用数据库的 ``LENGTH`` 函数作为字符数的粗略代理；调用方再将其
    换算为估算的 token 数。这样避免了把所有消息正文加载到 Python 中
    仅为计数。

    Args:
        db: 当前活跃的异步会话。
        user_id: 发起聊天的用户 id。
        article_id: 对话所围绕的文章。

    Returns:
        未摘要消息内容的总字符数。
    """
    stmt = (
        select(func.coalesce(func.sum(func.length(AiConversation.content)), 0))
        .where(
            AiConversation.user_id == user_id,
            AiConversation.article_id == article_id,
            AiConversation.is_summarized.is_(False),
        )
    )
    result = await db.execute(stmt)
    return result.scalar() or 0


# ---- AI 记忆（长期记忆） ---------------------------------------------------


async def create_memory(
    db: AsyncSession,
    user_id: int,
    article_id: Optional[int],
    memory_type: str,
    content: str,
    importance: float,
    token_count: int,
) -> AiMemory:
    """创建一条新的长期记忆条目。

    Args:
        db: 当前活跃的异步会话。
        user_id: 所属用户的 id。
        article_id: 相关文章，``None`` 表示全局记忆。
        memory_type: ``summary`` / ``fact`` / ``mistake`` /
            ``preference`` 之一。
        content: 记忆文本（LLM 生成的摘要或事实）。
        importance: 0.0-1.0 的重要性评分。
        token_count: ``content`` 的估算 token 数。

    Returns:
        新创建的 :class:`AiMemory`。
    """
    memory = AiMemory(
        user_id=user_id,
        article_id=article_id,
        memory_type=memory_type,
        content=content,
        importance=importance,
        token_count=token_count,
    )
    db.add(memory)
    await db.flush()
    await db.refresh(memory)
    return memory


async def get_active_memories(
    db: AsyncSession, user_id: int, max_tokens: int = 2000
) -> list[AiMemory]:
    """为用户加载最相关的、处于激活状态的记忆。

    记忆按 ``importance`` 降序排列，因此最重要的会优先加载。本函数
    会累加记忆，直到 token 预算耗尽。

    全局记忆（``article_id IS NULL``）始终包含在内；文章级记忆仅在
    调用方通过单独的 :func:`get_active_article_memories` 函数传入文章
    id 时才加载。

    Args:
        db: 当前活跃的异步会话。
        user_id: 所属用户的 id。
        max_tokens: 加载记忆的最大总 token 预算。

    Returns:
        :class:`AiMemory` 条目列表，按重要性从高到低排列。
    """
    stmt = (
        select(AiMemory)
        .where(
            AiMemory.user_id == user_id,
            AiMemory.is_active.is_(True),
            AiMemory.article_id.is_(None),
        )
        .order_by(AiMemory.importance.desc())
    )
    result = await db.execute(stmt)
    all_memories = list(result.scalars().all())

    selected: list[AiMemory] = []
    used_tokens = 0
    for mem in all_memories:
        if used_tokens + mem.token_count > max_tokens:
            continue
        selected.append(mem)
        used_tokens += mem.token_count

    return selected


async def get_active_article_memories(
    db: AsyncSession, user_id: int, article_id: int, max_tokens: int = 1000
) -> list[AiMemory]:
    """为用户加载某篇文章专用的、处于激活状态的记忆。

    类似于 :func:`get_active_memories`，但限定在某篇具体文章范围内。

    Args:
        db: 当前活跃的异步会话。
        user_id: 所属用户的 id。
        article_id: 要加载记忆的文章。
        max_tokens: 最大总 token 预算。

    Returns:
        :class:`AiMemory` 条目列表，按重要性从高到低排列。
    """
    stmt = (
        select(AiMemory)
        .where(
            AiMemory.user_id == user_id,
            AiMemory.article_id == article_id,
            AiMemory.is_active.is_(True),
        )
        .order_by(AiMemory.importance.desc())
    )
    result = await db.execute(stmt)
    all_memories = list(result.scalars().all())

    selected: list[AiMemory] = []
    used_tokens = 0
    for mem in all_memories:
        if used_tokens + mem.token_count > max_tokens:
            continue
        selected.append(mem)
        used_tokens += mem.token_count

    return selected


async def get_all_active_memories(
    db: AsyncSession, user_id: int, max_tokens: int = 4000
) -> list[AiMemory]:
    """为用户加载所有处于激活状态的记忆，不区分文章范围。

    将全局（``article_id IS NULL``）和文章级记忆合并为一个列表，按
    ``importance`` 降序排列。供画像生成器使用，以便其从所有文章的
    完整对话历史中综合出用户的学习画像。

    Args:
        db: 当前活跃的异步会话。
        user_id: 所属用户的 id。
        max_tokens: 加载记忆的最大总 token 预算。

    Returns:
        :class:`AiMemory` 条目列表，按重要性从高到低排列。
    """
    stmt = (
        select(AiMemory)
        .where(
            AiMemory.user_id == user_id,
            AiMemory.is_active.is_(True),
        )
        .order_by(AiMemory.importance.desc())
    )
    result = await db.execute(stmt)
    all_memories = list(result.scalars().all())

    selected: list[AiMemory] = []
    used_tokens = 0
    for mem in all_memories:
        if used_tokens + mem.token_count > max_tokens:
            continue
        selected.append(mem)
        used_tokens += mem.token_count

    return selected


async def count_memories(
    db: AsyncSession, user_id: int, article_id: Optional[int] = None
) -> int:
    """统计用户处于激活状态的记忆数，可选按文章范围限定。

    用于判断是否应触发画像刷新。

    Args:
        db: 当前活跃的异步会话。
        user_id: 所属用户的 id。
        article_id: 可选的文章范围。

    Returns:
        处于激活状态的记忆条目数。
    """
    conditions = [
        AiMemory.user_id == user_id,
        AiMemory.is_active.is_(True),
    ]
    if article_id is not None:
        conditions.append(AiMemory.article_id == article_id)

    stmt = select(func.count()).select_from(AiMemory).where(*conditions)
    result = await db.execute(stmt)
    return result.scalar() or 0


async def deactivate_article_memories(
    db: AsyncSession, user_id: int, article_id: int
) -> None:
    """将某篇文章的所有专用记忆标记为非激活。

    在新摘要替换同一文章的旧摘要时调用。

    Args:
        db: 当前活跃的异步会话。
        user_id: 所属用户的 id。
        article_id: 要停用记忆的文章。
    """
    await db.execute(
        update(AiMemory)
        .where(
            AiMemory.user_id == user_id,
            AiMemory.article_id == article_id,
            AiMemory.memory_type == "summary",
            AiMemory.is_active.is_(True),
        )
        .values(is_active=False)
    )
    await db.flush()


async def deactivate_global_facts(
    db: AsyncSession, user_id: int
) -> None:
    """将所有处于激活状态的全局事实记忆标记为非激活。

    在创建新的用户特征条目之前调用，以确保只有最新的特征保持激活
    （``article_id IS NULL`` 且 ``memory_type = 'fact'``）。这样可以
    防止跨摘要周期累积重复的用户特征记录。

    Args:
        db: 当前活跃的异步会话。
        user_id: 所属用户的 id。
    """
    await db.execute(
        update(AiMemory)
        .where(
            AiMemory.user_id == user_id,
            AiMemory.article_id.is_(None),
            AiMemory.memory_type == "fact",
            AiMemory.is_active.is_(True),
        )
        .values(is_active=False)
    )
    await db.flush()


# ---- 用户画像 --------------------------------------------------------------


async def get_profile(
    db: AsyncSession, user_id: int
) -> Optional[UserProfile]:
    """获取用户画像，若尚未创建则返回 ``None``。

    Args:
        db: 当前活跃的异步会话。
        user_id: 用户的 id。

    Returns:
        :class:`UserProfile`，或 ``None``。
    """
    result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == user_id)
    )
    return result.scalars().first()


async def upsert_profile(
    db: AsyncSession,
    user_id: int,
    profile_summary: str,
    strengths: list[str],
    weaknesses: list[str],
    learning_style: Optional[str],
    interests: list[str],
    common_mistakes: list[str],
    message_count: int,
) -> UserProfile:
    """创建或更新用户画像。

    Args:
        db: 当前活跃的异步会话。
        user_id: 用户的 id。
        profile_summary: 自然语言形式的画像文本。
        strengths: 用户优势列表。
        weaknesses: 用户弱点列表。
        learning_style: 用户的学习风格。
        interests: 兴趣话题列表。
        common_mistakes: 反复出现的错误列表。
        message_count: 本次更新时的总消息数。

    Returns:
        创建或更新后的 :class:`UserProfile`。
    """
    existing = await get_profile(db, user_id)

    if existing is not None:
        existing.profile_summary = profile_summary
        existing.strengths = strengths
        existing.weaknesses = weaknesses
        existing.learning_style = learning_style
        existing.interests = interests
        existing.common_mistakes = common_mistakes
        existing.message_count = message_count
        existing.last_updated_at = func.now()
        await db.flush()
        await db.refresh(existing)
        return existing

    profile = UserProfile(
        user_id=user_id,
        profile_summary=profile_summary,
        strengths=strengths,
        weaknesses=weaknesses,
        learning_style=learning_style,
        interests=interests,
        common_mistakes=common_mistakes,
        message_count=message_count,
        last_updated_at=func.now(),
    )
    db.add(profile)
    await db.flush()
    await db.refresh(profile)
    return profile


async def increment_message_count(
    db: AsyncSession, user_id: int, delta: int = 1
) -> None:
    """增加用户画像上的消息计数。

    若画像尚不存在，则以默认值创建一条记录。

    Args:
        db: 当前活跃的异步会话。
        user_id: 用户的 id。
        delta: 增量（默认 1）。
    """
    existing = await get_profile(db, user_id)
    if existing is not None:
        existing.message_count += delta
        await db.flush()
    else:
        # 创建一个占位画像，稍后会被填充。
        profile = UserProfile(
            user_id=user_id,
            message_count=delta,
        )
        db.add(profile)
        await db.flush()
