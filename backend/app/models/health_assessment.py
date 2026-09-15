from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class HealthAssessment(UUIDPrimaryKeyMixin, Base):
    """Score, computed date, and a JSONB breakdown — see docs/database.md §5. The
    breakdown is never optional: requirement 10 demands the score be inspectable.
    """

    __tablename__ = "health_assessments"

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    score: Mapped[int] = mapped_column(nullable=False)
    weights_version: Mapped[str] = mapped_column(String, nullable=False)
    breakdown: Mapped[dict] = mapped_column(JSONB, nullable=False)
