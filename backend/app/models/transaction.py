from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.payment_taxonomy import PaymentMethod, SpendingPurpose
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, pg_enum
from app.models.enums import PAYMENT_METHOD_ENUM, SPENDING_PURPOSE_ENUM


class Direction(str, enum.Enum):
    DEBIT = "debit"
    CREDIT = "credit"


class Transaction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """See docs/database.md §3: sign convention is outflow-negative, inflow-positive, for
    every account type without exception. `fingerprint` is the exact-dedup key.
    """

    __tablename__ = "transactions"
    __table_args__ = {"schema": "ledger"}

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=False, index=True
    )
    account_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ledger.accounts.id"), nullable=False, index=True
    )
    category_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ledger.categories.id"), nullable=True
    )
    occurred_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    posted_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    normalised_description: Mapped[str] = mapped_column(String, nullable=False)
    direction: Mapped[Direction] = mapped_column(
        pg_enum(Direction, name="direction_enum"), nullable=False
    )
    transfer_group_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    is_recurring: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    recurrence_group_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    category_confidence: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    category_set_by_user: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Spending detection (app/domain/payment_taxonomy.py). Method and purpose are stored
    # separately from `category_id` on purpose: a category is what the user's chart of
    # accounts calls this, which they may rename or correct, while these two are what the
    # statement line itself said. Keeping both means a later change to the rule table can
    # be re-run over history without destroying a user's corrections, and a user's
    # correction never rewrites the evidence it was made against.
    payment_method: Mapped[PaymentMethod | None] = mapped_column(
        PAYMENT_METHOD_ENUM, nullable=True
    )
    spending_purpose: Mapped[SpendingPurpose | None] = mapped_column(
        SPENDING_PURPOSE_ENUM, nullable=True
    )
    merchant: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    purpose_confidence: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    import_batch_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ledger.import_batches.id"), nullable=True
    )
    external_id: Mapped[str | None] = mapped_column(String, nullable=True)
    fingerprint: Mapped[str] = mapped_column(String, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
