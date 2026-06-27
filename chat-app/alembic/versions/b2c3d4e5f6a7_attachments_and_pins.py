"""archivos adjuntos genéricos y mensajes fijados

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-25 19:30:00.000000

Añade adjuntos de archivo (file_url/file_name/file_size) a mensajes de canal y
DMs, y el campo pinned_at para fijar mensajes en canales de texto.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('messages', schema=None) as batch_op:
        batch_op.add_column(sa.Column('file_url', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('file_name', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('file_size', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('pinned_at', sa.DateTime(timezone=True), nullable=True))
    with op.batch_alter_table('direct_messages', schema=None) as batch_op:
        batch_op.add_column(sa.Column('file_url', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('file_name', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('file_size', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('direct_messages', schema=None) as batch_op:
        batch_op.drop_column('file_size')
        batch_op.drop_column('file_name')
        batch_op.drop_column('file_url')
    with op.batch_alter_table('messages', schema=None) as batch_op:
        batch_op.drop_column('pinned_at')
        batch_op.drop_column('file_size')
        batch_op.drop_column('file_name')
        batch_op.drop_column('file_url')
