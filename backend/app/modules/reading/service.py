"""阅读模块的业务逻辑层。

该服务层位于 HTTP 路由与仓库层之间，负责领域规则：校验文章是否存在、
持久化单词/句子收藏和阅读历史。
"""

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BizException
from app.modules.article.models import Article
from app.modules.article.repository import get_article_by_id
from app.modules.reading import repository as repo
from app.modules.reading.models import MasteryLevel
from app.modules.reading.schemas import (
    ReadingHistoryCreate,
    ReadingHistoryOut,
    ReadingHistoryUpdate,
    ReadingHistoryWithArticleListResponse,
    ReadingHistoryWithArticleOut,
    SentenceCollectionCreate,
    SentenceCollectionOut,
    SentenceCollectionUpdate,
    SentenceListResponse,
    WordCollectionCreate,
    WordCollectionOut,
    WordCollectionUpdate,
    WordListResponse,
)

# ---- 业务错误码 -------------------------------------------------------------
# 文章未找到（与文章模块的错误码共用）。
ARTICLE_NOT_FOUND_CODE = 90002
# 当前用户未找到该收藏单词。
WORD_NOT_FOUND_CODE = 90003
# 当前用户未找到该收藏句子。
SENTENCE_NOT_FOUND_CODE = 90004
# 当前用户未找到该阅读历史记录。
HISTORY_NOT_FOUND_CODE = 90005


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


# ---- 单词收藏服务 ----------------------------------------------------------


async def save_word(
    db: AsyncSession, user_id: int, data: WordCollectionCreate
) -> WordCollectionOut:
    """为用户保存（upsert）一个收藏的单词。

    Args:
        db: 当前活跃的异步会话。
        user_id: 执行收藏操作的用户 id。
        data: 单词收藏的创建载荷。

    Returns:
        新建或更新后单词对应的 :class:`WordCollectionOut`。
    """
    word = await repo.get_or_create_word(
        db,
        user_id=user_id,
        word=data.word,
        context=data.context,
        article_id=data.article_id,
        ai_explanation=data.ai_explanation,
    )
    return WordCollectionOut.model_validate(word)


async def list_words(
    db: AsyncSession,
    user_id: int,
    page: int,
    page_size: int,
    mastery_level: Optional[MasteryLevel] = None,
    search: Optional[str] = None,
) -> WordListResponse:
    """返回用户收藏单词的分页列表。

    Args:
        db: 当前活跃的异步会话。
        user_id: 所属用户的 id。
        page: 从 1 开始的页码。
        page_size: 每页条数。
        mastery_level: 可选，按掌握程度过滤。
        search: 可选，不区分大小写的单词搜索。

    Returns:
        包含序列化条目和总数的 :class:`WordListResponse`。
    """
    items, total = await repo.list_words(
        db, user_id, page, page_size, mastery_level, search
    )
    return WordListResponse(
        items=[WordCollectionOut.model_validate(w) for w in items],
        total=total,
    )


async def update_word_mastery(
    db: AsyncSession,
    user_id: int,
    word_id: int,
    data: WordCollectionUpdate,
) -> WordCollectionOut:
    """更新某个收藏单词的掌握程度和/或学习次数。

    Args:
        db: 当前活跃的异步会话。
        user_id: 所属用户的 id。
        word_id: 单词收藏记录的主键。
        data: 部分更新载荷。

    Returns:
        反映更新后单词的 :class:`WordCollectionOut`。

    Raises:
        BizException: 若该用户不存在指定 id 的单词
            （错误码 ``90003``）。
    """
    word = await repo.get_word(db, user_id, word_id)
    if word is None:
        raise BizException("word not found", code=WORD_NOT_FOUND_CODE)

    update_data = data.model_dump(exclude_unset=True)
    if update_data:
        word = await repo.update_word(db, word, update_data)
    return WordCollectionOut.model_validate(word)


async def remove_word(db: AsyncSession, user_id: int, word_id: int) -> None:
    """删除一个收藏单词。

    Args:
        db: 当前活跃的异步会话。
        user_id: 所属用户的 id。
        word_id: 单词收藏记录的主键。

    Raises:
        BizException: 若该用户不存在指定 id 的单词
            （错误码 ``90003``）。
    """
    word = await repo.get_word(db, user_id, word_id)
    if word is None:
        raise BizException("word not found", code=WORD_NOT_FOUND_CODE)
    await repo.delete_word(db, word)


# ---- 句子收藏服务 ----------------------------------------------------------


async def save_sentence(
    db: AsyncSession, user_id: int, data: SentenceCollectionCreate
) -> SentenceCollectionOut:
    """为用户保存（upsert）一个收藏的句子。

    如果该用户已存在相同句子文本，则更新已有行的 note 和 article_id，
    而不是创建重复记录。

    Args:
        db: 当前活跃的异步会话。
        user_id: 执行收藏操作的用户 id。
        data: 句子收藏的创建载荷。

    Returns:
        新建或更新后句子对应的 :class:`SentenceCollectionOut`。
    """
    sentence = await repo.get_or_create_sentence(db, user_id, data)
    return SentenceCollectionOut.model_validate(sentence)


async def list_sentences(
    db: AsyncSession,
    user_id: int,
    page: int,
    page_size: int,
    search: Optional[str] = None,
) -> SentenceListResponse:
    """返回用户收藏句子的分页列表。

    Args:
        db: 当前活跃的异步会话。
        user_id: 所属用户的 id。
        page: 从 1 开始的页码。
        page_size: 每页条数。
        search: 可选，不区分大小写的句子搜索。

    Returns:
        包含序列化条目和总数的 :class:`SentenceListResponse`。
    """
    items, total = await repo.list_sentences(
        db, user_id, page, page_size, search
    )
    return SentenceListResponse(
        items=[SentenceCollectionOut.model_validate(s) for s in items],
        total=total,
    )


async def remove_sentence(
    db: AsyncSession, user_id: int, sentence_id: int
) -> None:
    """删除一个收藏句子。

    Args:
        db: 当前活跃的异步会话。
        user_id: 所属用户的 id。
        sentence_id: 句子收藏记录的主键。

    Raises:
        BizException: 若该用户不存在指定 id 的句子
            （错误码 ``90004``）。
    """
    sentence = await repo.get_sentence(db, user_id, sentence_id)
    if sentence is None:
        raise BizException("sentence not found", code=SENTENCE_NOT_FOUND_CODE)
    await repo.delete_sentence(db, sentence)


async def update_sentence_note(
    db: AsyncSession,
    user_id: int,
    sentence_id: int,
    data: SentenceCollectionUpdate,
) -> SentenceCollectionOut:
    """更新某个收藏句子的备注。

    Args:
        db: 当前活跃的异步会话。
        user_id: 所属用户的 id。
        sentence_id: 句子收藏记录的主键。
        data: 部分更新载荷（``note``）。

    Returns:
        反映更新后句子的 :class:`SentenceCollectionOut`。

    Raises:
        BizException: 若该用户不存在指定 id 的句子
            （错误码 ``90004``）。
    """
    sentence = await repo.get_sentence(db, user_id, sentence_id)
    if sentence is None:
        raise BizException("sentence not found", code=SENTENCE_NOT_FOUND_CODE)

    update_data = data.model_dump(exclude_unset=True)
    if update_data:
        sentence = await repo.update_sentence(db, sentence, update_data)
    return SentenceCollectionOut.model_validate(sentence)


# ---- 阅读历史服务 ----------------------------------------------------------


async def start_reading(
    db: AsyncSession, user_id: int, data: ReadingHistoryCreate
) -> ReadingHistoryOut:
    """为某篇文章开启（或恢复）一次阅读会话。

    校验文章是否存在。如果用户已有针对该文章的历史记录，则将
    ``read_count`` 加 1，并为新会话重置时间戳；否则创建一条新记录。

    Args:
        db: 当前活跃的异步会话。
        user_id: 执行阅读操作的用户 id。
        data: 阅读历史的创建载荷。

    Returns:
        新建或更新后记录对应的 :class:`ReadingHistoryOut`。

    Raises:
        BizException: 若文章不存在（错误码 ``90002``）。
    """
    await _get_article_or_raise(db, data.article_id)
    history = await repo.get_or_create_history(db, user_id, data.article_id)
    return ReadingHistoryOut.model_validate(history)


async def end_reading(
    db: AsyncSession,
    user_id: int,
    history_id: int,
    data: ReadingHistoryUpdate,
) -> ReadingHistoryOut:
    """结束阅读会话，记录结束时间与时长。

    Args:
        db: 当前活跃的异步会话。
        user_id: 所属用户的 id。
        history_id: 阅读历史记录的主键。
        data: 部分更新载荷（``ended_at`` / ``duration_seconds``）。

    Returns:
        反映更新后记录的 :class:`ReadingHistoryOut`。

    Raises:
        BizException: 若该用户不存在指定 id 的历史记录
            （错误码 ``90005``）。
    """
    history = await repo.get_history(db, user_id, history_id)
    if history is None:
        raise BizException("history not found", code=HISTORY_NOT_FOUND_CODE)

    update_data = data.model_dump(exclude_unset=True)
    if update_data:
        history = await repo.update_history(db, history, update_data)
    return ReadingHistoryOut.model_validate(history)


async def list_histories(
    db: AsyncSession, user_id: int, page: int, page_size: int
) -> ReadingHistoryWithArticleListResponse:
    """返回用户阅读历史的分页列表。

    通过连接查询为每条记录附上文章标题，以便客户端无需第二次请求即可
    展示阅读的是哪篇文章。

    Args:
        db: 当前活跃的异步会话。
        user_id: 所属用户的 id。
        page: 从 1 开始的页码。
        page_size: 每页条数。

    Returns:
        包含序列化条目（含 ``article_title``）和总数的
        :class:`ReadingHistoryWithArticleListResponse`。
    """
    items, total = await repo.list_histories_with_article(
        db, user_id, page, page_size
    )
    serialized: list[ReadingHistoryWithArticleOut] = []
    for history, article_title in items:
        obj = ReadingHistoryWithArticleOut.model_validate(history)
        obj.article_title = article_title
        serialized.append(obj)
    return ReadingHistoryWithArticleListResponse(
        items=serialized,
        total=total,
    )
