from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ForecastAccuracy(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One measured month, per metric. See specs/forecasting.md's accuracy section.

    `forecast_id` records which forecast made the projection being scored, so an
    improvement in accuracy can be attributed to the engine version that produced it
    rather than to the passage of time. The unique constraint means re-measuring a month
    corrects the existing row instead of accumulating duplicates for the same claim.
    """

    __tablename__ = "forecast_accuracy"
    __table_args__ = (
        UniqueConstraint("user_id", "month", "metric", name="uq_forecast_accuracy_month_metric"),
        {"schema": "analytics"},
    )

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=False, index=True
    )
    forecast_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    month: Mapped[str] = mapped_column(String, nullable=False)
    metric: Mapped[str] = mapped_column(String, nullable=False)
    projected: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    actual: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    absolute_error: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    signed_error: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    percentage_error: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    engine_version: Mapped[str] = mapped_column(String, nullable=False)
