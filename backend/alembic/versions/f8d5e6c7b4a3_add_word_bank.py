"""add word_bank and word_bank_levels tables

Revision ID: f8d5e6c7b4a3
Revises: f7b2c3d9e100
Create Date: 2026-08-15 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f8d5e6c7b4a3'
down_revision: Union[str, None] = 'f7b2c3d9e100'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 词库单词表（小写原形 + 音标 + 中文释义）
    op.create_table(
        'word_bank',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('word', sa.String(length=255), nullable=False),
        sa.Column('phonetic', sa.String(length=255), nullable=True),
        sa.Column('meaning', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_word_bank_word', 'word_bank', ['word'], unique=True
    )

    # 单词等级归属（多对多，一词可属多个等级）
    op.create_table(
        'word_bank_levels',
        sa.Column('word_id', sa.BigInteger(), nullable=False),
        sa.Column('level', sa.String(length=20), nullable=False),
        sa.ForeignKeyConstraint(
            ['word_id'], ['word_bank.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('word_id', 'level'),
    )
    op.create_index(
        'ix_word_bank_levels_level', 'word_bank_levels', ['level']
    )


def downgrade() -> None:
    op.drop_index('ix_word_bank_levels_level', table_name='word_bank_levels')
    op.drop_table('word_bank_levels')
    op.drop_index('ix_word_bank_word', table_name='word_bank')
    op.drop_table('word_bank')
