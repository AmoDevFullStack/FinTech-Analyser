"""Remembered per-account column mappings. See specs/transactions.md step 1.

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-15
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "account_column_mappings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("mapping", postgresql.JSONB(), nullable=False),
        sa.Column("label", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("account_id", name="uq_account_column_mapping"),
    )
    op.create_index("ix_account_column_mappings_user_id", "account_column_mappings", ["user_id"])
    op.execute(
        "CREATE TRIGGER account_column_mappings_set_updated_at BEFORE UPDATE ON account_column_mappings "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )

    # Merge resolution (specs/transactions.md step 3) updates an existing row instead of
    # inserting, so the import summary needs somewhere to report how many it moved.
    op.add_column(
        "import_batches",
        sa.Column("rows_merged", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("import_batches", "rows_merged")
    op.execute("DROP TRIGGER IF EXISTS account_column_mappings_set_updated_at ON account_column_mappings")
    op.drop_index("ix_account_column_mappings_user_id", table_name="account_column_mappings")
    op.drop_table("account_column_mappings")
