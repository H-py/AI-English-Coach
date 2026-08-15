"""阅读模块的 HTTP 路由。

提供单词收藏、句子收藏和阅读历史的标准 REST 端点。
所有端点均需认证。
"""

from typing import Optional

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.core.response import ResponseModel, success
from app.modules.reading.models import MasteryLevel
from app.modules.reading.schemas import (
    ReadingHistoryCreate,
    ReadingHistoryOut,
    ReadingHistoryUpdate,
    ReadingHistoryWithArticleListResponse,
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
from app.modules.reading.service import (
    end_reading,
    get_vocabulary_study_plan,
    list_histories,
    list_sentences,
    list_words,
    mark_word_studied,
    remove_sentence,
    remove_word,
    save_sentence,
    save_word,
    start_reading,
    update_sentence_note,
    update_word_mastery,
)

router = APIRouter(prefix="/reading", tags=["reading"])


# ---- 单词收藏端点 -----------------------------------------------------------


@router.post(
    "/words",
    response_model=ResponseModel[WordCollectionOut],
    summary="Save a word",
)
async def save_word_endpoint(
    data: WordCollectionCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """为当前用户保存（upsert）一个收藏的单词。"""
    word = await save_word(db, current_user.id, data)
    return success(word)


@router.get(
    "/words",
    response_model=ResponseModel[WordListResponse],
    summary="List collected words",
)
async def list_words_endpoint(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    mastery_level: Optional[MasteryLevel] = Query(default=None),
    search: Optional[str] = Query(default=None, max_length=255),
) -> dict:
    """分页列出当前用户收藏的单词。

    可选按 ``mastery_level``（``new``、``learning``、``familiar``、
    ``mastered``）过滤，和/或按单词文本搜索（不区分大小写）。
    """
    result = await list_words(
        db, current_user.id, page, page_size, mastery_level, search
    )
    return success(result)


@router.put(
    "/words/{word_id}",
    response_model=ResponseModel[WordCollectionOut],
    summary="Update word mastery",
)
async def update_word_endpoint(
    word_id: int,
    data: WordCollectionUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """更新某个收藏单词的掌握程度和/或学习次数。"""
    word = await update_word_mastery(db, current_user.id, word_id, data)
    return success(word)


@router.post(
    "/words/{word_id}/study",
    response_model=ResponseModel[WordCollectionOut],
    summary="Mark a word as studied",
)
async def mark_word_studied_endpoint(
    word_id: int,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """把某个收藏单词标记为已学习一次（背诵场景，服务端递增学习次数）。"""
    word = await mark_word_studied(db, current_user.id, word_id)
    return success(word)


@router.get(
    "/study-plan",
    response_model=ResponseModel[VocabularyPlanOut],
    summary="Get AI vocabulary study plan",
)
async def get_study_plan_endpoint(
    db: DbSession,
    current_user: CurrentUser,
    count: int = Query(default=10, ge=1, le=50),
) -> dict:
    """生成一次生词背诵方案（AI 选词 + 顺序 + 建议；失败降级为规则）。"""
    result = await get_vocabulary_study_plan(db, current_user, count)
    return success(result)


@router.delete(
    "/words/{word_id}",
    response_model=ResponseModel[None],
    summary="Delete a word",
)
async def delete_word_endpoint(
    word_id: int,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """删除当前用户收藏的某个单词。"""
    await remove_word(db, current_user.id, word_id)
    return success(None)


# ---- 句子收藏端点 -----------------------------------------------------------


@router.post(
    "/sentences",
    response_model=ResponseModel[SentenceCollectionOut],
    status_code=201,
    summary="Save a sentence",
)
async def save_sentence_endpoint(
    data: SentenceCollectionCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """为当前用户保存一个收藏的句子。"""
    sentence = await save_sentence(db, current_user.id, data)
    return success(sentence)


@router.get(
    "/sentences",
    response_model=ResponseModel[SentenceListResponse],
    summary="List collected sentences",
)
async def list_sentences_endpoint(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: Optional[str] = Query(default=None, max_length=255),
) -> dict:
    """分页列出当前用户收藏的句子。

    可选按句子文本搜索（不区分大小写）。
    """
    result = await list_sentences(
        db, current_user.id, page, page_size, search
    )
    return success(result)


@router.put(
    "/sentences/{sentence_id}",
    response_model=ResponseModel[SentenceCollectionOut],
    summary="Update sentence note",
)
async def update_sentence_endpoint(
    sentence_id: int,
    data: SentenceCollectionUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """更新当前用户某个收藏句子的备注。"""
    sentence = await update_sentence_note(
        db, current_user.id, sentence_id, data
    )
    return success(sentence)


@router.delete(
    "/sentences/{sentence_id}",
    response_model=ResponseModel[None],
    summary="Delete a sentence",
)
async def delete_sentence_endpoint(
    sentence_id: int,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """删除当前用户收藏的某个句子。"""
    await remove_sentence(db, current_user.id, sentence_id)
    return success(None)


# ---- 阅读历史端点 -----------------------------------------------------------


@router.post(
    "/history",
    response_model=ResponseModel[ReadingHistoryOut],
    status_code=201,
    summary="Start reading",
)
async def start_reading_endpoint(
    data: ReadingHistoryCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """开始一篇文章的新的阅读会话。"""
    history = await start_reading(db, current_user.id, data)
    return success(history)


@router.put(
    "/history/{history_id}",
    response_model=ResponseModel[ReadingHistoryOut],
    summary="End reading",
)
async def end_reading_endpoint(
    history_id: int,
    data: ReadingHistoryUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """结束阅读会话，记录结束时间与时长。"""
    history = await end_reading(db, current_user.id, history_id, data)
    return success(history)


@router.get(
    "/history",
    response_model=ResponseModel[ReadingHistoryWithArticleListResponse],
    summary="List reading history",
)
async def list_history_endpoint(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    """分页列出当前用户的阅读历史。"""
    result = await list_histories(db, current_user.id, page, page_size)
    return success(result)
