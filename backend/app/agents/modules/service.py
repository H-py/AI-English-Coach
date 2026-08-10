"""Agent 模块的服务层。

负责编排 Agent 的完整执行流程：加载文章、构建对话上下文、创建会话
记录、驱动 Agent 执行、将步骤转换为 SSE 帧推送给前端，以及在执行
完毕后持久化对话消息、活动日志和步骤记录。

本模块是 Agent 核心逻辑（``base.py`` / ``reading_coach.py``）与 Web
层（路由）之间的桥梁，确保 Agent 的 ReAct 推理循环与项目的记忆系统、
数据持久化层无缝集成。
"""

import json
import logging
from collections.abc import AsyncGenerator

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentStep
from app.agents.modules import repository as agent_repo
from app.agents.modules.models import AgentConversation
from app.agents.reading_coach import ReadingCoachAgent
from app.core.ai.memory import build_chat_context, maybe_summarize
from app.core.ai.provider import ChatMessage
from app.modules.ai import memory_repository as mem_repo
from app.modules.ai import repository as ai_repo
from app.modules.article.repository import get_article_by_id
from app.modules.users.models import User

logger = logging.getLogger(__name__)


async def run_reading_coach_agent(
    db: AsyncSession,
    redis: aioredis.Redis,
    user: User,
    article_id: int | None,
    message: str,
    history_id: int | None = None,
    conversation_id: int | None = None,
) -> AsyncGenerator[str, None]:
    """执行阅读教练 Agent 并以 SSE 帧流式返回执行过程。

    完整流程：

    1. 处理多轮对话：若 ``conversation_id`` 为 ``None`` 则创建新对话，
       否则加载该对话的历史会话作为对话上下文。
    2. 若 ``article_id`` 不为 ``None``，加载文章并构建带三层记忆的
       对话上下文；否则使用空上下文（Agent 自身的工具可按需获取数据）。
    3. 创建 AgentSession 记录。
    4. 实例化 ReadingCoachAgent 并执行 ReAct 循环。
    5. 逐步将 AgentStep 转换为 SSE 帧并 yield，同时收集最终回答
       和步骤数据。
    6. 执行完毕后持久化结果。当 ``article_id`` 不为 ``None`` 时，
       额外保存对话消息和活动日志并触发摘要；为 ``None`` 时仅保存
       Agent 会话和步骤记录。

    Args:
        db: 当前活跃的异步会话。
        redis: 共享的 Redis 客户端。
        user: 已认证的用户。
        article_id: 对话所围绕的文章 id；独立"智能学习"页面为 ``None``。
        message: 用户输入的消息文本。
        history_id: 可选的阅读历史记录 id。
        conversation_id: 可选的对话 id，用于多轮对话关联。为 ``None``
            时将创建新对话。

    Yields:
        SSE 格式的 ``str`` 帧（``data: {...}\\n\\n``）。
    """
    # ---- 1. 处理多轮对话 ----
    prev_sessions: list = []
    if conversation_id is None:
        # 创建新对话，标题取用户消息前 30 个字符。
        conv = await agent_repo.create_conversation(
            db, user.id, title=message[:30]
        )
        conv_id = conv.id
    else:
        # 加载已有对话的历史会话，用于构建对话上下文。
        prev_sessions = await agent_repo.get_conversation_messages(
            db, conversation_id, user.id
        )
        conv_id = conversation_id

    # 立即将 conversation_id 推送给前端，确保即使后续 Agent 执行出错，
    # 前端也能获取到 conversation_id 用于后续多轮对话。
    yield _sse_frame(
        {"type": "conversation_started", "conversation_id": conv_id}
    )

    # ---- 2. 构建对话上下文 ----
    context_messages: list[ChatMessage] = []

    # 将历史会话的 user_message 和 final_answer 转为对话上下文。
    for s in prev_sessions:
        context_messages.append(
            ChatMessage(role="user", content=s.user_message)
        )
        if s.final_answer:
            context_messages.append(
                ChatMessage(role="assistant", content=s.final_answer)
            )

    if article_id is not None:
        article = await get_article_by_id(db, article_id)
        if article is None:
            yield _sse_frame({"type": "error", "message": "文章不存在"})
            yield _sse_frame(
                {"type": "done", "conversation_id": conv_id}
            )
            return

        # build_chat_context 返回 [system_message, ...history_messages, user_message]。
        # Agent 的 run 方法会自行构建 system 提示和追加 user 消息，因此
        # 这里只需提取中间的历史消息，追加到已有对话上下文之后。
        full_context = await build_chat_context(
            db, redis, user, article, message
        )
        article_context = (
            full_context[1:-1] if len(full_context) > 2 else []
        )
        context_messages.extend(article_context)

    # ---- 3. 创建会话记录 ----
    session = await agent_repo.create_session(
        db,
        user_id=user.id,
        article_id=article_id,
        history_id=history_id,
        agent_type="reading_coach",
        user_message=message,
        conversation_id=conv_id,
    )

    # 更新对话的 updated_at，使侧边栏对话列表按最近活跃排序。
    await agent_repo.touch_conversation(db, conv_id)

    # ---- 4. 实例化并执行 Agent ----
    agent = ReadingCoachAgent(
        db, redis, user.id, article_id, history_id
    )

    final_answer_parts: list[str] = []
    steps_data: list[dict] = []
    step_order = 0
    status = "completed"
    done_sent = False

    try:
        async for step in agent.run(message, context_messages):
            # 将步骤转换为 SSE 帧并推送给前端。
            # done 帧额外包含 conversation_id，供前端记录当前对话。
            if step.step_type == "done":
                yield _sse_frame(
                    {"type": "done", "conversation_id": conv_id}
                )
                done_sent = True
            else:
                yield _step_to_sse(step)

            # 收集最终回答文本（content 步骤）。
            if step.step_type == "content" and step.content:
                final_answer_parts.append(step.content)

            # 收集需要持久化的步骤数据。
            # 仅持久化 thinking / tool_call / tool_result 三类步骤，
            # content / done / error 属于流式传输控制帧，不写入数据库。
            if step.step_type in ("thinking", "tool_call", "tool_result"):
                step_order += 1
                steps_data.append(
                    _step_to_record(step_order, step)
                )

    except Exception as e:
        logger.exception(
            "Agent execution failed for session=%s", session.id
        )
        status = "failed"
        yield _sse_frame(
            {"type": "error", "message": f"Agent 执行出错：{e}"}
        )

    # ---- 6. 持久化执行结果 ----
    final_answer = "".join(final_answer_parts) or None

    # 当 article_id 不为 None 时，保存对话消息和活动日志（这些表
    # 要求 article_id NOT NULL），并触发记忆摘要。
    # 当 article_id 为 None（独立智能学习页面）时，仅保存 Agent
    # 会话和步骤记录，跳过 ai_conversations / ai_activities 写入。
    if article_id is not None:
        await ai_repo.save_message(
            db, user.id, article_id, "user", message, history_id=history_id
        )
        if final_answer:
            await ai_repo.save_message(
                db,
                user.id,
                article_id,
                "assistant",
                final_answer,
                history_id=history_id,
            )

        await ai_repo.create_activity(
            db, user.id, article_id, history_id, "agent_chat", message
        )

    # 更新会话记录。
    await agent_repo.update_session(
        db,
        session_id=session.id,
        final_answer=final_answer,
        total_steps=len(steps_data),
        status=status,
    )

    # 批量创建步骤记录。
    await agent_repo.create_steps(db, session.id, steps_data)

    # 递增消息计数（用户 + 助手 = 2 条消息）。
    await mem_repo.increment_message_count(db, user.id, delta=2)

    # 触发记忆摘要（后台优化，不影响主流程）。
    if article_id is not None:
        await maybe_summarize(db, redis, user.id, article_id)

    # 如果 done 事件未发送（例如 Agent 执行出错），在此补发，
    # 确保前端始终能收到 done 事件并正确结束流式状态。
    if not done_sent:
        yield _sse_frame(
            {"type": "done", "conversation_id": conv_id}
        )


# ---- SSE 辅助函数 -----------------------------------------------------------


def _step_to_sse(step: AgentStep) -> str:
    """将 AgentStep 转换为 SSE 帧字符串。

    根据步骤类型构建不同的 JSON 载荷：

    - ``thinking``   — ``{"type": "thinking", "content": "..."}``
    - ``tool_call``  — ``{"type": "tool_call", "tool": "...", "arguments": {...}}``
    - ``tool_result``— ``{"type": "tool_result", "tool": "...", "content": "...", "data": {...}}``
    - ``content``    — ``{"type": "content", "content": "..."}`
    - ``done``       — ``{"type": "done"}``
    - ``error``      — ``{"type": "error", "message": "..."}``

    Args:
        step: Agent 执行步骤。

    Returns:
        ``data: {json_payload}\\n\\n`` 格式的 SSE 帧。
    """
    if step.step_type == "thinking":
        payload = {"type": "thinking", "content": step.content}
    elif step.step_type == "tool_call":
        payload = {
            "type": "tool_call",
            "tool": step.tool_name,
            "arguments": step.tool_arguments,
        }
    elif step.step_type == "tool_result":
        payload = {
            "type": "tool_result",
            "tool": step.tool_name,
            "content": step.content,
            "data": step.tool_result_data,
        }
    elif step.step_type == "content":
        payload = {"type": "content", "content": step.content}
    elif step.step_type == "done":
        payload = {"type": "done"}
    elif step.step_type == "error":
        payload = {
            "type": "error",
            "message": step.content,
        }
    else:
        payload = {"type": step.step_type, "content": step.content}

    return _sse_frame(payload)


def _sse_frame(payload: dict) -> str:
    """将字典序列化为 SSE 帧字符串。

    Args:
        payload: 要序列化的 JSON 载荷。

    Returns:
        ``data: {json_payload}\\n\\n`` 格式的 SSE 帧。
    """
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _step_to_record(step_order: int, step: AgentStep) -> dict:
    """将 AgentStep 转换为 AgentStepRecord 的数据字典。

    仅处理 ``thinking`` / ``tool_call`` / ``tool_result`` 三类步骤。

    Args:
        step_order: 步骤序号（从 1 开始）。
        step: Agent 执行步骤。

    Returns:
        包含 ``step_order``、``step_type``、``content``、``tool_name``、
        ``tool_arguments`` 和 ``tool_result`` 键的字典。
    """
    record: dict = {
        "step_order": step_order,
        "step_type": step.step_type,
        "content": None,
        "tool_name": None,
        "tool_arguments": None,
        "tool_result": None,
    }

    if step.step_type == "thinking":
        record["content"] = step.content
    elif step.step_type == "tool_call":
        record["tool_name"] = step.tool_name or None
        record["tool_arguments"] = step.tool_arguments or None
    elif step.step_type == "tool_result":
        record["content"] = step.content or None
        record["tool_name"] = step.tool_name or None
        record["tool_result"] = step.tool_result_data or None

    return record
