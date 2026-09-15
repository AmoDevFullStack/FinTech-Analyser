"""Recommendation evaluation worker.

specs/recommendations.md: "Evaluated by a worker after forecast regeneration." A thin
entry point calling the same service the API calls, per docs/architecture.md §3.5.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from app.core.db import DbSession
from app.models.recommendation import Recommendation
from app.services.recommendation import RecommendationService


def evaluate_recommendations(
    session: DbSession, *, user_id: UUID, as_of: date | None = None
) -> list[Recommendation]:
    return RecommendationService(session).evaluate(user_id=user_id, as_of=as_of)
