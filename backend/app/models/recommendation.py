from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, pg_enum

import enum


class RecommendationStatus(str, enum.Enum):
    ACTIVE = "active"
    DISMISSED = "dismissed"
    ACTED_ON = "acted_on"


class Recommendation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """See specs/recommendations.md.

    `computation_reference` and `benefit_amount` are both NOT NULL because the spec allows
    no recommendation without them: "Every recommendation carries a quantified benefit and
    its computation reference." `benefit_amount` is also what the list is ranked by.

    `dismissed_at` drives the 60-day suppression, and the stored benefit is what a later
    evaluation compares against to decide whether the benefit has "materially increased"
    enough to override that suppression.
    """

    __tablename__ = "recommendations"
    __table_args__ = {"schema": "analytics"}

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=False, index=True
    )
    rule_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[RecommendationStatus] = mapped_column(
        pg_enum(RecommendationStatus, name="recommendation_status_enum"), nullable=False
    )
    benefit_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    benefit_kind: Mapped[str] = mapped_column(String, nullable=False)
    explanation: Mapped[str] = mapped_column(String, nullable=False)
    computation_reference: Mapped[str] = mapped_column(String, nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False)
    generated_on: Mapped[date] = mapped_column(Date, nullable=False)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
