"""channel kind (text/voice) and position

Revision ID: f5a6b7c8d9e0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-02

Añade a `channels`:
- `kind`: "text" o "voice" (por defecto "text"; los existentes quedan en texto).
- `position`: orden en la lista (menor = más arriba). Se rellena por orden de
  nombre para conservar el orden actual.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f5a6b7c8d9e0"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "channels",
        sa.Column("kind", sa.String(length=8), server_default="text", nullable=False),
    )
    op.add_column(
        "channels",
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
    )
    # Backfill de position por orden de nombre, para conservar el orden actual.
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id FROM channels ORDER BY name")).fetchall()
    for i, (cid,) in enumerate(rows):
        conn.execute(
            sa.text("UPDATE channels SET position = :p WHERE id = :id"),
            {"p": i, "id": cid},
        )


def downgrade() -> None:
    op.drop_column("channels", "position")
    op.drop_column("channels", "kind")
