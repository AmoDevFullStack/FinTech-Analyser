"""Goals and goal contributions. See specs/goals.md and docs/database.md §3.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-15
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "goals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("target_amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("current_amount", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("planned_monthly_contribution", sa.Numeric(15, 2), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_goals_user_id", "goals", ["user_id"])
    op.execute(
        "CREATE TRIGGER goals_set_updated_at BEFORE UPDATE ON goals "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )

    op.create_table(
        "goal_contributions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("goal_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("goals.id"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("occurred_on", sa.Date(), nullable=False),
        sa.Column("note", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_goal_contributions_goal_id", "goal_contributions", ["goal_id"])
    op.create_index("ix_goal_contributions_user_id", "goal_contributions", ["user_id"])
    op.execute(
        "CREATE TRIGGER goal_contributions_set_updated_at BEFORE UPDATE ON goal_contributions "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS goal_contributions_set_updated_at ON goal_contributions")
    op.drop_index("ix_goal_contributions_user_id", table_name="goal_contributions")
    op.drop_index("ix_goal_contributions_goal_id", table_name="goal_contributions")
    op.drop_table("goal_contributions")
    op.execute("DROP TRIGGER IF EXISTS goals_set_updated_at ON goals")
    op.drop_index("ix_goals_user_id", table_name="goals")
    op.drop_table("goals")
