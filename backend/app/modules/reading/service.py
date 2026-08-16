"""阅读模块的业务逻辑层。

该服务层位于 HTTP 路由与仓库层之间，负责领域规则：校验文章是否存在、
持久化单词/句子收藏和阅读历史。
"""

import re
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.vocabulary_planner import VocabularyPlanner
from app.core.exceptions import BizException, CODE_VALIDATION_ERROR
from app.modules.article.models import Article
from app.modules.article.repository import get_article_by_id
from app.modules.reading import repository as repo
from app.modules.reading.models import MasteryLevel
from app.modules.word_bank.models import WordLevel
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
    VocabularyPlanOut,
    WordCollectionCreate,
    WordCollectionOut,
    WordCollectionUpdate,
    WordListResponse,
)
from app.modules.users.models import User
from app.modules.word_bank.repository import get_levels_for_words

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
        raise BizException("文章不存在", code=ARTICLE_NOT_FOUND_CODE)
    return article


# ---- 单词收藏服务 ----------------------------------------------------------


async def _attach_levels(
    db: AsyncSession, outs: list[WordCollectionOut]
) -> list[WordCollectionOut]:
    """批量查询分级词库并填充 ``WordCollectionOut.levels``。

    等级为派生字段，由词库（``word_bank``）按单词批量查询后写入，
    避免逐个查询。未收录的词等级为空列表。
    """
    if not outs:
        return outs
    words = [out.word.strip().lower() for out in outs]
    levels = await get_levels_for_words(db, words)
    for out in outs:
        out.levels = levels.get(out.word.strip().lower(), [])
    return outs


def extract_short_meaning(expl: Optional[str]) -> Optional[str]:
    """从 AI 解释（markdown）中提取简短释义。

    简短释义 = 单词的核心含义词条列表（如 ``"主管、高管、行政的、执行的"``），
    最多 4 个，用顿号连接，不含解释性描述。AI 解释由 LLM 生成，格式存在
    多种变体（带编号、带加粗、纯文本、极简等），本函数按行解析并兼容。

    Args:
        expl: 完整的 AI 解释文本。

    Returns:
        提取出的简短释义；无法提取时返回 ``None``。
    """
    if not expl or not expl.strip():
        return None
    text = expl.strip()

    # 定位通用释义段落（多种标记形式）
    m = re.search(
        r"(?:\*\*)?通用释义(?:\*\*)?\s*[：:]\s*([\s\S]*)",
        text,
        re.IGNORECASE,
    )
    if m:
        section = re.split(
            r"(?:\*\*)?语境释义(?:\*\*)?\s*[：:]|例句\s*[：:]",
            m.group(1),
            maxsplit=1,
        )[0]
        terms = _extract_meaning_terms(section)
        if terms:
            return "、".join(terms[:4])

        # 通用释义段落存在但无词条，回退到段落第一行
        first_line = next(
            (l.strip() for l in section.split("\n") if l.strip()), None
        )
        if first_line:
            plain = re.sub(r"[#>*`]", "", first_line).strip()
            return plain[:40]

    # 无通用释义段落（极简格式）：尝试 "释义/含义：内容" 行，截断 40 字
    m2 = re.search(
        r"(?:\*\*)?(?:释义|含义)(?:\*\*)?\s*[：:]\s*(.+)",
        text,
        re.IGNORECASE,
    )
    if m2:
        plain = re.sub(r"[#>*`]", "", m2.group(1)).strip()
        if plain:
            return plain[:40]

    # 最后回退：整个解释前 40 字（去 markdown）
    plain = re.sub(r"[#>*`]", "", text)
    return plain[:40]


def _extract_meaning_terms(section: str) -> list[str]:
    """从通用释义段落中提取含义词条列表（去重，最多 4 个）。

    每条释义形如 ``"主管，高管：公司中负责决策的人"``，冒号前是含义词
    部分；可能含编号、加粗、"含义一"前缀等变体。逐个含义词拆分提取。

    Args:
        section: 通用释义段落文本。

    Returns:
        按出现顺序去重后的含义词条列表（最多 4 个）。
    """
    terms: list[str] = []
    for line in section.split("\n"):
        line = line.strip()
        if not line:
            continue
        # 去掉编号前缀和加粗标记
        line = re.sub(r"^\d+[.、]\s*", "", line).replace("**", "").strip()
        if not line:
            continue
        # 去掉 "含义一：/含义二：" 等标签前缀
        line = re.sub(r"^含义[一二三四五六七八九十][：:]\s*", "", line).strip()
        if not line:
            continue

        # 分离含义词部分（第一个冒号前）；无冒号则整行即含义词部分
        head = line
        m = re.match(r"^(.+?)\s*[：:]\s*(.+)$", line)
        if m:
            head = m.group(1).strip()

        # 先去掉括号注解（如（动词）（医学）），避免括号内顿号干扰拆分
        head = re.sub(r"[（(][^（）()]*[）)]", "", head).strip()
        if not head:
            continue

        # 再按逗号/顿号拆分为独立含义词
        for part in re.split(r"[，,、·]", head):
            part = part.strip()
            if not part:
                continue
            if part not in terms:
                terms.append(part)
            if len(terms) >= 4:
                return terms

    return terms


async def save_word(
    db: AsyncSession, user_id: int, data: WordCollectionCreate
) -> WordCollectionOut:
    """为用户保存（upsert）一个收藏的单词。

    若请求未提供 ``short_meaning`` 但提供了 ``ai_explanation``，则自动
    从解释中提取第一条释义作为简短释义。

    Args:
        db: 当前活跃的异步会话。
        user_id: 执行收藏操作的用户 id。
        data: 单词收藏的创建载荷。

    Returns:
        新建或更新后单词对应的 :class:`WordCollectionOut`。
    """
    short_meaning = data.short_meaning
    if not short_meaning and data.ai_explanation:
        short_meaning = extract_short_meaning(data.ai_explanation)

    word = await repo.get_or_create_word(
        db,
        user_id=user_id,
        word=data.word,
        context=data.context,
        article_id=data.article_id,
        ai_explanation=data.ai_explanation,
        short_meaning=short_meaning,
    )
    out = WordCollectionOut.model_validate(word)
    await _attach_levels(db, [out])
    return out


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
    items_out = [WordCollectionOut.model_validate(w) for w in items]
    await _attach_levels(db, items_out)
    return WordListResponse(items=items_out, total=total)


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
        raise BizException("单词不存在", code=WORD_NOT_FOUND_CODE)

    update_data = data.model_dump(exclude_unset=True)
    if update_data:
        word = await repo.update_word(db, word, update_data)
    out = WordCollectionOut.model_validate(word)
    await _attach_levels(db, [out])
    return out


async def mark_word_studied(
    db: AsyncSession, user_id: int, word_id: int
) -> WordCollectionOut:
    """把某个收藏单词标记为已学习一次（背诵场景）。

    由服务端权威递增 ``study_count``、更新 ``last_studied_at``，并把
    ``mastery_level`` 推进到 ``mastered``（用户"记住了"即视为掌握）。

    Args:
        db: 当前活跃的异步会话。
        user_id: 所属用户的 id。
        word_id: 单词收藏记录的主键。

    Returns:
        更新后单词的 :class:`WordCollectionOut`。

    Raises:
        BizException: 若该用户不存在指定 id 的单词（错误码 ``90003``）。
    """
    word = await repo.get_word(db, user_id, word_id)
    if word is None:
        raise BizException("单词不存在", code=WORD_NOT_FOUND_CODE)
    word = await repo.increment_word_study(db, word)
    out = WordCollectionOut.model_validate(word)
    await _attach_levels(db, [out])
    return out


async def get_vocabulary_study_plan(
    db: AsyncSession, user: User, count: int, level: Optional[str] = None
) -> VocabularyPlanOut:
    """生成一次生词背诵方案（有序选词 + 背诵建议）。

    由 :class:`VocabularyPlanner` 调用数据工具 + 单次 LLM 调用生成；
    LLM 失败时自动降级为规则选词，因此该接口通常不报错。

    Args:
        db: 当前活跃的异步会话。
        user: 已认证用户。
        count: 本次要背诵的单词数量。
        level: 可选，按分级词库等级过滤（如 ``cet4``）；None 为全部。

    Returns:
        有序的单词序列与背诵建议的 :class:`VocabularyPlanOut`。

    Raises:
        BizException: 若 ``level`` 非法（错误码 ``10000``）。
    """
    if level is not None and level not in {lv.value for lv in WordLevel}:
        raise BizException(f"无效的词汇等级：{level}", code=CODE_VALIDATION_ERROR)

    result = await VocabularyPlanner().plan(db, user, count, level=level)
    words = [
        WordCollectionOut.model_validate(result.words_by_id[i])
        for i in result.word_ids
        if i in result.words_by_id
    ]
    await _attach_levels(db, words)
    return VocabularyPlanOut(
        words=words,
        note=result.note,
        total=len(words),
        generated_by=result.generated_by,
    )


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
        raise BizException("单词不存在", code=WORD_NOT_FOUND_CODE)
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
        raise BizException("句子不存在", code=SENTENCE_NOT_FOUND_CODE)
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
        raise BizException("句子不存在", code=SENTENCE_NOT_FOUND_CODE)

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
        raise BizException("阅读记录不存在", code=HISTORY_NOT_FOUND_CODE)

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
