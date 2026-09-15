"""Forecast accuracy measurements. See specs/forecasting.md.

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-15
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "forecast_accuracy",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("forecast_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("month", sa.String(), nullable=False),
        sa.Column("metric", sa.String(), nullable=False),
        sa.Column("projected", sa.Numeric(15, 2), nullable=False),
        sa.Column("actual", sa.Numeric(15, 2), nullable=False),
        sa.Column("absolute_error", sa.Numeric(15, 2), nullable=False),
        sa.Column("signed_error", sa.Numeric(15, 2), nullable=False),
        sa.Column("percentage_error", sa.Numeric(9, 6), nullable=True),
        sa.Column("engine_version", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("user_id", "month", "metric", name="uq_forecast_accuracy_month_metric"),
    )
    op.create_index("ix_forecast_accuracy_user_id", "forecast_accuracy", ["user_id"])
    op.execute(
        "CREATE TRIGGER forecast_accuracy_set_updated_at BEFORE UPDATE ON forecast_accuracy "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS forecast_accuracy_set_updated_at ON forecast_accuracy")
    op.drop_index("ix_forecast_accuracy_user_id", table_name="forecast_accuracy")
    op.drop_table("forecast_accuracy")
