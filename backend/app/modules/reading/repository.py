"""阅读模块的数据库访问层。

所有函数均为异步函数，并操作共享的 :class:`AsyncSession`。
它们负责持久化机制（``add`` / ``flush`` / ``refresh`` / ``execute``），
而事务的提交/回滚则交由 ``get_db`` 依赖完成，该依赖会将每个请求
包裹在单个事务中。
"""

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.article.models import Article
from app.modules.reading.models import (
    MasteryLevel,
    ReadingHistory,
    SentenceCollection,
    WordCollection,
)
from app.modules.reading.schemas import SentenceCollectionCreate


# ---- 单词收藏 ----------------------------------------------------------------


async def get_or_create_word(
    db: AsyncSession,
    user_id: int,
    word: str,
    context: str,
    article_id: Optional[int],
    ai_explanation: Optional[str],
    short_meaning: Optional[str] = None,
) -> WordCollection:
    """为用户新增或更新（upsert）一个收藏的单词。

    如果用户已经收藏过 ``word``，则更新已有行的 ``context``，并在提供了
    新解释时更新 ``ai_explanation`` 和 ``short_meaning``。若提供了新的
    ``article_id``，也会一并刷新。否则创建一条新的 :class:`WordCollection`
    行。

    Args:
        db: 当前活跃的异步会话。
        user_id: 执行收藏操作的用户 id。
        word: 被收藏的单词。
        context: 该单词出现的句子。
        article_id: 单词所属的文章，可选。
        ai_explanation: 预先生成的 AI 解释，可选。
        short_meaning: 单词的简短释义，可选。

    Returns:
        新建或更新后的 :class:`WordCollection`。
    """
    result = await db.execute(
        select(WordCollection).where(
            WordCollection.user_id == user_id,
            WordCollection.word == word,
        )
    )
    existing = result.scalars().first()

    if existing is not None:
        existing.context = context
        if ai_explanation is not None:
            existing.ai_explanation = ai_explanation
        if short_meaning is not None:
            existing.short_meaning = short_meaning
        if article_id is not None:
            existing.article_id = article_id
        await db.flush()
        await db.refresh(existing)
        return existing

    word_obj = WordCollection(
        user_id=user_id,
        word=word,
        context=context,
        article_id=article_id,
        ai_explanation=ai_explanation,
        short_meaning=short_meaning,
    )
    db.add(word_obj)
    await db.flush()
    await db.refresh(word_obj)
    return word_obj


async def list_words(
    db: AsyncSession,
    user_id: int,
    page: int,
    page_size: int,
    mastery_level: Optional[MasteryLevel] = None,
    search: Optional[str] = None,
) -> tuple[list[WordCollection], int]:
    """返回用户收藏单词的分页列表。

    结果按 ``created_at`` 倒序排列（最新在前）。当提供 ``mastery_level``
    时，仅返回该掌握程度的单词。当提供 ``search`` 时，仅返回包含该
    搜索字符串的单词（不区分大小写）。

    Args:
        db: 当前活跃的异步会话。
        user_id: 所属用户的 id。
        page: 从 1 开始的页码。
        page_size: 每页条数。
        mastery_level: 可选，按掌握程度过滤。
        search: 可选，不区分大小写的单词搜索。

    Returns:
        ``(items, total)`` 元组。
    """
    conditions = [WordCollection.user_id == user_id]
    if mastery_level is not None:
        conditions.append(WordCollection.mastery_level == mastery_level)
    if search:
        conditions.append(WordCollection.word.ilike(f"%{search}%"))

    count_stmt = (
        select(func.count())
        .select_from(WordCollection)
        .where(*conditions)
    )
    total = (await db.execute(count_stmt)).scalar() or 0

    offset = (page - 1) * page_size
    data_stmt = (
        select(WordCollection)
        .where(*conditions)
        .order_by(WordCollection.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    items = list((await db.execute(data_stmt)).scalars().all())
    return items, total


async def get_word(
    db: AsyncSession, user_id: int, word_id: int
) -> Optional[WordCollection]:
    """获取单个收藏单词，限定在所属用户范围内。

    Args:
        db: 当前活跃的异步会话。
        user_id: 所属用户的 id。
        word_id: 单词收藏记录的主键。

    Returns:
        :class:`WordCollection`，未找到时返回 ``None``。
    """
    result = await db.execute(
        select(WordCollection).where(
            WordCollection.id == word_id,
            WordCollection.user_id == user_id,
        )
    )
    return result.scalars().first()


async def update_word(
    db: AsyncSession, word: WordCollection, data: dict
) -> WordCollection:
    """对已有收藏单词应用一组字段更新。

    Args:
        db: 当前活跃的异步会话。
        word: 待更新的 :class:`WordCollection` 实例。
        data: 属性名到新值的映射。

    Returns:
        更新后并刷新属性的 :class:`WordCollection`。
    """
    for key, value in data.items():
        setattr(word, key, value)
    await db.flush()
    await db.refresh(word)
    return word


async def delete_word(db: AsyncSession, word: WordCollection) -> None:
    """从数据库中删除一个收藏单词。

    Args:
        db: 当前活跃的异步会话。
        word: 待删除的 :class:`WordCollection` 实例。
    """
    await db.delete(word)
    await db.flush()


# ---- 句子收藏 ----------------------------------------------------------------


async def get_or_create_sentence(
    db: AsyncSession, user_id: int, data: SentenceCollectionCreate
) -> SentenceCollection:
    """为用户新增或更新（upsert）一个收藏的句子。

    如果用户已经收藏过完全相同的句子文本，则更新已有行的 ``note``
    （当提供时）和 ``article_id``。否则创建一条新的
    :class:`SentenceCollection` 行。

    Args:
        db: 当前活跃的异步会话。
        user_id: 执行收藏操作的用户 id。
        data: 已校验的创建载荷。

    Returns:
        新建或更新后的 :class:`SentenceCollection`。
    """
    result = await db.execute(
        select(SentenceCollection).where(
            SentenceCollection.user_id == user_id,
            SentenceCollection.sentence == data.sentence,
        )
    )
    existing = result.scalars().first()

    if existing is not None:
        if data.note is not None:
            existing.note = data.note
        if data.article_id is not None:
            existing.article_id = data.article_id
        await db.flush()
        await db.refresh(existing)
        return existing

    sentence = SentenceCollection(
        user_id=user_id,
        sentence=data.sentence,
        article_id=data.article_id,
        note=data.note,
    )
    db.add(sentence)
    await db.flush()
    await db.refresh(sentence)
    return sentence


async def list_sentences(
    db: AsyncSession,
    user_id: int,
    page: int,
    page_size: int,
    search: Optional[str] = None,
) -> tuple[list[SentenceCollection], int]:
    """返回用户收藏句子的分页列表。

    结果按 ``created_at`` 倒序排列（最新在前）。当提供 ``search`` 时，
    仅返回包含该搜索字符串的句子（不区分大小写）。

    Args:
        db: 当前活跃的异步会话。
        user_id: 所属用户的 id。
        page: 从 1 开始的页码。
        page_size: 每页条数。
        search: 可选，不区分大小写的句子搜索。

    Returns:
        ``(items, total)`` 元组。
    """
    conditions = [SentenceCollection.user_id == user_id]
    if search:
        conditions.append(SentenceCollection.sentence.ilike(f"%{search}%"))

    count_stmt = (
        select(func.count())
        .select_from(SentenceCollection)
        .where(*conditions)
    )
    total = (await db.execute(count_stmt)).scalar() or 0

    offset = (page - 1) * page_size
    data_stmt = (
        select(SentenceCollection)
        .where(*conditions)
        .order_by(SentenceCollection.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    items = list((await db.execute(data_stmt)).scalars().all())
    return items, total


async def get_sentence(
    db: AsyncSession, user_id: int, sentence_id: int
) -> Optional[SentenceCollection]:
    """获取单个收藏句子，限定在所属用户范围内。

    Args:
        db: 当前活跃的异步会话。
        user_id: 所属用户的 id。
        sentence_id: 句子收藏记录的主键。

    Returns:
        :class:`SentenceCollection`，未找到时返回 ``None``。
    """
    result = await db.execute(
        select(SentenceCollection).where(
            SentenceCollection.id == sentence_id,
            SentenceCollection.user_id == user_id,
        )
    )
    return result.scalars().first()


async def update_sentence(
    db: AsyncSession, sentence: SentenceCollection, data: dict
) -> SentenceCollection:
    """对已有收藏句子应用字段更新。

    Args:
        db: 当前活跃的异步会话。
        sentence: 待更新的 :class:`SentenceCollection` 实例。
        data: 属性名到新值的映射。

    Returns:
        更新后并刷新属性的 :class:`SentenceCollection`。
    """
    for key, value in data.items():
        setattr(sentence, key, value)
    await db.flush()
    await db.refresh(sentence)
    return sentence


async def delete_sentence(
    db: AsyncSession, sentence: SentenceCollection
) -> None:
    """从数据库中删除一个收藏句子。

    Args:
        db: 当前活跃的异步会话。
        sentence: 待删除的 :class:`SentenceCollection` 实例。
    """
    await db.delete(sentence)
    await db.flush()


# ---- 阅读历史 ----------------------------------------------------------------


async def get_or_create_history(
    db: AsyncSession, user_id: int, article_id: int
) -> ReadingHistory:
    """为用户获取或创建阅读会话记录（upsert）。

    每个用户对每篇文章只保留一条记录（唯一约束）。若记录已存在，
    则更新 ``started_at`` 为当前时间、重置 ``ended_at`` 和
    ``duration_seconds``、递增 ``read_count``，标记新一次阅读会话
    的开始。若不存在则创建新记录。

    AI 活动日志和对话消息通过 ``history_id`` 关联到此记录，生成阅读
    总结时按 ``created_at >= started_at`` 过滤以隔离每次会话的数据。

    Args:
        db: 当前活跃的异步会话。
        user_id: 执行阅读操作的用户 id。
        article_id: 正在阅读的文章。

    Returns:
        新建或更新后的 :class:`ReadingHistory`。
    """
    result = await db.execute(
        select(ReadingHistory).where(
            ReadingHistory.user_id == user_id,
            ReadingHistory.article_id == article_id,
        )
    )
    existing = result.scalars().first()

    if existing is not None:
        # 重新阅读：更新 started_at，重置会话数据，递增 read_count。
        existing.started_at = func.now()
        existing.ended_at = None
        existing.duration_seconds = None
        existing.read_count += 1
        await db.flush()
        await db.refresh(existing)
        return existing

    # 首次阅读：创建新记录。
    history = ReadingHistory(
        user_id=user_id,
        article_id=article_id,
    )
    db.add(history)
    await db.flush()
    await db.refresh(history)
    return history


async def update_history(
    db: AsyncSession, history: ReadingHistory, data: dict
) -> ReadingHistory:
    """对已有阅读历史记录应用字段更新。

    通常用于在阅读会话结束时记录 ``ended_at`` 和 ``duration_seconds``。

    Args:
        db: 当前活跃的异步会话。
        history: 待更新的 :class:`ReadingHistory` 实例。
        data: 属性名到新值的映射。

    Returns:
        更新后并刷新属性的 :class:`ReadingHistory`。
    """
    for key, value in data.items():
        setattr(history, key, value)
    await db.flush()
    await db.refresh(history)
    return history


async def get_history(
    db: AsyncSession, user_id: int, history_id: int
) -> Optional[ReadingHistory]:
    """获取单条阅读历史记录，限定在所属用户范围内。

    Args:
        db: 当前活跃的异步会话。
        user_id: 所属用户的 id。
        history_id: 历史记录的主键。

    Returns:
        :class:`ReadingHistory`，未找到时返回 ``None``。
    """
    result = await db.execute(
        select(ReadingHistory).where(
            ReadingHistory.id == history_id,
            ReadingHistory.user_id == user_id,
        )
    )
    return result.scalars().first()


async def list_histories(
    db: AsyncSession, user_id: int, page: int, page_size: int
) -> tuple[list[ReadingHistory], int]:
    """返回用户阅读历史的分页列表。

    结果按 ``started_at`` 倒序排列（最近阅读的在前），因此重新阅读
    某篇文章会将其置顶。

    Args:
        db: 当前活跃的异步会话。
        user_id: 所属用户的 id。
        page: 从 1 开始的页码。
        page_size: 每页条数。

    Returns:
        ``(items, total)`` 元组。
    """
    count_stmt = (
        select(func.count())
        .select_from(ReadingHistory)
        .where(ReadingHistory.user_id == user_id)
    )
    total = (await db.execute(count_stmt)).scalar() or 0

    offset = (page - 1) * page_size
    data_stmt = (
        select(ReadingHistory)
        .where(ReadingHistory.user_id == user_id)
        .order_by(ReadingHistory.started_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    items = list((await db.execute(data_stmt)).scalars().all())
    return items, total


async def list_histories_with_article(
    db: AsyncSession, user_id: int, page: int, page_size: int
) -> tuple[list[tuple[ReadingHistory, Optional[str]]], int]:
    """返回带有文章标题的阅读历史分页列表。

    将 ``reading_histories`` 与 ``articles`` 连接，为每条历史记录附上
    文章标题。结果按 ``started_at`` 倒序排列（最近阅读的在前），因此
    重新阅读某篇文章会将其置顶。

    Args:
        db: 当前活跃的异步会话。
        user_id: 所属用户的 id。
        page: 从 1 开始的页码。
        page_size: 每页条数。

    Returns:
        ``(items, total)`` 元组，其中每个 item 是一个
        ``(ReadingHistory, article_title)`` 元组。
    """
    count_stmt = (
        select(func.count())
        .select_from(ReadingHistory)
        .where(ReadingHistory.user_id == user_id)
    )
    total = (await db.execute(count_stmt)).scalar() or 0

    offset = (page - 1) * page_size
    data_stmt = (
        select(ReadingHistory, Article.title)
        .outerjoin(Article, ReadingHistory.article_id == Article.id)
        .where(ReadingHistory.user_id == user_id)
        .order_by(ReadingHistory.started_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    result = await db.execute(data_stmt)
    items = [(row[0], row[1]) for row in result.all()]
    return items, total
