from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from app.core.db import DbSession

from app.models.account import Account


class AccountRepository:
    """Every method takes `user_id` and filters on it — see docs/architecture.md §3.4.
    Scoping is enforced here, not in the API layer, so no future call site can forget it.
    """

    def __init__(self, session: DbSession) -> None:
        self._session = session

    def list_for_user(self, *, user_id: UUID, include_archived: bool = False) -> list[Account]:
        stmt = select(Account).where(Account.user_id == user_id, Account.deleted_at.is_(None))
        if not include_archived:
            stmt = stmt.where(Account.archived_at.is_(None))
        return list(self._session.scalars(stmt))

    def get_for_user(self, account_id: UUID, *, user_id: UUID) -> Account | None:
        stmt = select(Account).where(
            Account.id == account_id,
            Account.user_id == user_id,
            Account.deleted_at.is_(None),
        )
        return self._session.scalars(stmt).first()

    def add(self, account: Account) -> Account:
        self._session.add(account)
        self._session.flush()
        return account
