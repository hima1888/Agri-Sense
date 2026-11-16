"""crop_cycles.yield_reference (Phase 14 yield estimate)

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-15 09:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "crop_cycles", sa.Column("yield_reference", postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("crop_cycles", "yield_reference")
