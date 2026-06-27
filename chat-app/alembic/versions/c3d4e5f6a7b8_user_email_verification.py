"""email y verificación de cuenta

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-26 12:30:00.000000

Añade email, email_verified y el código de verificación a users. Las cuentas
ya existentes se marcan como verificadas para no dejarlas fuera.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('email', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('email_verified', sa.Boolean(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('verification_code', sa.String(length=8), nullable=True))
        batch_op.add_column(sa.Column('verification_expires', sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index('ix_users_email', ['email'], unique=True)
    # Cuentas existentes: darlas por verificadas (no tienen email todavía).
    op.execute("UPDATE users SET email_verified = 1")


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index('ix_users_email')
        batch_op.drop_column('verification_expires')
        batch_op.drop_column('verification_code')
        batch_op.drop_column('email_verified')
        batch_op.drop_column('email')
