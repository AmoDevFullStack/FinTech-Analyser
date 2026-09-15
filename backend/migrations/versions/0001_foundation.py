"""Foundation: users, accounts, transactions, categories.

Revision ID: 0001
Revises:
Create Date: 2026-09-14
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    op.execute(
        """
        CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    # create_type=False on every enum below: each is created explicitly, once, via
    # .create(checkfirst=True) immediately after. Without create_type=False, the
    # subsequent create_table call tries to CREATE TYPE a second time (Alembic's table
    # creation does not checkfirst its own implicit type creation) and fails with
    # DuplicateObject.
    account_type_enum = postgresql.ENUM(
        "transactional",
        "savings",
        "credit_card",
        "loan",
        "home_loan",
        "vehicle_finance",
        "investment",
        "manual_asset",
        name="account_type_enum",
        create_type=False,
    )
    balance_source_enum = postgresql.ENUM(
        "derived", "manual", name="balance_source_enum", create_type=False
    )
    category_kind_enum = postgresql.ENUM(
        "income", "essential", "discretionary", "debt", "saving", "transfer",
        name="category_kind_enum",
        create_type=False,
    )
    direction_enum = postgresql.ENUM(
        "debit", "credit", name="direction_enum", create_type=False
    )

    bind = op.get_bind()
    account_type_enum.create(bind, checkfirst=True)
    balance_source_enum.create(bind, checkfirst=True)
    category_kind_enum.create(bind, checkfirst=True)
    direction_enum.create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", postgresql.CITEXT(), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("full_name", sa.String(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="ZAR"),
        sa.Column("timezone", sa.String(), nullable=False, server_default="Africa/Johannesburg"),
        sa.Column("mfa_secret", sa.String(), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.execute(
        "CREATE TRIGGER users_set_updated_at BEFORE UPDATE ON users "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )

    op.create_table(
        "accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("account_type", account_type_enum, nullable=False),
        sa.Column("institution", sa.String(), nullable=True),
        sa.Column("current_balance", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("balance_source", balance_source_enum, nullable=False),
        sa.Column("manual_balance_set_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("credit_limit", sa.Numeric(15, 2), nullable=True),
        sa.Column("interest_rate", sa.Numeric(9, 6), nullable=True),
        sa.Column("opened_on", sa.Date(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_accounts_user_id", "accounts", ["user_id"])
    op.execute(
        "CREATE TRIGGER accounts_set_updated_at BEFORE UPDATE ON accounts "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )

    op.create_table(
        "categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("categories.id"), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("kind", category_kind_enum, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_categories_user_id", "categories", ["user_id"])
    op.execute(
        "CREATE TRIGGER categories_set_updated_at BEFORE UPDATE ON categories "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )

    op.create_table(
        "transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("categories.id"), nullable=True),
        sa.Column("occurred_on", sa.Date(), nullable=False),
        sa.Column("posted_on", sa.Date(), nullable=True),
        sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("normalised_description", sa.String(), nullable=False),
        sa.Column("direction", direction_enum, nullable=False),
        sa.Column("transfer_group_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_recurring", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("recurrence_group_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("category_confidence", sa.Numeric(9, 6), nullable=True),
        sa.Column("category_set_by_user", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("import_batch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("external_id", sa.String(), nullable=True),
        sa.Column("fingerprint", sa.String(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_transactions_user_id", "transactions", ["user_id"])
    op.create_index("ix_transactions_account_id", "transactions", ["account_id"])
    op.create_index("ix_transactions_occurred_on", "transactions", ["occurred_on"])
    op.create_index(
        "ix_transactions_user_occurred", "transactions", ["user_id", "occurred_on"]
    )
    op.create_index(
        "ix_transactions_account_occurred", "transactions", ["account_id", "occurred_on"]
    )
    op.create_index("ix_transactions_recurrence_group", "transactions", ["recurrence_group_id"])
    op.create_index(
        "uq_transactions_fingerprint_live",
        "transactions",
        ["user_id", "fingerprint"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.execute(
        "CREATE TRIGGER transactions_set_updated_at BEFORE UPDATE ON transactions "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )


def downgrade() -> None:
    op.drop_table("transactions")
    op.drop_table("categories")
    op.drop_table("accounts")
    op.drop_table("users")
    for enum_name in (
        "direction_enum",
        "category_kind_enum",
        "balance_source_enum",
        "account_type_enum",
    ):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
    op.execute("DROP FUNCTION IF EXISTS set_updated_at")
