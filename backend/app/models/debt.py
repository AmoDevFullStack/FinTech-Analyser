from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, pg_enum


class DebtType(str, enum.Enum):
    CREDIT_CARD = "credit_card"
    PERSONAL_LOAN = "personal_loan"
    VEHICLE = "vehicle"
    HOME_LOAN = "home_loan"
    STORE_ACCOUNT = "store_account"
    OTHER = "other"


class Debt(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """See docs/database.md §3 and specs/debts.md.

    `account_id` links this debt to a tracked `Account` where one exists (a credit card
    is both), and is null for a debt with no corresponding account — a personal loan the
    user only records here, for instance. `term_months` is null for a debt with no fixed
    term (a credit card or store account), in which case a schedule is driven by
    `minimum_payment` instead of a solved instalment — see app/domain/debt_payoff.py.
    """

    __tablename__ = "debts"
    __table_args__ = {"schema": "obligations"}

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=False, index=True
    )
    account_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ledger.accounts.id"), nullable=True
    )
    debt_type: Mapped[DebtType] = mapped_column(pg_enum(DebtType, name="debt_type_enum"), nullable=False)
    original_principal: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    current_balance: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    annual_rate: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    minimum_payment: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    instalment: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    term_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_on: Mapped[date] = mapped_column(Date, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
