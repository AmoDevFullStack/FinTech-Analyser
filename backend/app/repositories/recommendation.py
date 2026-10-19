from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, text

from app.core.db import DbSession
from app.models.recommendation import Recommendation, RecommendationStatus

_LIST_FOR_USER = text(
    """
    SELECT *
      FROM analytics.recommendations
     WHERE user_id = :user_id
       AND (
         CAST(:status AS shared.recommendation_status_enum) IS NULL
         OR status = CAST(:status AS shared.recommendation_status_enum)
       )
     ORDER BY benefit_amount DESC
    """
)

_LATEST_OF_RULE = text(
    """
    SELECT *
      FROM analytics.recommendations
     WHERE user_id = :user_id
       AND rule_id = :rule_id
     ORDER BY generated_on DESC, created_at DESC
    """
)

_GET_FOR_USER = text(
    """
    SELECT *
      FROM analytics.recommendations
     WHERE id = :recommendation_id
       AND user_id = :user_id
    """
)


class RecommendationRepository:
    """Every method takes `user_id` and filters on it — see docs/architecture.md §3.4."""

    def __init__(self, session: DbSession) -> None:
        self._session = session

    def list_for_user(
        self, *, user_id: UUID, status: RecommendationStatus | None = RecommendationStatus.ACTIVE
    ) -> list[Recommendation]:
        return list(
            self._session.scalars(
                select(Recommendation).from_statement(_LIST_FOR_USER),
                {"user_id": user_id, "status": status.value if status is not None else None},
            )
        )

    def latest_of_rule(self, *, user_id: UUID, rule_id: str) -> Recommendation | None:
        return self._session.scalars(
            select(Recommendation).from_statement(_LATEST_OF_RULE),
            {"user_id": user_id, "rule_id": rule_id},
        ).first()

    def get_for_user(self, recommendation_id: UUID, *, user_id: UUID) -> Recommendation | None:
        return self._session.scalars(
            select(Recommendation).from_statement(_GET_FOR_USER),
            {"recommendation_id": recommendation_id, "user_id": user_id},
        ).first()

    def add(self, recommendation: Recommendation) -> Recommendation:
        self._session.add(recommendation)
        self._session.flush()
        return recommendation
