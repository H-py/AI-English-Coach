"""AI 模块的 Pydantic 模式（schema）。

描述了 AI 交互请求和对话历史的传输数据结构。
采用 Pydantic v2 风格，使用 ``model_config`` / ``ConfigDict``，并在
输出模式上启用 ``from_attributes``，以便直接从 ORM 实例构建。
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---- AI 交互请求 ------------------------------------------------------------


class ExplainWordRequest(BaseModel):
    """请求在上下文中解释单个单词。"""

    word: str = Field(min_length=1, max_length=255)
    context: str
    article_id: int
    history_id: Optional[int] = None


class AnalyzeSentenceRequest(BaseModel):
    """请求分析单个句子的结构。"""

    sentence: str
    article_id: int
    history_id: Optional[int] = None


class SentenceTranslationRequest(BaseModel):
    """请求将句子翻译为中文。"""

    sentence: str
    article_id: int
    history_id: Optional[int] = None


class ParagraphSummaryRequest(BaseModel):
    """请求对单个段落进行摘要。"""

    paragraph: str
    article_id: int
    history_id: Optional[int] = None


class ChatRequest(BaseModel):
    """请求向文章感知的 AI 教练发送一条消息。"""

    message: str
    article_id: int
    history_id: Optional[int] = None


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


# ---- 阅读总结 ---------------------------------------------------------------


class SummaryRequest(BaseModel):
    """请求生成某次阅读会话的总结。"""

    history_id: int


class ActivityStats(BaseModel):
    """阅读会话的活动统计数据，附带在总结中。"""

    word_count: int = 0
    sentence_count: int = 0
    chat_count: int = 0
    duration_seconds: Optional[int] = None


class ReadingSummaryOut(BaseModel):
    """返回给客户端的阅读总结。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    history_id: int
    article_id: int
    content: str
    activity_stats: dict[str, Any]
    created_at: datetime


# ---- 阅读练习题 -------------------------------------------------------------


class QuizRequest(BaseModel):
    """请求基于文章生成练习题。"""

    article_id: int
    history_id: int


class QuizQuestion(BaseModel):
    """单道练习题。"""

    id: int
    question: str
    options: list[str]
    correct_answer: str
    explanation: str


class QuizAnswerItem(BaseModel):
    """用户对单道题的作答。"""

    question_id: int
    user_answer: str


class QuizSubmitRequest(BaseModel):
    """提交练习题答案。"""

    answers: list[QuizAnswerItem]


class QuizAnswerResult(BaseModel):
    """单道题的判分结果。"""

    question_id: int
    user_answer: str
    correct_answer: str
    is_correct: bool
    explanation: str


class ReadingQuizOut(BaseModel):
    """返回给客户端的练习题。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    history_id: int
    article_id: int
    questions: list[dict[str, Any]]
    user_answers: Optional[list[dict[str, Any]]] = None
    score: Optional[int] = None
    total: int
    created_at: datetime


class QuizSubmitResponse(BaseModel):
    """提交练习题后的判分结果。"""

    quiz_id: int
    score: int
    total: int
    results: list[QuizAnswerResult]
