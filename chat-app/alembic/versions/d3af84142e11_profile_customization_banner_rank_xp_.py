"""profile customization: banner, rank, xp, badges

Revision ID: d3af84142e11
Revises: a7b8c9d0e1f2
Create Date: 2026-07-24 01:02:04.864865

Solo añade las 5 columnas nuevas de `users`. Los cambios de image_url/FK que
el autogenerate detectó son "drift" preexistente del esquema (columnas que ya
existen y funcionan) y NO se tocan aquí a propósito, para no arriesgar datos.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd3af84142e11'
down_revision: Union[str, Sequence[str], None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: personalización de perfil en users."""
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('banner_url', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('rank', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('xp', sa.Integer(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('xp_updated_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('badges', sa.Text(), server_default='[]', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('badges')
        batch_op.drop_column('xp_updated_at')
        batch_op.drop_column('xp')
        batch_op.drop_column('rank')
        batch_op.drop_column('banner_url')
