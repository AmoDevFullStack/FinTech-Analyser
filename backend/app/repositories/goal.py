from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import select

from app.core.db import DbSession
from app.models.goal import Goal, GoalContribution


class GoalRepository:
    """Every method takes `user_id` and filters on it — see docs/architecture.md §3.4."""

    def __init__(self, session: DbSession) -> None:
        self._session = session

    def list_for_user(self, *, user_id: UUID) -> list[Goal]:
        stmt = (
            select(Goal)
            .where(Goal.user_id == user_id, Goal.deleted_at.is_(None))
            .order_by(Goal.priority, Goal.target_date)
        )
        return list(self._session.scalars(stmt))

    def get_for_user(self, goal_id: UUID, *, user_id: UUID) -> Goal | None:
        stmt = select(Goal).where(
            Goal.id == goal_id, Goal.user_id == user_id, Goal.deleted_at.is_(None)
        )
        return self._session.scalars(stmt).first()

    def add(self, goal: Goal) -> Goal:
        self._session.add(goal)
        self._session.flush()
        return goal

    def contributions_for(
        self, goal_id: UUID, *, user_id: UUID, since: date | None = None
    ) -> list[GoalContribution]:
        stmt = select(GoalContribution).where(
            GoalContribution.goal_id == goal_id, GoalContribution.user_id == user_id
        )
        if since is not None:
            stmt = stmt.where(GoalContribution.occurred_on >= since)
        stmt = stmt.order_by(GoalContribution.occurred_on)
        return list(self._session.scalars(stmt))

    def add_contribution(self, contribution: GoalContribution) -> GoalContribution:
        self._session.add(contribution)
        self._session.flush()
        return contribution
