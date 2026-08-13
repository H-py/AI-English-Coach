"""article 模块的 Pydantic schemas。

这些 schemas 描述了文章相关端点使用的传输数据结构：共享的基础字段、
创建/更新载荷、完整读取表示（``ArticleOut``）、轻量列表项
（``ArticleListItem``）、分页列表响应以及查询参数模型。它们采用
Pydantic v2 风格，使用 ``model_config`` / ``ConfigDict``。
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.modules.article.models import Difficulty


class ArticleBase(BaseModel):
    """请求与响应 schemas 共用的文章字段。"""

    title: str = Field(min_length=1, max_length=500)
    content: str
    difficulty: Difficulty = Difficulty.b1
    source: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    cover_url: Optional[str] = None


class ArticleCreate(ArticleBase):
    """创建新文章的载荷。

    在 :class:`ArticleBase` 基础上扩展了客户端可提供的可选字段。
    刻意未包含 ``word_count`` —— 该值由服务层根据 ``content`` 自动计算。
    """

    summary: Optional[str] = None
    reading_time: Optional[int] = None
    is_published: bool = True


class ArticleUpdate(BaseModel):
    """对已有文章进行部分更新的载荷。

    所有字段均为可选，客户端可只提交需要修改的字段。服务层使用
    ``exclude_unset`` 仅应用已提供的值。若 ``content`` 被更新，
    ``word_count`` 会自动重新计算。
    """

    title: Optional[str] = Field(default=None, min_length=1, max_length=500)
    content: Optional[str] = None
    summary: Optional[str] = None
    source: Optional[str] = None
    difficulty: Optional[Difficulty] = None
    reading_time: Optional[int] = None
    cover_url: Optional[str] = None
    tags: Optional[list[str]] = None
    is_published: Optional[bool] = None


class ArticleOut(BaseModel):
    """返回给客户端的完整文章表示。

    包含所有持久化字段。启用了 ``from_attributes``，因此可通过
    :meth:`ArticleOut.model_validate` 直接从 ORM ``Article`` 实例构建。
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    content: str
    summary: Optional[str] = None
    source: Optional[str] = None
    difficulty: Difficulty
    word_count: int
    reading_time: Optional[int] = None
    cover_url: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    is_published: bool
    view_count: int
    created_at: datetime
    updated_at: datetime


class ArticleListItem(BaseModel):
    """用于列表视图的轻量文章表示。

    不包含完整的 ``content`` 正文，以保持列表响应体较小。改用
    ``summary`` 字段提供简要概览。
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    summary: Optional[str] = None
    difficulty: Difficulty
    word_count: int
    reading_time: Optional[int] = None
    cover_url: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    created_at: datetime


class ArticleListResponse(BaseModel):
    """带总数与分页元数据的文章分页列表。"""

    items: list[ArticleListItem]
    total: int
    page: int
    page_size: int


class ArticleNeighborRef(BaseModel):
    """相邻文章的轻量引用（id + 标题）。"""

    id: int
    title: str


class ArticleNeighborsOut(BaseModel):
    """当前文章的上一篇 / 下一篇（按列表顺序循环）。

    顺序与列表接口一致（``created_at`` 倒序）。循环规则：
    第一篇的上一篇是最后一篇，最后一篇的下一篇是第一篇。
    只有一篇文章时，前后都是它自身。
    """

    prev: Optional[ArticleNeighborRef] = None
    next: Optional[ArticleNeighborRef] = None


class ArticleQueryParams(BaseModel):
    """用于筛选和分页文章列表的查询参数。

    作为列表端点所接受的查询字符串参数的结构化表示。路由会从各个
    ``Query`` 参数构造该模型，并将其传递给服务层。
    """

    difficulty: Optional[Difficulty] = None
    tag: Optional[str] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
