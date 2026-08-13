"""add user_llm_configs table

Revision ID: f7b2c3d9e100
Revises: e4a9b1c7f302
Create Date: 2026-08-13 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7b2c3d9e100'
down_revision: Union[str, None] = 'e4a9b1c7f302'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. 新增 user_llm_configs 表（每个用户可有多条，至多一条激活）
    op.create_table(
        'user_llm_configs',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            'user_id',
            sa.BigInteger(),
            sa.ForeignKey('users.id'),
            nullable=False,
        ),
        sa.Column('provider_name', sa.String(length=100), nullable=False, server_default=''),
        sa.Column('base_url', sa.String(length=512), nullable=False),
        sa.Column('model', sa.String(length=100), nullable=False),
        sa.Column('api_key', sa.String(length=512), nullable=False, server_default=''),
        sa.Column(
            'is_active',
            sa.Boolean(),
            server_default='false',
            nullable=False,
        ),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_user_llm_configs_user_id', 'user_llm_configs', ['user_id']
    )
    # 每用户至多一条激活配置
    op.create_index(
        'uq_user_llm_configs_one_active',
        'user_llm_configs',
        ['user_id'],
        unique=True,
        postgresql_where=sa.text('is_active'),
    )

    # 2. updated_at 触发器（与 init.sql 中的 update_updated_at() 对齐，
    #    保证两种初始化路径行为一致）
    op.execute(
        """
        CREATE OR REPLACE FUNCTION update_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_user_llm_configs_updated_at
        BEFORE UPDATE ON user_llm_configs
        FOR EACH ROW
        EXECUTE FUNCTION update_updated_at();
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_user_llm_configs_updated_at ON user_llm_configs"
    )
    op.drop_index('uq_user_llm_configs_one_active', table_name='user_llm_configs')
    op.drop_index('ix_user_llm_configs_user_id', table_name='user_llm_configs')
    op.drop_table('user_llm_configs')
