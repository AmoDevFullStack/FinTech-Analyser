from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, pg_enum


class Direction(str, enum.Enum):
    DEBIT = "debit"
    CREDIT = "credit"


class Transaction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """See docs/database.md §3: sign convention is outflow-negative, inflow-positive, for
    every account type without exception. `fingerprint` is the exact-dedup key.
    """

    __tablename__ = "transactions"

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    account_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False, index=True
    )
    category_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("categories.id"), nullable=True
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
    import_batch_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("import_batches.id"), nullable=True
    )
    external_id: Mapped[str | None] = mapped_column(String, nullable=True)
    fingerprint: Mapped[str] = mapped_column(String, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
