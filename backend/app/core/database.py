"""异步数据库基础设施。

提供 SQLAlchemy 异步引擎、会话工厂、所有 ORM 模型使用的声明式
``Base`` 基类，以及用于产出 :class:`AsyncSession` 的 ``get_db`` FastAPI 依赖。
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

# 异步引擎，连接池针对异步使用场景进行了调优。
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.APP_DEBUG,
    pool_pre_ping=True,
    future=True,
)

# 绑定到异步引擎的会话工厂。
async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """所有 ORM 模型的声明式基类。

    每个功能模块都导入 :class:`Base` 来声明其数据表，以便 Alembic
    能够通过元数据反射发现它们。
    """

    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """提供事务性异步会话的 FastAPI 依赖。

    请求结束时该会话会自动关闭。如果发生异常，事务将被回滚。
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
