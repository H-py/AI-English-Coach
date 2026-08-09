"""用于创建或升级初始管理员账户的独立脚本。

用法::

    cd backend
    python -m app.scripts.init_admin

管理员凭据从应用配置（``ADMIN_EMAIL``、``ADMIN_USERNAME``、
``ADMIN_PASSWORD``）读取，而这些配置又从环境变量或 ``.env`` 文件中
加载。

行为：
    * 若不存在使用配置管理员邮箱的用户，则创建一个新的管理员用户。
    * 若已存在使用该邮箱的用户但不是管理员，则将其角色升级为
      ``admin``。
    * 若管理员用户已存在且角色正确，则不做任何更改。
"""

import asyncio

from sqlalchemy import select

from app.core.config import settings
from app.core.database import async_session_factory
from app.core.logging import configure_logging, get_logger
from app.core.security import hash_password
from app.modules.users.models import User, UserRole

logger = get_logger(__name__)


async def init_admin() -> None:
    """创建或升级初始管理员用户。"""
    configure_logging()

    async with async_session_factory() as session:
        result = await session.execute(
            select(User).where(User.email == settings.ADMIN_EMAIL)
        )
        user = result.scalars().first()

        if user is None:
            # 创建新的管理员用户。
            user = User(
                email=settings.ADMIN_EMAIL,
                username=settings.ADMIN_USERNAME,
                password_hash=hash_password(settings.ADMIN_PASSWORD),
                role=UserRole.admin,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            logger.info(
                "Admin user created: id=%s email=%s username=%s",
                user.id,
                user.email,
                user.username,
            )
        elif user.role != UserRole.admin:
            # 将已存在的用户升级为管理员。
            user.role = UserRole.admin
            await session.commit()
            await session.refresh(user)
            logger.info(
                "Existing user upgraded to admin: id=%s email=%s",
                user.id,
                user.email,
            )
        else:
            logger.info(
                "Admin user already exists: id=%s email=%s",
                user.id,
                user.email,
            )

    print(
        f"\nAdmin account ready:\n"
        f"  Email:    {settings.ADMIN_EMAIL}\n"
        f"  Username: {settings.ADMIN_USERNAME}\n"
        f"  Role:     admin\n"
    )


if __name__ == "__main__":
    asyncio.run(init_admin())
