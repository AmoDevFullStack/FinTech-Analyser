from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, text

from app.core.db import DbSession
from app.models.health_assessment import HealthAssessment

_LATEST_FOR_USER = text(
    """
    SELECT *
      FROM health_assessments
     WHERE user_id = :user_id
     ORDER BY computed_at DESC
    """
)

_HISTORY_FOR_USER = text(
    """
    SELECT *
      FROM health_assessments
     WHERE user_id = :user_id
       AND (CAST(:since AS timestamptz) IS NULL OR computed_at >= CAST(:since AS timestamptz))
       AND (CAST(:until AS timestamptz) IS NULL OR computed_at <= CAST(:until AS timestamptz))
     ORDER BY computed_at DESC
     LIMIT :limit
    """
)


class HealthAssessmentRepository:
    def __init__(self, session: DbSession) -> None:
        self._session = session

    def latest_for_user(self, *, user_id: UUID) -> HealthAssessment | None:
        return self._session.scalars(
            select(HealthAssessment).from_statement(_LATEST_FOR_USER), {"user_id": user_id}
        ).first()

    def history_for_user(
        self,
        *,
        user_id: UUID,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 50,
    ) -> list[HealthAssessment]:
        return list(
            self._session.scalars(
                select(HealthAssessment).from_statement(_HISTORY_FOR_USER),
                {"user_id": user_id, "since": since, "until": until, "limit": limit},
            )
        )

    def add(self, assessment: HealthAssessment) -> HealthAssessment:
        self._session.add(assessment)
        self._session.flush()
        return assessment
