from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Forecast(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "forecasts"
    __table_args__ = {"schema": "analytics"}

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=False, index=True
    )
    horizon_months: Mapped[int] = mapped_column(nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    input_snapshot_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("analytics.position_snapshots.id"), nullable=False
    )
    assumptions: Mapped[dict] = mapped_column(JSONB, nullable=False)
    engine_version: Mapped[str] = mapped_column(String, nullable=False)
    is_stale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class ForecastPeriod(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "forecast_periods"
    __table_args__ = {"schema": "analytics"}

    forecast_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("analytics.forecasts.id"), nullable=False, index=True
    )
    period_index: Mapped[int] = mapped_column(nullable=False)
    month: Mapped[str] = mapped_column(String, nullable=False)
    projected_income: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    projected_expenses: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    cash_flow: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    savings_balance: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    debt_balance: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    emergency_fund_months: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    net_worth: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
