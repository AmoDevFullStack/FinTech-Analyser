from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.core.db import DbSession
from app.models.debt import Debt


class DebtRepository:
    """Every method takes `user_id` and filters on it — see docs/architecture.md §3.4.
    Scoping is enforced here, not in the API layer, so no future call site can forget it.
    """

    def __init__(self, session: DbSession) -> None:
        self._session = session

    def list_for_user(self, *, user_id: UUID) -> list[Debt]:
        stmt = select(Debt).where(Debt.user_id == user_id, Debt.deleted_at.is_(None))
        return list(self._session.scalars(stmt))

    def get_for_user(self, debt_id: UUID, *, user_id: UUID) -> Debt | None:
        stmt = select(Debt).where(
            Debt.id == debt_id, Debt.user_id == user_id, Debt.deleted_at.is_(None)
        )
        return self._session.scalars(stmt).first()

    def add(self, debt: Debt) -> Debt:
        self._session.add(debt)
        self._session.flush()
        return debt
