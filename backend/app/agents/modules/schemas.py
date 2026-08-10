"""Agent 模块的 Pydantic 模式（schema）。

描述了 Agent 交互请求和会话记录的传输数据结构。
采用 Pydantic v2 风格，使用 ``model_config``，并在输出模式上启用
``from_attributes``，以便直接从 ORM 实例构建。
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---- Agent 交互请求 ---------------------------------------------------------


class AgentChatRequest(BaseModel):
    """请求向阅读教练 Agent 发送一条消息。

    ``article_id`` 可选地指明对话所围绕的文章——在独立"智能学习"
    页面中不绑定具体文章时为 ``None``。``history_id`` 可选地将
    本次交互关联到具体的阅读会话。
    """

    message: str = Field(min_length=1, max_length=2000)
    article_id: Optional[int] = None
    history_id: Optional[int] = None
    conversation_id: Optional[int] = None


# ---- Agent 会话输出 ---------------------------------------------------------


class AgentSessionOut(BaseModel):
    """返回给客户端的 Agent 会话记录。

    包含会话的基本信息和执行结果，供前端展示历史会话列表。
    """

    model_config = {"from_attributes": True}

    id: int
    agent_type: str
    user_message: str
    final_answer: Optional[str] = None
    total_steps: int
    status: str
    created_at: datetime


class AgentStepOut(BaseModel):
    """返回给客户端的 Agent 执行步骤记录。

    供前端在回看历史会话时展示思考流程。
    """

    model_config = {"from_attributes": True}

    id: int
    step_order: int
    step_type: str
    content: Optional[str] = None
    tool_name: Optional[str] = None
    tool_arguments: Optional[dict[str, Any]] = None
    tool_result: Optional[dict[str, Any]] = None
    created_at: datetime


class AgentSessionDetailOut(AgentSessionOut):
    """返回给客户端的 Agent 会话详情（含执行步骤）。

    供前端点击历史记录后加载完整会话内容。
    """

    steps: list[AgentStepOut] = []


# ---- Agent 对话输出 ---------------------------------------------------------


class AgentConversationOut(BaseModel):
    """返回给客户端的 Agent 对话记录。

    包含对话的基本信息，供前端展示对话列表。
    """

    model_config = {"from_attributes": True}

    id: int
    title: str
    created_at: datetime
    updated_at: datetime


class AgentConversationDetailOut(AgentConversationOut):
    """返回给客户端的 Agent 对话详情（含所有会话和步骤）。

    供前端点击对话后加载完整的多轮对话内容。
    """

    sessions: list[AgentSessionDetailOut] = []
