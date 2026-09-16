from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import select, text

from app.core.db import DbSession
from app.models.goal import Goal, GoalContribution

_LIST_FOR_USER = text(
    """
    SELECT *
      FROM goals
     WHERE user_id = :user_id
       AND deleted_at IS NULL
     ORDER BY priority, target_date
    """
)

_GET_FOR_USER = text(
    """
    SELECT *
      FROM goals
     WHERE id = :goal_id
       AND user_id = :user_id
       AND deleted_at IS NULL
    """
)

_CONTRIBUTIONS_FOR = text(
    """
    SELECT *
      FROM goal_contributions
     WHERE goal_id = :goal_id
       AND user_id = :user_id
       AND (CAST(:since AS date) IS NULL OR occurred_on >= CAST(:since AS date))
     ORDER BY occurred_on
    """
)


class GoalRepository:
    """Every method takes `user_id` and filters on it — see docs/architecture.md §3.4."""

    def __init__(self, session: DbSession) -> None:
        self._session = session

    def list_for_user(self, *, user_id: UUID) -> list[Goal]:
        return list(
            self._session.scalars(
                select(Goal).from_statement(_LIST_FOR_USER), {"user_id": user_id}
            )
        )

    def get_for_user(self, goal_id: UUID, *, user_id: UUID) -> Goal | None:
        return self._session.scalars(
            select(Goal).from_statement(_GET_FOR_USER),
            {"goal_id": goal_id, "user_id": user_id},
        ).first()

    def contributions_for(
        self, goal_id: UUID, *, user_id: UUID, since: date | None = None
    ) -> list[GoalContribution]:
        return list(
            self._session.scalars(
                select(GoalContribution).from_statement(_CONTRIBUTIONS_FOR),
                {"goal_id": goal_id, "user_id": user_id, "since": since},
            )
        )

    def add_contribution(self, contribution: GoalContribution) -> GoalContribution:
        self._session.add(contribution)
        self._session.flush()
        return contribution

    def add(self, goal: Goal) -> Goal:
        self._session.add(goal)
        self._session.flush()
        return goal
