"""ai_recommendations.rule and .factors (Phase 11 explainability)

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-14 21:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("ai_recommendations", sa.Column("rule", sa.Text(), nullable=True))
    op.add_column("ai_recommendations", sa.Column("factors", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.create_index(
        op.f("ix_ai_recommendations_farm_id_zone_id_rule_status"),
        "ai_recommendations",
        ["farm_id", "zone_id", "rule", "status"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_ai_recommendations_farm_id_zone_id_rule_status"), table_name="ai_recommendations")
    op.drop_column("ai_recommendations", "factors")
    op.drop_column("ai_recommendations", "rule")
