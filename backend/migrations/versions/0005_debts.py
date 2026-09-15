"""Debts. See specs/debts.md and docs/database.md §3.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-15
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

DEBT_TYPE_ENUM = postgresql.ENUM(
    "credit_card", "personal_loan", "vehicle", "home_loan", "store_account", "other",
    name="debt_type_enum",
    create_type=False,
)


def upgrade() -> None:
    DEBT_TYPE_ENUM.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "debts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=True),
        sa.Column("debt_type", DEBT_TYPE_ENUM, nullable=False),
        sa.Column("original_principal", sa.Numeric(15, 2), nullable=False),
        sa.Column("current_balance", sa.Numeric(15, 2), nullable=False),
        sa.Column("annual_rate", sa.Numeric(9, 6), nullable=False),
        sa.Column("minimum_payment", sa.Numeric(15, 2), nullable=False),
        sa.Column("instalment", sa.Numeric(15, 2), nullable=True),
        sa.Column("term_months", sa.Integer(), nullable=True),
        sa.Column("started_on", sa.Date(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_debts_user_id", "debts", ["user_id"])
    op.execute(
        "CREATE TRIGGER debts_set_updated_at BEFORE UPDATE ON debts "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS debts_set_updated_at ON debts")
    op.drop_index("ix_debts_user_id", table_name="debts")
    op.drop_table("debts")
    DEBT_TYPE_ENUM.drop(op.get_bind(), checkfirst=True)
