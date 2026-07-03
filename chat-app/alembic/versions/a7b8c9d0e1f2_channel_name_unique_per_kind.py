"""channel name unique per kind (allow same name for text and voice)

Revision ID: a7b8c9d0e1f2
Revises: f5a6b7c8d9e0
Create Date: 2026-07-03

El nombre del canal dejaba de ser único GLOBAL para pasar a ser único POR TIPO:
así puede coexistir #general (texto) y 🔊general (voz). Se quita el índice único
sobre `name` y se añade una restricción única compuesta (name, kind).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, Sequence[str], None] = "f5a6b7c8d9e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # batch_alter_table recrea la tabla en SQLite (no soporta ALTER de índices
    # únicos in situ). Quitamos el índice único de `name`, lo dejamos como índice
    # normal y añadimos la unicidad compuesta (name, kind).
    with op.batch_alter_table("channels", schema=None) as batch_op:
        batch_op.drop_index("ix_channels_name")
        batch_op.create_index("ix_channels_name", ["name"], unique=False)
        batch_op.create_unique_constraint("uq_channels_name_kind", ["name", "kind"])


def downgrade() -> None:
    with op.batch_alter_table("channels", schema=None) as batch_op:
        batch_op.drop_constraint("uq_channels_name_kind", type_="unique")
        batch_op.drop_index("ix_channels_name")
        batch_op.create_index("ix_channels_name", ["name"], unique=True)
