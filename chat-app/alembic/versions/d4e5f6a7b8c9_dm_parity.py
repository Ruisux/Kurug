"""paridad de DMs: edición, fijado y reacciones

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-26 13:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('direct_messages', schema=None) as batch_op:
        batch_op.add_column(sa.Column('edited_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('pinned_at', sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        'dm_reactions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('dm_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('emoji', sa.String(length=16), nullable=False),
        sa.ForeignKeyConstraint(['dm_id'], ['direct_messages.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('dm_id', 'user_id', 'emoji', name='uq_dm_reaction'),
    )
    op.create_index('ix_dm_reactions_dm_id', 'dm_reactions', ['dm_id'])


def downgrade() -> None:
    op.drop_index('ix_dm_reactions_dm_id', table_name='dm_reactions')
    op.drop_table('dm_reactions')
    with op.batch_alter_table('direct_messages', schema=None) as batch_op:
        batch_op.drop_column('pinned_at')
        batch_op.drop_column('edited_at')
