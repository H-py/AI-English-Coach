"""users 模块的数据库访问层。

所有函数均为异步函数，并操作共享的 :class:`AsyncSession`。
它们负责持久化机制（``add`` / ``flush`` / ``refresh``），
而事务的提交/回滚则交由 ``get_db`` 依赖完成，该依赖会将每个请求
包裹在单个事务中。
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.models import User, UserRole


async def get_user_by_id(db: AsyncSession, user_id: int) -> Optional[User]:
    """按主键获取单个用户。

    Args:
        db: 当前活跃的异步会话。
        user_id: 用户的主键。

    Returns:
        :class:`User` 实例，若无匹配用户则返回 ``None``。
    """
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalars().first()


async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    """按邮箱地址获取单个用户。

    Args:
        db: 当前活跃的异步会话。
        email: 要查询的精确邮箱。

    Returns:
        :class:`User` 实例，若无匹配用户则返回 ``None``。
    """
    result = await db.execute(select(User).where(User.email == email))
    return result.scalars().first()


async def get_user_by_username(db: AsyncSession, username: str) -> Optional[User]:
    """按用户名获取单个用户。

    Args:
        db: 当前活跃的异步会话。
        username: 要查询的精确用户名。

    Returns:
        :class:`User` 实例，若无匹配用户则返回 ``None``。
    """
    result = await db.execute(select(User).where(User.username == username))
    return result.scalars().first()


async def create_user(
    db: AsyncSession,
    email: str,
    username: str,
    password_hash: str,
    role: UserRole = UserRole.user,
) -> User:
    """创建并持久化一个新用户。

    用户会被 flush（而非 commit），以便 ``id`` 和 ``created_at`` 等
    服务端默认值填充并可在返回的实例上访问，同时外层请求事务仍保留
    提交控制权。

    Args:
        db: 当前活跃的异步会话。
        email: 用户的邮箱地址。
        username: 用户的显示名。
        password_hash: 已哈希的密码（绝不传入明文）。
        role: 用户的角色（默认为 ``user``）。

    Returns:
        新创建的、已刷新属性的 :class:`User`。
    """
    user = User(
        email=email,
        username=username,
        password_hash=password_hash,
        role=role,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


async def update_user(db: AsyncSession, user: User, data: dict) -> User:
    """对已有用户应用一组字段更新。

    只写入 ``data`` 中存在的键。更改会被 flush，以便 ``onupdate``
    默认值（如 ``updated_at``）生效，并在返回前刷新实例。

    Args:
        db: 当前活跃的异步会话。
        user: 待更新的 :class:`User` 实例。
        data: 属性名到新值的映射。

    Returns:
        更新后并刷新属性的 :class:`User`。
    """
    for key, value in data.items():
        setattr(user, key, value)
    await db.flush()
    await db.refresh(user)
    return user


async def update_last_login(db: AsyncSession, user: User) -> User:
    """将用户的 ``last_login_at`` 标记为当前 UTC 时间。

    Args:
        db: 当前活跃的异步会话。
        user: 刚完成认证的 :class:`User` 实例。

    Returns:
        更新后并刷新属性的 :class:`User`。
    """
    user.last_login_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(user)
    return user


async def list_users(
    db: AsyncSession,
    search: Optional[str] = None,
    role: Optional[UserRole] = None,
    is_active: Optional[bool] = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[User], int]:
    """列出用户，支持可选的过滤、搜索和分页。

    Args:
        db: 当前活跃的异步会话。
        search: 可选，不区分大小写的子串，用于匹配邮箱或用户名。
        role: 可选，按角色过滤。
        is_active: 可选，按激活状态过滤。
        page: 从 1 开始的页码。
        page_size: 每页条数。

    Returns:
        ``(items, total)`` 元组。
    """
    conditions = []

    if search is not None and search.strip():
        conditions.append(
            or_(
                User.email.ilike(f"%{search}%"),
                User.username.ilike(f"%{search}%"),
            )
        )

    if role is not None:
        conditions.append(User.role == role)

    if is_active is not None:
        conditions.append(User.is_active.is_(is_active))

    count_stmt = select(func.count()).select_from(User).where(*conditions)
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    offset = (page - 1) * page_size
    data_stmt = (
        select(User)
        .where(*conditions)
        .order_by(User.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    data_result = await db.execute(data_stmt)
    items = list(data_result.scalars().all())

    return items, total


async def delete_user(db: AsyncSession, user: User) -> None:
    """从数据库中删除一个用户。

    Args:
        db: 当前活跃的异步会话。
        user: 待删除的 :class:`User` 实例。
    """
    await db.delete(user)
    await db.flush()
