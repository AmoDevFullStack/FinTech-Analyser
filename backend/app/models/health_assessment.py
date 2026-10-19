from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class HealthAssessment(UUIDPrimaryKeyMixin, Base):
    """One calendar month's score, with a JSONB breakdown — see docs/database.md §5. The
    breakdown is never optional: requirement 10 demands the score be inspectable.

    `month` is what the assessment is *about*; `computed_at` is when it was worked out.
    Keeping both is what makes "is the score improving?" answerable: before this column,
    history was a log of when the assessment happened to run, so two runs on one afternoon
    read as two data points and a quiet fortnight read as none.

    The unique constraint means re-assessing a month corrects that month's row instead of
    accumulating a second opinion about the same period — the same rule
    `analytics.forecast_accuracy` follows.
    """

    __tablename__ = "health_assessments"
    __table_args__ = (
        UniqueConstraint("user_id", "month", name="uq_health_assessment_month"),
        {"schema": "analytics"},
    )

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=False, index=True
    )
    #: The calendar month assessed, `YYYY-MM`.
    month: Mapped[str] = mapped_column(String, nullable=False, index=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    score: Mapped[int] = mapped_column(nullable=False)
    weights_version: Mapped[str] = mapped_column(String, nullable=False)
    breakdown: Mapped[dict] = mapped_column(JSONB, nullable=False)
