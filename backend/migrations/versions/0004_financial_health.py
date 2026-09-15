"""Financial health assessments. See specs/financial-health.md and docs/database.md §5.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-14
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "health_assessments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("weights_version", sa.String(), nullable=False),
        sa.Column("breakdown", postgresql.JSONB(), nullable=False),
    )
    op.create_index("ix_health_assessments_user_id", "health_assessments", ["user_id"])


def downgrade() -> None:
    op.drop_table("health_assessments")
