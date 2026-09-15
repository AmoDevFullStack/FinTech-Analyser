from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.core.db import DbSession
from app.models.recommendation import Recommendation, RecommendationStatus


class RecommendationRepository:
    """Every method takes `user_id` and filters on it — see docs/architecture.md §3.4."""

    def __init__(self, session: DbSession) -> None:
        self._session = session

    def list_for_user(
        self, *, user_id: UUID, status: RecommendationStatus | None = RecommendationStatus.ACTIVE
    ) -> list[Recommendation]:
        stmt = select(Recommendation).where(Recommendation.user_id == user_id)
        if status is not None:
            stmt = stmt.where(Recommendation.status == status)
        stmt = stmt.order_by(Recommendation.benefit_amount.desc())
        return list(self._session.scalars(stmt))

    def latest_of_rule(self, *, user_id: UUID, rule_id: str) -> Recommendation | None:
        stmt = (
            select(Recommendation)
            .where(Recommendation.user_id == user_id, Recommendation.rule_id == rule_id)
            .order_by(Recommendation.generated_on.desc(), Recommendation.created_at.desc())
        )
        return self._session.scalars(stmt).first()

    def get_for_user(self, recommendation_id: UUID, *, user_id: UUID) -> Recommendation | None:
        stmt = select(Recommendation).where(
            Recommendation.id == recommendation_id, Recommendation.user_id == user_id
        )
        return self._session.scalars(stmt).first()

    def add(self, recommendation: Recommendation) -> Recommendation:
        self._session.add(recommendation)
        self._session.flush()
        return recommendation
