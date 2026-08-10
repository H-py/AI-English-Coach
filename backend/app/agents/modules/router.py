"""Agent 模块的 HTTP 路由。

提供阅读教练 Agent 的流式聊天端点（Server-Sent Events），将 Agent
的 ReAct 推理过程（思考、工具调用、工具结果、最终回答）实时推送
给前端。所有端点均需认证。

SSE 协议
-------------
每个流式端点以 ``text/event-stream`` 帧的形式输出，格式如下::

    data: {"type": "thinking", "content": "..."}\\n\\n
    data: {"type": "tool_call", "tool": "...", "arguments": {...}}\\n\\n
    data: {"type": "tool_result", "tool": "...", "content": "...", "data": {...}}\\n\\n
    data: {"type": "content", "content": "..."}\\n\\n
    data: {"type": "done"}\\n\\n

若在流式过程中发生错误，则发送错误帧::

    data: {"type": "error", "message": "..."}\\n\\n
"""

import json
import logging
from collections.abc import AsyncGenerator

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.agents.modules import repository as agent_repo
from app.agents.modules.schemas import (
    AgentChatRequest,
    AgentConversationDetailOut,
    AgentConversationOut,
    AgentSessionDetailOut,
    AgentSessionOut,
)
from app.agents.modules.service import run_reading_coach_agent
from app.api.deps import CurrentUser, DbSession, RedisClient
from app.core.response import success

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents", tags=["agents"])


@router.post(
    "/reading-coach/chat",
    summary="Chat with reading coach agent (streaming)",
)
async def reading_coach_agent_endpoint(
    data: AgentChatRequest,
    db: DbSession,
    current_user: CurrentUser,
    redis: RedisClient,
) -> StreamingResponse:
    """以 Server-Sent Events 形式流式输出阅读教练 Agent 的执行过程。

    Agent 会进行多步推理（Thought → Action → Observation），每一步
    都会以 SSE 帧的形式实时推送，包括思考过程、工具调用和工具结果。
    最终回答以 ``content`` 帧分块推送，流结束时发送 ``done`` 帧。
    """
    return StreamingResponse(
        _safe_stream(
            run_reading_coach_agent(
                db=db,
                redis=redis,
                user=current_user,
                article_id=data.article_id,
                message=data.message,
                history_id=data.history_id,
                conversation_id=data.conversation_id,
            )
        ),
        media_type="text/event-stream",
    )


@router.get(
    "/sessions",
    summary="List agent sessions",
)
async def list_agent_sessions(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict:
    """分页列出当前用户的 Agent 会话记录。

    返回最近执行的 Agent 会话列表，按创建时间倒序排列，
    供前端"智能学习"页面的左侧历史栏使用。
    """
    items, total = await agent_repo.list_sessions(
        db, current_user.id, page=page, page_size=page_size
    )
    return success({
        "items": [AgentSessionOut.model_validate(s).model_dump() for s in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    })


@router.get(
    "/sessions/{session_id}",
    summary="Get agent session detail",
)
async def get_agent_session_detail(
    session_id: int,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """获取指定 Agent 会话的详情（含执行步骤）。

    供前端点击历史记录后加载完整会话内容，包括思考流程、
    工具调用和最终回答。
    """
    session = await agent_repo.get_session_with_steps(
        db, session_id, current_user.id
    )
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return success(AgentSessionDetailOut.model_validate(session).model_dump())


# ---- Agent 对话 -------------------------------------------------------------


@router.get(
    "/conversations",
    summary="List agent conversations",
)
async def list_agent_conversations(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict:
    """分页列出当前用户的 Agent 对话记录。

    返回最近活跃的对话列表，按更新时间倒序排列，
    供前端"智能学习"页面的对话历史栏使用。
    """
    items, total = await agent_repo.list_conversations(
        db, current_user.id, page=page, page_size=page_size
    )
    return success({
        "items": [
            AgentConversationOut.model_validate(c).model_dump()
            for c in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    })


@router.get(
    "/conversations/{conversation_id}",
    summary="Get agent conversation detail",
)
async def get_agent_conversation_detail(
    conversation_id: int,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """获取指定 Agent 对话的详情（含所有会话和步骤）。

    供前端点击对话后加载完整的多轮对话内容，包括每一轮的
    思考流程、工具调用和最终回答。
    """
    conversation = await agent_repo.get_conversation_with_sessions(
        db, conversation_id, current_user.id
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="对话不存在")
    return success(
        AgentConversationDetailOut.model_validate(conversation).model_dump()
    )


@router.delete(
    "/conversations/{conversation_id}",
    summary="Delete agent conversation",
)
async def delete_agent_conversation(
    conversation_id: int,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """删除指定 Agent 对话及其所有会话和步骤记录。

    级联删除对话下的所有 AgentSession 和 AgentStepRecord。
    """
    deleted = await agent_repo.delete_conversation(
        db, conversation_id, current_user.id
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="对话不存在")
    return success({"id": conversation_id})


def _safe_stream(
    generator: AsyncGenerator[str, None],
) -> AsyncGenerator[str, None]:
    """包装服务层生成器，捕获未预期的异常并转为错误 SSE 帧。

    服务层内部已对 Agent 执行过程中的异常进行了处理，但此处仍需
    兜底捕获持久化或其他环节可能抛出的异常，确保前端始终能收到
    一个错误帧而非连接中断。

    Args:
        generator: 服务层产出 SSE 帧 ``str`` 的异步生成器。

    Yields:
        SSE 格式的 ``str`` 帧。
    """

    async def event_stream() -> AsyncGenerator[str, None]:
        try:
            async for frame in generator:
                yield frame
        except Exception as e:
            logger.exception("Unexpected error in agent stream")
            payload = {"type": "error", "message": str(e)}
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            # 兜底发送 done 帧，确保前端能正确结束流式状态。
            # conversation_id 已在流开始时通过 conversation_started 事件发送。
            done_payload = {"type": "done"}
            yield f"data: {json.dumps(done_payload, ensure_ascii=False)}\n\n"

    return event_stream()
