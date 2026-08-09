"""AI 模块的 HTTP 路由。

提供五个 AI 流式端点（Server-Sent Events），分别用于单词解释、
句子分析、句子翻译、段落摘要和文章聊天；此外还提供对话历史的
查询端点。所有端点均需认证。

SSE 协议
-------------
每个流式端点以 ``text/event-stream`` 帧的形式输出，格式如下::

    data: {"content": "<chunk>"}\\n\\n

当流正常完成时，会发送一个终止帧::

    data: {"done": true}\\n\\n

若在流式过程中发生错误，则改为发送错误帧::

    data: {"error": "<message>"}\\n\\n
"""

import json
from collections.abc import AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.api.deps import CurrentUser, DbSession, RedisClient
from app.core.exceptions import BizException
from app.core.response import ResponseModel, success
from app.modules.ai.schemas import (
    AnalyzeSentenceRequest,
    ChatRequest,
    ConversationListResponse,
    ExplainWordRequest,
    ParagraphSummaryRequest,
    SentenceTranslationRequest,
)
from app.modules.ai.service import (
    analyze_sentence,
    chat,
    explain_word,
    list_conversations,
    paragraph_summary,
    translate_sentence,
)

router = APIRouter(prefix="/ai", tags=["ai"])


# ---- SSE 辅助 ---------------------------------------------------------------


def _sse_stream(
    generator: AsyncGenerator[str, None],
) -> AsyncGenerator[str, None]:
    """将服务层的异步生成器包装为 SSE 字节流。

    每个 yield 的分块被封装为 ``data: {"content": ...}\\n\\n`` 帧。
    正常完成时发送 ``data: {"done": true}\\n\\n`` 帧。
    :class:`BizException` 实例会使用异常消息生成
    ``data: {"error": ...}\\n\\n`` 帧；其他异常则使用 ``str(exc)``。

    Args:
        generator: 服务层产出 ``str`` 分块的异步生成器。

    Yields:
        SSE 格式的 ``str`` 帧。
    """

    async def event_stream() -> AsyncGenerator[str, None]:
        try:
            async for chunk in generator:
                yield f"data: {json.dumps({'content': chunk})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
        except BizException as e:
            yield f"data: {json.dumps({'error': e.message})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return event_stream()


# ---- AI 流式端点（SSE） -----------------------------------------------------


@router.post(
    "/explain-word",
    summary="Explain a word in context (streaming)",
)
async def explain_word_endpoint(
    data: ExplainWordRequest,
    db: DbSession,
    current_user: CurrentUser,
    redis: RedisClient,
) -> StreamingResponse:
    """以 Server-Sent Events 形式流式输出某个单词的 AI 解释。"""
    return StreamingResponse(
        _sse_stream(explain_word(db, current_user, data, redis)),
        media_type="text/event-stream",
    )


@router.post(
    "/analyze-sentence",
    summary="Analyze a sentence structure (streaming)",
)
async def analyze_sentence_endpoint(
    data: AnalyzeSentenceRequest,
    db: DbSession,
    current_user: CurrentUser,
    redis: RedisClient,
) -> StreamingResponse:
    """以 Server-Sent Events 形式流式输出句子的 AI 结构分析。"""
    return StreamingResponse(
        _sse_stream(analyze_sentence(db, current_user, data, redis)),
        media_type="text/event-stream",
    )


@router.post(
    "/translate-sentence",
    summary="Translate a sentence into Chinese (streaming)",
)
async def translate_sentence_endpoint(
    data: SentenceTranslationRequest,
    db: DbSession,
    current_user: CurrentUser,
    redis: RedisClient,
) -> StreamingResponse:
    """以 Server-Sent Events 形式流式输出句子的 AI 翻译。"""
    return StreamingResponse(
        _sse_stream(translate_sentence(db, current_user, data, redis)),
        media_type="text/event-stream",
    )


@router.post(
    "/paragraph-summary",
    summary="Summarize a paragraph (streaming)",
)
async def paragraph_summary_endpoint(
    data: ParagraphSummaryRequest,
    db: DbSession,
    current_user: CurrentUser,
    redis: RedisClient,
) -> StreamingResponse:
    """以 Server-Sent Events 形式流式输出段落的 AI 摘要。"""
    return StreamingResponse(
        _sse_stream(paragraph_summary(db, current_user, data, redis)),
        media_type="text/event-stream",
    )


@router.post(
    "/chat",
    summary="Chat about the current article (streaming)",
)
async def chat_endpoint(
    data: ChatRequest,
    db: DbSession,
    current_user: CurrentUser,
    redis: RedisClient,
) -> StreamingResponse:
    """以 Server-Sent Events 形式流式输出围绕当前文章的 AI 聊天回复。"""
    return StreamingResponse(
        _sse_stream(chat(db, current_user, data, redis)),
        media_type="text/event-stream",
    )


# ---- AI 对话端点 -----------------------------------------------------------


@router.get(
    "/conversations/{article_id}",
    response_model=ResponseModel[ConversationListResponse],
    summary="List chat history for an article",
)
async def list_conversations_endpoint(
    article_id: int,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """列出当前用户针对某篇文章的 AI 聊天历史。

    最多返回 50 条最近的消息，按时间顺序排列，以便前端在页面刷新后
    恢复聊天会话。
    """
    result = await list_conversations(db, current_user.id, article_id)
    return success(result)
