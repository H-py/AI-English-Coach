"""llm_config 模块的数据库访问层。

所有函数均为异步函数，并操作共享的 :class:`AsyncSession`。它们负责
持久化机制（``add`` / ``flush`` / ``refresh``），而事务的提交/回滚
交由 ``get_db`` 依赖完成。每个用户可有多条配置，其中至多一条
``is_active`` 为 true。
"""

from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.llm_config.models import UserLlmConfig


async def list_configs(
    db: AsyncSession, user_id: int
) -> list[UserLlmConfig]:
    """列出用户的全部模型配置（最新的在前）。"""
    result = await db.execute(
        select(UserLlmConfig)
        .where(UserLlmConfig.user_id == user_id)
        .order_by(UserLlmConfig.id.desc())
    )
    return list(result.scalars().all())


async def get_config(
    db: AsyncSession, config_id: int, user_id: int
) -> Optional[UserLlmConfig]:
    """按 id + user_id 获取单条配置，不属于该用户时返回 ``None``。"""
    result = await db.execute(
        select(UserLlmConfig).where(
            UserLlmConfig.id == config_id,
            UserLlmConfig.user_id == user_id,
        )
    )
    return result.scalars().first()


async def get_active_config(
    db: AsyncSession, user_id: int
) -> Optional[UserLlmConfig]:
    """获取用户当前激活（使用中）的配置；没有则返回 ``None``。"""
    result = await db.execute(
        select(UserLlmConfig).where(
            UserLlmConfig.user_id == user_id,
            UserLlmConfig.is_active.is_(True),
        )
    )
    return result.scalars().first()


async def count_configs(db: AsyncSession, user_id: int) -> int:
    """统计用户的配置数量（用于首个配置自动激活的判断）。"""
    result = await db.execute(
        select(UserLlmConfig.id).where(UserLlmConfig.user_id == user_id)
    )
    return len(result.scalars().all())


async def create_config(
    db: AsyncSession, user_id: int, data: dict, is_active: bool
) -> UserLlmConfig:
    """创建一条新的模型配置。"""
    config = UserLlmConfig(user_id=user_id, is_active=is_active, **data)
    db.add(config)
    await db.flush()
    await db.refresh(config)
    return config


async def update_config(
    db: AsyncSession, config: UserLlmConfig, data: dict
) -> UserLlmConfig:
    """更新指定配置的字段；未提供的字段保持不变。"""
    for key, value in data.items():
        setattr(config, key, value)
    await db.flush()
    await db.refresh(config)
    return config


async def delete_config(db: AsyncSession, config: UserLlmConfig) -> None:
    """删除一条配置。"""
    await db.delete(config)
    await db.flush()


async def deactivate_all(db: AsyncSession, user_id: int) -> None:
    """将该用户所有配置标记为非激活（回到默认模型）。"""
    await db.execute(
        update(UserLlmConfig)
        .where(
            UserLlmConfig.user_id == user_id,
            UserLlmConfig.is_active.is_(True),
        )
        .values(is_active=False)
    )
    await db.flush()


async def activate_config(
    db: AsyncSession, config_id: int, user_id: int
) -> Optional[UserLlmConfig]:
    """把指定配置设为激活（先清除其余激活标记）。

    Returns:
        激活后的配置；配置不存在或不属于该用户时返回 ``None``。
    """
    config = await get_config(db, config_id, user_id)
    if config is None:
        return None
    await deactivate_all(db, user_id)
    config.is_active = True
    await db.flush()
    await db.refresh(config)
    return config
