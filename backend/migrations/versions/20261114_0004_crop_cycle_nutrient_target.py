"""crop_cycles.nutrient_target (Phase 13 fertilizer planning)

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-14 23:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "crop_cycles", sa.Column("nutrient_target", postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("crop_cycles", "nutrient_target")
