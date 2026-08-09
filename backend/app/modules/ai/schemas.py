"""AI 模块的 Pydantic 模式（schema）。

描述了 AI 交互请求和对话历史的传输数据结构。
采用 Pydantic v2 风格，使用 ``model_config`` / ``ConfigDict``，并在
输出模式上启用 ``from_attributes``，以便直接从 ORM 实例构建。
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ---- AI 交互请求 ------------------------------------------------------------


class ExplainWordRequest(BaseModel):
    """请求在上下文中解释单个单词。"""

    word: str = Field(min_length=1, max_length=255)
    context: str
    article_id: int


class AnalyzeSentenceRequest(BaseModel):
    """请求分析单个句子的结构。"""

    sentence: str
    article_id: int


class SentenceTranslationRequest(BaseModel):
    """请求将句子翻译为中文。"""

    sentence: str
    article_id: int


class ParagraphSummaryRequest(BaseModel):
    """请求对单个段落进行摘要。"""

    paragraph: str
    article_id: int


class ChatRequest(BaseModel):
    """请求向文章感知的 AI 教练发送一条消息。"""

    message: str
    article_id: int


# ---- AI 对话模式 -----------------------------------------------------------


class ConversationOut(BaseModel):
    """返回给客户端的单条 AI 对话消息。

    每条消息要么是 ``"user"`` 消息（学习者的问题），要么是
    ``"assistant"`` 消息（AI 教练的回复）。
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    content: str
    created_at: datetime


class ConversationListResponse(BaseModel):
    """按时间顺序排列的 AI 对话消息列表。

    由对话历史端点返回，以便前端在页面刷新后恢复用户的聊天会话。
    """

    items: list[ConversationOut]
    total: int
