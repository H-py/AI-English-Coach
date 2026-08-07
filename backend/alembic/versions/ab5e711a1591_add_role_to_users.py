"""add role to users

Revision ID: ab5e711a1591
Revises:
Create Date: 2026-08-07 09:35:18.367390

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ab5e711a1591'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create the PostgreSQL enum type before adding the column.
    userrole_enum = sa.Enum('user', 'admin', name='userrole')
    userrole_enum.create(op.get_bind(), checkfirst=True)

    op.add_column(
        'users',
        sa.Column(
            'role',
            userrole_enum,
            server_default='user',
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column('users', 'role')
    sa.Enum(name='userrole').drop(op.get_bind(), checkfirst=True)
