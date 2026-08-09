"""add reading summary, quiz tables and ai_activities

Revision ID: c7f3a2b8d901
Revises: ab5e711a1591
Create Date: 2026-08-09 18:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7f3a2b8d901'
down_revision: Union[str, None] = 'ab5e711a1591'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. ai_conversations 加 history_id 列
    op.add_column(
        'ai_conversations',
        sa.Column(
            'history_id',
            sa.BigInteger(),
            sa.ForeignKey('reading_histories.id'),
            nullable=True,
        ),
    )
    op.create_index(
        'ix_ai_conversations_history_id',
        'ai_conversations',
        ['history_id'],
    )

    # 2. 新增 ai_activities 表
    op.create_table(
        'ai_activities',
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
            nullable=False,
        ),
        sa.Column(
            'history_id',
            sa.BigInteger(),
            sa.ForeignKey('reading_histories.id'),
            nullable=True,
        ),
        sa.Column('activity_type', sa.String(length=30), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_ai_activities_user_id', 'ai_activities', ['user_id']
    )
    op.create_index(
        'ix_ai_activities_article_id', 'ai_activities', ['article_id']
    )
    op.create_index(
        'ix_ai_activities_history_id', 'ai_activities', ['history_id']
    )

    # 3. 新增 reading_summaries 表
    op.create_table(
        'reading_summaries',
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
            nullable=False,
        ),
        sa.Column(
            'history_id',
            sa.BigInteger(),
            sa.ForeignKey('reading_histories.id'),
            nullable=False,
        ),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column(
            'activity_stats',
            sa.JSON(),
            server_default='{}',
            nullable=False,
        ),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'history_id', name='uq_reading_summaries_history'
        ),
    )
    op.create_index(
        'ix_reading_summaries_user_id', 'reading_summaries', ['user_id']
    )

    # 4. 新增 reading_quizzes 表
    op.create_table(
        'reading_quizzes',
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
            nullable=False,
        ),
        sa.Column(
            'history_id',
            sa.BigInteger(),
            sa.ForeignKey('reading_histories.id'),
            nullable=False,
        ),
        sa.Column(
            'questions', sa.JSON(), server_default='[]', nullable=False
        ),
        sa.Column('user_answers', sa.JSON(), nullable=True),
        sa.Column('score', sa.Integer(), nullable=True),
        sa.Column(
            'total', sa.Integer(), server_default='0', nullable=False
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
        'ix_reading_quizzes_user_id', 'reading_quizzes', ['user_id']
    )


def downgrade() -> None:
    op.drop_table('reading_quizzes')
    op.drop_table('reading_summaries')
    op.drop_table('ai_activities')
    op.drop_index(
        'ix_ai_conversations_history_id', table_name='ai_conversations'
    )
    op.drop_column('ai_conversations', 'history_id')
