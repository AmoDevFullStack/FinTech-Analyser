from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, pg_enum


class RiskStatus(str, enum.Enum):
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    DISMISSED = "dismissed"
    RESOLVED = "resolved"


class RiskFlag(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """See docs/database.md §5 and specs/risk-detection.md.

    `computation_reference` is not nullable on purpose: "A flag without a computation
    reference cannot be explained and must not be created." The column type enforces what
    the spec asks for, so no future code path can create an unexplainable flag.

    `dismissed_at` drives the 30-day suppression, and `severity` is stored so a
    re-evaluation can tell an escalation (which overrides suppression) from a repeat.
    """

    __tablename__ = "risk_flags"

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    risk_type: Mapped[str] = mapped_column(String, nullable=False)
    severity: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[RiskStatus] = mapped_column(
        pg_enum(RiskStatus, name="risk_status_enum"), nullable=False
    )
    detected_on: Mapped[date] = mapped_column(Date, nullable=False)
    projected_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    quantified_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    explanation: Mapped[str] = mapped_column(String, nullable=False)
    computation_reference: Mapped[str] = mapped_column(String, nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
