from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select

from app.core.db import DbSession
from app.models.health_assessment import HealthAssessment


class HealthAssessmentRepository:
    def __init__(self, session: DbSession) -> None:
        self._session = session

    def latest_for_user(self, *, user_id: UUID) -> HealthAssessment | None:
        stmt = (
            select(HealthAssessment)
            .where(HealthAssessment.user_id == user_id)
            .order_by(HealthAssessment.computed_at.desc())
        )
        return self._session.scalars(stmt).first()

    def history_for_user(
        self,
        *,
        user_id: UUID,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 50,
    ) -> list[HealthAssessment]:
        stmt = select(HealthAssessment).where(HealthAssessment.user_id == user_id)
        if since is not None:
            stmt = stmt.where(HealthAssessment.computed_at >= since)
        if until is not None:
            stmt = stmt.where(HealthAssessment.computed_at <= until)
        stmt = stmt.order_by(HealthAssessment.computed_at.desc()).limit(limit)
        return list(self._session.scalars(stmt))

    def add(self, assessment: HealthAssessment) -> HealthAssessment:
        self._session.add(assessment)
        self._session.flush()
        return assessment
