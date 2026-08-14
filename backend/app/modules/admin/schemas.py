"""admin 模块的 Pydantic schemas。

这些 schemas 描述了仅管理员可用端点在文章和用户管理时使用的传输数据结构。
它们继承或组合了 article 与 users 模块的基础 schemas，并添加了仅对管理员
有意义的字段（例如文章列表项中的 ``is_published``，或对用户更新 ``role``
与 ``is_active`` 的能力）。
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.modules.article.models import Difficulty
from app.modules.article.schemas import ArticleListItem
from app.modules.users.models import EnglishLevel, UserRole


# ---------------------------------------------------------------------------
# 文章 schemas
# ---------------------------------------------------------------------------

class AdminArticleListItem(ArticleListItem):
    """带管理员专属字段的文章列表项。

    在 :class:`ArticleListItem` 基础上扩展了 ``is_published``、``view_count``
    和 ``updated_at``，使管理员可一目了然地查看发布状态与互动指标。
    """

    is_published: bool
    view_count: int
    updated_at: datetime


class AdminArticleListResponse(BaseModel):
    """供管理员使用的全部文章（含未发布）分页列表。"""

    items: list[AdminArticleListItem]
    total: int
    page: int
    page_size: int


class AdminArticleQueryParams(BaseModel):
    """管理员文章列表的查询参数。

    支持不区分大小写的标题搜索、难度筛选、标签筛选、发布状态筛选以及分页。
    """

    search: Optional[str] = None
    difficulty: Optional[Difficulty] = None
    cet_type: Optional[str] = None
    tag: Optional[str] = None
    is_published: Optional[bool] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


# ---------------------------------------------------------------------------
# 用户 schemas
# ---------------------------------------------------------------------------

class AdminUserOut(BaseModel):
    """供管理员视图使用的完整用户表示。

    与 users 模块中的 :class:`UserOut` 对应，但在此处定义以保持 admin 模块
    自包含，并便于将来出现差异化时独立演进。
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    username: str
    avatar_url: Optional[str] = None
    english_level: EnglishLevel
    role: UserRole
    is_active: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None


class AdminUserListResponse(BaseModel):
    """供管理员使用的用户分页列表。"""

    items: list[AdminUserOut]
    total: int
    page: int
    page_size: int


class AdminUserUpdate(BaseModel):
    """管理员用户管理的部分更新载荷。

    允许更新用户名、角色、启用状态和英语等级。
    邮箱被刻意排除在外——修改邮箱需要走单独的验证流程。
    """

    username: Optional[str] = Field(default=None, min_length=2, max_length=50)
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    english_level: Optional[EnglishLevel] = None


class AdminUserQueryParams(BaseModel):
    """管理员用户列表的查询参数。"""

    search: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


# ---------------------------------------------------------------------------
# 仪表盘 / 概览 schemas
# ---------------------------------------------------------------------------

class AdminDashboard(BaseModel):
    """管理概览页面的高层统计数据。"""

    total_users: int
    total_articles: int
    published_articles: int
    total_views: int
