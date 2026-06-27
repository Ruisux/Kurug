"""message and dm image_url

Revision ID: a1b2c3d4e5f6
Revises: 2529f26ce839
Create Date: 2026-06-21 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '2529f26ce839'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('messages', schema=None) as batch_op:
        batch_op.add_column(sa.Column('image_url', sa.String(length=255), nullable=True))
    with op.batch_alter_table('direct_messages', schema=None) as batch_op:
        batch_op.add_column(sa.Column('image_url', sa.String(length=255), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('direct_messages', schema=None) as batch_op:
        batch_op.drop_column('image_url')
    with op.batch_alter_table('messages', schema=None) as batch_op:
        batch_op.drop_column('image_url')
