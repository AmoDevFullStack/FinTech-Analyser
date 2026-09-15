"""Recommendations. See specs/recommendations.md.

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-15
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

RECOMMENDATION_STATUS_ENUM = postgresql.ENUM(
    "active", "dismissed", "acted_on", name="recommendation_status_enum"
)


def upgrade() -> None:
    RECOMMENDATION_STATUS_ENUM.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "recommendations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("rule_id", sa.String(), nullable=False),
        sa.Column("status", RECOMMENDATION_STATUS_ENUM, nullable=False),
        sa.Column("benefit_amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("benefit_kind", sa.String(), nullable=False),
        sa.Column("explanation", sa.String(), nullable=False),
        sa.Column("computation_reference", sa.String(), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False),
        sa.Column("generated_on", sa.Date(), nullable=False),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_recommendations_user_id", "recommendations", ["user_id"])
    op.create_index("ix_recommendations_user_rule", "recommendations", ["user_id", "rule_id"])
    op.execute(
        "CREATE TRIGGER recommendations_set_updated_at BEFORE UPDATE ON recommendations "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS recommendations_set_updated_at ON recommendations")
    op.drop_index("ix_recommendations_user_rule", table_name="recommendations")
    op.drop_index("ix_recommendations_user_id", table_name="recommendations")
    op.drop_table("recommendations")
    RECOMMENDATION_STATUS_ENUM.drop(op.get_bind(), checkfirst=True)
