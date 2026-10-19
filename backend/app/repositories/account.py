from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, text

from app.core.db import DbSession

from app.models.account import Account

_LIST_FOR_USER = text(
    """
    SELECT *
      FROM ledger.accounts
     WHERE user_id = :user_id
       AND deleted_at IS NULL
       AND (CAST(:include_archived AS boolean) OR archived_at IS NULL)
    """
)

_GET_FOR_USER = text(
    """
    SELECT *
      FROM ledger.accounts
     WHERE id = :account_id
       AND user_id = :user_id
       AND deleted_at IS NULL
    """
)


class AccountRepository:
    """Every method takes `user_id` and filters on it — see docs/architecture.md §3.4.
    Scoping is enforced here, not in the API layer, so no future call site can forget it.
    """

    def __init__(self, session: DbSession) -> None:
        self._session = session

    def list_for_user(self, *, user_id: UUID, include_archived: bool = False) -> list[Account]:
        return list(
            self._session.scalars(
                select(Account).from_statement(_LIST_FOR_USER),
                {"user_id": user_id, "include_archived": include_archived},
            )
        )

    def get_for_user(self, account_id: UUID, *, user_id: UUID) -> Account | None:
        return self._session.scalars(
            select(Account).from_statement(_GET_FOR_USER),
            {"account_id": account_id, "user_id": user_id},
        ).first()

    def add(self, account: Account) -> Account:
        self._session.add(account)
        self._session.flush()
        return account
