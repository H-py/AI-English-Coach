"""add agent sessions and steps tables

Revision ID: e4a9b1c7f302
Revises: c7f3a2b8d901
Create Date: 2026-08-10 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e4a9b1c7f302'
down_revision: Union[str, None] = 'c7f3a2b8d901'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. 新增 agent_sessions 表
    op.create_table(
        'agent_sessions',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            'user_id',
            sa.BigInteger(),
            sa.ForeignKey('users.id'),
            nullable=False,
        ),
        sa.Column(
            'article_id',
            sa.BigInteger(),
            sa.ForeignKey('articles.id'),
            nullable=True,
        ),
        sa.Column(
            'history_id',
            sa.BigInteger(),
            sa.ForeignKey('reading_histories.id'),
            nullable=True,
        ),
        sa.Column('agent_type', sa.String(length=50), nullable=False),
        sa.Column('user_message', sa.Text(), nullable=False),
        sa.Column('final_answer', sa.Text(), nullable=True),
        sa.Column(
            'total_steps',
            sa.Integer(),
            server_default='0',
            nullable=False,
        ),
        sa.Column(
            'status',
            sa.String(length=20),
            server_default='completed',
            nullable=False,
        ),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_agent_sessions_user_id', 'agent_sessions', ['user_id']
    )

    # 2. 新增 agent_steps 表
    op.create_table(
        'agent_steps',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            'session_id',
            sa.BigInteger(),
            sa.ForeignKey('agent_sessions.id'),
            nullable=False,
        ),
        sa.Column('step_order', sa.Integer(), nullable=False),
        sa.Column('step_type', sa.String(length=20), nullable=False),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('tool_name', sa.String(length=100), nullable=True),
        sa.Column('tool_arguments', sa.JSON(), nullable=True),
        sa.Column('tool_result', sa.JSON(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_agent_steps_session_id', 'agent_steps', ['session_id']
    )


def downgrade() -> None:
    op.drop_table('agent_steps')
    op.drop_table('agent_sessions')
