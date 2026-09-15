"""Risk flags. See specs/risk-detection.md and docs/database.md §5.

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-15
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

RISK_STATUS_ENUM = postgresql.ENUM(
    "active", "acknowledged", "dismissed", "resolved", name="risk_status_enum", create_type=False
)


def upgrade() -> None:
    RISK_STATUS_ENUM.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "risk_flags",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("risk_type", sa.String(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("status", RISK_STATUS_ENUM, nullable=False),
        sa.Column("detected_on", sa.Date(), nullable=False),
        sa.Column("projected_date", sa.Date(), nullable=True),
        sa.Column("quantified_amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("explanation", sa.String(), nullable=False),
        # NOT NULL is the schema-level enforcement of specs/risk-detection.md's rule that
        # a flag without a computation reference must not exist.
        sa.Column("computation_reference", sa.String(), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_risk_flags_user_id", "risk_flags", ["user_id"])
    op.create_index("ix_risk_flags_user_type", "risk_flags", ["user_id", "risk_type"])
    op.execute(
        "CREATE TRIGGER risk_flags_set_updated_at BEFORE UPDATE ON risk_flags "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS risk_flags_set_updated_at ON risk_flags")
    op.drop_index("ix_risk_flags_user_type", table_name="risk_flags")
    op.drop_index("ix_risk_flags_user_id", table_name="risk_flags")
    op.drop_table("risk_flags")
    RISK_STATUS_ENUM.drop(op.get_bind(), checkfirst=True)
