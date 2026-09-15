"""Data in: import batches and staging. See specs/transactions.md.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-14
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # create_type=False — see the comment in 0001_foundation.py's upgrade().
    import_status_enum = postgresql.ENUM(
        "staged", "awaiting_resolution", "committed", "undone", "failed",
        name="import_status_enum",
        create_type=False,
    )
    import_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "import_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("status", import_status_enum, nullable=False),
        sa.Column("detected_format", sa.String(), nullable=True),
        sa.Column("rows_parsed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_imported", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_skipped_duplicate", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_pending_conflict", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_import_batches_user_id", "import_batches", ["user_id"])
    op.execute(
        "CREATE TRIGGER import_batches_set_updated_at BEFORE UPDATE ON import_batches "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_foreign_key(
        "fk_transactions_import_batch", "transactions", "import_batches", ["import_batch_id"], ["id"]
    )

    op.create_table(
        "staged_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "import_batch_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("import_batches.id"),
            nullable=False,
        ),
        sa.Column("occurred_on", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("normalised_description", sa.String(), nullable=False),
        sa.Column("fingerprint", sa.String(), nullable=False),
        sa.Column("is_exact_duplicate", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "conflict_candidate_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("transactions.id"),
            nullable=True,
        ),
        sa.Column("resolution", sa.String(), nullable=True),
        sa.Column("raw_row", postgresql.JSONB(), nullable=False),
    )
    op.create_index("ix_staged_transactions_batch", "staged_transactions", ["import_batch_id"])
    op.create_index("ix_staged_transactions_fingerprint", "staged_transactions", ["fingerprint"])


def downgrade() -> None:
    op.drop_table("staged_transactions")
    op.drop_constraint("fk_transactions_import_batch", "transactions", type_="foreignkey")
    op.drop_table("import_batches")
    op.execute("DROP TYPE IF EXISTS import_status_enum")
