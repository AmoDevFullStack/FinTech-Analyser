from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, text

from app.core.db import DbSession
from app.models.health_assessment import HealthAssessment

# Ordered by `month`, not by `computed_at`. "Latest" means the most recent period assessed,
# not the most recent time the assessment happened to run — after a backfill those are
# different rows, and the one a user is shown should be the one about now.
_LATEST_FOR_USER = text(
    """
    SELECT *
      FROM analytics.health_assessments
     WHERE user_id = :user_id
     ORDER BY month DESC
     LIMIT 1
    """
)

_FOR_MONTH = text(
    """
    SELECT *
      FROM analytics.health_assessments
     WHERE user_id = :user_id
       AND month = :month
    """
)

_RECENT_MONTHS = text(
    """
    SELECT *
      FROM analytics.health_assessments
     WHERE user_id = :user_id
     ORDER BY month DESC
     LIMIT :limit
    """
)

_MONTHS_FOR_USER = text(
    """
    SELECT *
      FROM analytics.health_assessments
     WHERE user_id = :user_id
       AND (CAST(:since AS text) IS NULL OR month >= CAST(:since AS text))
       AND (CAST(:until AS text) IS NULL OR month <= CAST(:until AS text))
     ORDER BY month
     LIMIT :limit
    """
)


class HealthAssessmentRepository:
    """Every method takes `user_id` and filters on it — see docs/architecture.md §3.4.

    `month` is a `YYYY-MM` string, which sorts and compares chronologically as text. That
    is why the range filters above are plain string comparisons rather than date casts.
    """

    def __init__(self, session: DbSession) -> None:
        self._session = session

    def latest_for_user(self, *, user_id: UUID) -> HealthAssessment | None:
        return self._session.scalars(
            select(HealthAssessment).from_statement(_LATEST_FOR_USER), {"user_id": user_id}
        ).first()

    def for_month(self, *, user_id: UUID, month: str) -> HealthAssessment | None:
        return self._session.scalars(
            select(HealthAssessment).from_statement(_FOR_MONTH),
            {"user_id": user_id, "month": month},
        ).first()

    def recent_for_user(self, *, user_id: UUID, limit: int = 2) -> list[HealthAssessment]:
        """The most recent months assessed, newest first.

        Separate from `months_for_user` because the dashboard wants the last two and
        nothing else; reading the whole series to take two off the end is a table scan to
        answer a question about two rows.
        """
        return list(
            self._session.scalars(
                select(HealthAssessment).from_statement(_RECENT_MONTHS),
                {"user_id": user_id, "limit": limit},
            )
        )

    def months_for_user(
        self,
        *,
        user_id: UUID,
        since: str | None = None,
        until: str | None = None,
        limit: int = 60,
    ) -> list[HealthAssessment]:
        """Oldest month first — a series is read left to right."""
        return list(
            self._session.scalars(
                select(HealthAssessment).from_statement(_MONTHS_FOR_USER),
                {"user_id": user_id, "since": since, "until": until, "limit": limit},
            )
        )

    def add(self, assessment: HealthAssessment) -> HealthAssessment:
        self._session.add(assessment)
        self._session.flush()
        return assessment
