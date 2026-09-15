"""Proof of thesis: position snapshots, scenarios, forecasts, audit log.

No foreign key runs from any real financial table to a scenario table — ADR-005.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-14
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # create_type=False — see the comment in 0001_foundation.py's upgrade().
    scenario_type_enum = postgresql.ENUM(
        "vehicle_purchase",
        "property_purchase",
        "income_change",
        "new_loan",
        "debt_repayment_change",
        "savings_change",
        "discretionary_expense",
        name="scenario_type_enum",
        create_type=False,
    )
    scenario_status_enum = postgresql.ENUM(
        "draft", "run", name="scenario_status_enum", create_type=False
    )
    actor_enum = postgresql.ENUM("user", "system", name="actor_enum", create_type=False)
    bind = op.get_bind()
    scenario_type_enum.create(bind, checkfirst=True)
    scenario_status_enum.create(bind, checkfirst=True)
    actor_enum.create(bind, checkfirst=True)

    op.create_table(
        "position_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("net_worth", sa.Numeric(15, 2), nullable=False),
        sa.Column("monthly_income", sa.Numeric(15, 2), nullable=False),
        sa.Column("monthly_essential", sa.Numeric(15, 2), nullable=False),
        sa.Column("monthly_discretionary", sa.Numeric(15, 2), nullable=False),
        sa.Column("total_debt", sa.Numeric(15, 2), nullable=False),
        sa.Column("liquid_savings", sa.Numeric(15, 2), nullable=False),
        sa.Column("position", postgresql.JSONB(), nullable=False),
    )
    op.create_index("ix_position_snapshots_user_id", "position_snapshots", ["user_id"])

    op.create_table(
        "scenarios",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("scenario_type", scenario_type_enum, nullable=False),
        sa.Column(
            "snapshot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("position_snapshots.id"),
            nullable=False,
        ),
        sa.Column("status", scenario_status_enum, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_scenarios_user_id", "scenarios", ["user_id"])
    op.execute(
        "CREATE TRIGGER scenarios_set_updated_at BEFORE UPDATE ON scenarios "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )

    op.create_table(
        "scenario_assumptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("scenario_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("scenarios.id"), nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("value", sa.String(), nullable=False),
    )
    op.create_index("ix_scenario_assumptions_scenario_id", "scenario_assumptions", ["scenario_id"])

    op.create_table(
        "scenario_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("scenario_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("scenarios.id"), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("engine_version", sa.String(), nullable=False),
        sa.Column("assumptions_hash", sa.String(), nullable=False),
        sa.Column("impact", postgresql.JSONB(), nullable=False),
        sa.Column("periods", postgresql.JSONB(), nullable=False),
        sa.Column("baseline_periods", postgresql.JSONB(), nullable=False),
    )
    op.create_index("ix_scenario_results_scenario_id", "scenario_results", ["scenario_id"])

    op.create_table(
        "forecasts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("horizon_months", sa.Integer(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "input_snapshot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("position_snapshots.id"),
            nullable=False,
        ),
        sa.Column("assumptions", postgresql.JSONB(), nullable=False),
        sa.Column("engine_version", sa.String(), nullable=False),
        sa.Column("is_stale", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_forecasts_user_id", "forecasts", ["user_id"])
    op.execute(
        "CREATE TRIGGER forecasts_set_updated_at BEFORE UPDATE ON forecasts "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )

    op.create_table(
        "forecast_periods",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("forecast_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("forecasts.id"), nullable=False),
        sa.Column("period_index", sa.Integer(), nullable=False),
        sa.Column("month", sa.String(), nullable=False),
        sa.Column("projected_income", sa.Numeric(15, 2), nullable=False),
        sa.Column("projected_expenses", sa.Numeric(15, 2), nullable=False),
        sa.Column("cash_flow", sa.Numeric(15, 2), nullable=False),
        sa.Column("savings_balance", sa.Numeric(15, 2), nullable=False),
        sa.Column("debt_balance", sa.Numeric(15, 2), nullable=False),
        sa.Column("emergency_fund_months", sa.Numeric(9, 6), nullable=False),
        sa.Column("net_worth", sa.Numeric(15, 2), nullable=False),
    )
    op.create_index("ix_forecast_periods_forecast_id", "forecast_periods", ["forecast_id"])

    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("before", postgresql.JSONB(), nullable=True),
        sa.Column("after", postgresql.JSONB(), nullable=True),
        sa.Column("actor", actor_enum, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("forecast_periods")
    op.drop_table("forecasts")
    op.drop_table("scenario_results")
    op.drop_table("scenario_assumptions")
    op.drop_table("scenarios")
    op.drop_table("position_snapshots")
    for enum_name in ("actor_enum", "scenario_status_enum", "scenario_type_enum"):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
