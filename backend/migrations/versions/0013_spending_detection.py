"""Spending detection: payment method, purpose, and merchant on transactions.

See app/domain/payment_taxonomy.py and specs/transactions.md steps 2 and 5.

Both `transactions` and `staged_transactions` carry the columns, because detection runs at
staging so the impact preview a user approves is computed from the same classification the
committed rows will carry.

Every column is nullable and no backfill is attempted. A backfill would have to re-run the
rule table over existing history, and doing that silently inside a schema migration would
change figures a user has already seen with no record of why. `POST /transactions/reclassify`
is the explicit, user-initiated path for that.

The two enum types are created once here, before either table is altered, rather than
inline per column — the same failure the 0005/0007/0009 fix addressed.

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-16
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

PAYMENT_METHOD_ENUM = postgresql.ENUM(
    "debit_order",
    "stop_order",
    "card_purchase",
    "card_online",
    "atm_withdrawal",
    "cash_deposit",
    "eft_out",
    "eft_in",
    "instant_payment",
    "internal_transfer",
    "salary_deposit",
    "cheque",
    "bank_fee",
    "interest",
    "reversal",
    "unknown",
    name="payment_method_enum",
    create_type=False,
)

SPENDING_PURPOSE_ENUM = postgresql.ENUM(
    "rent",
    "bond_repayment",
    "levies",
    "rates_and_taxes",
    "utilities",
    "groceries",
    "fuel",
    "transport",
    "vehicle_instalment",
    "insurance",
    "medical",
    "telecoms",
    "subscriptions",
    "dining",
    "entertainment",
    "clothing",
    "education",
    "childcare",
    "domestic_help",
    "savings",
    "investment",
    "debt_repayment",
    "bank_charges",
    "salary",
    "other_income",
    "internal_transfer",
    "unknown",
    name="spending_purpose_enum",
    create_type=False,
)

_TABLES = ("transactions", "staged_transactions")


def upgrade() -> None:
    bind = op.get_bind()
    PAYMENT_METHOD_ENUM.create(bind, checkfirst=True)
    SPENDING_PURPOSE_ENUM.create(bind, checkfirst=True)

    for table in _TABLES:
        op.add_column(table, sa.Column("payment_method", PAYMENT_METHOD_ENUM, nullable=True))
        op.add_column(table, sa.Column("spending_purpose", SPENDING_PURPOSE_ENUM, nullable=True))
        op.add_column(table, sa.Column("merchant", sa.String(), nullable=True))
        op.add_column(table, sa.Column("purpose_confidence", sa.Numeric(9, 6), nullable=True))

    # Merchant is the join key for "everything I have ever paid this shop", which is the
    # query behind both the recurring-series view and the fuzzy search's candidate window.
    op.create_index("ix_transactions_merchant", "transactions", ["merchant"])
    # Purpose is what the cash-flow and health figures group by, always within one user.
    op.create_index(
        "ix_transactions_user_id_spending_purpose",
        "transactions",
        ["user_id", "spending_purpose"],
    )


def downgrade() -> None:
    op.drop_index("ix_transactions_user_id_spending_purpose", table_name="transactions")
    op.drop_index("ix_transactions_merchant", table_name="transactions")

    for table in _TABLES:
        op.drop_column(table, "purpose_confidence")
        op.drop_column(table, "merchant")
        op.drop_column(table, "spending_purpose")
        op.drop_column(table, "payment_method")

    bind = op.get_bind()
    SPENDING_PURPOSE_ENUM.drop(bind, checkfirst=True)
    PAYMENT_METHOD_ENUM.drop(bind, checkfirst=True)
