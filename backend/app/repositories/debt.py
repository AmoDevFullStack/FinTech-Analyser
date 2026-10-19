from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, text

from app.core.db import DbSession
from app.models.debt import Debt

_LIST_FOR_USER = text(
    """
    SELECT *
      FROM obligations.debts
     WHERE user_id = :user_id
       AND deleted_at IS NULL
    """
)

_GET_FOR_USER = text(
    """
    SELECT *
      FROM obligations.debts
     WHERE id = :debt_id
       AND user_id = :user_id
       AND deleted_at IS NULL
    """
)


class DebtRepository:
    """Every method takes `user_id` and filters on it — see docs/architecture.md §3.4.
    Scoping is enforced here, not in the API layer, so no future call site can forget it.
    """

    def __init__(self, session: DbSession) -> None:
        self._session = session

    def list_for_user(self, *, user_id: UUID) -> list[Debt]:
        return list(
            self._session.scalars(
                select(Debt).from_statement(_LIST_FOR_USER), {"user_id": user_id}
            )
        )

    def get_for_user(self, debt_id: UUID, *, user_id: UUID) -> Debt | None:
        return self._session.scalars(
            select(Debt).from_statement(_GET_FOR_USER),
            {"debt_id": debt_id, "user_id": user_id},
        ).first()

    def add(self, debt: Debt) -> Debt:
        self._session.add(debt)
        self._session.flush()
        return debt
