from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, pg_enum


class AccountType(str, enum.Enum):
    TRANSACTIONAL = "transactional"
    SAVINGS = "savings"
    CREDIT_CARD = "credit_card"
    LOAN = "loan"
    HOME_LOAN = "home_loan"
    VEHICLE_FINANCE = "vehicle_finance"
    INVESTMENT = "investment"
    MANUAL_ASSET = "manual_asset"


class BalanceSource(str, enum.Enum):
    DERIVED = "derived"
    MANUAL = "manual"


class Account(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "accounts"

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    account_type: Mapped[AccountType] = mapped_column(
        pg_enum(AccountType, name="account_type_enum"), nullable=False
    )
    institution: Mapped[str | None] = mapped_column(String, nullable=True)
    current_balance: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    balance_source: Mapped[BalanceSource] = mapped_column(
        pg_enum(BalanceSource, name="balance_source_enum"), nullable=False
    )
    manual_balance_set_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    credit_limit: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    interest_rate: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    opened_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
