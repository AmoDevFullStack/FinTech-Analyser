from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, text

from app.core.db import DbSession
from app.models.column_mapping import AccountColumnMapping

_FOR_ACCOUNT = text(
    """
    SELECT *
      FROM ledger.column_mappings
     WHERE account_id = :account_id
       AND user_id = :user_id
    """
)


class ColumnMappingRepository:
    """Every method takes `user_id` and filters on it — see docs/architecture.md §3.4."""

    def __init__(self, session: DbSession) -> None:
        self._session = session

    def for_account(self, account_id: UUID, *, user_id: UUID) -> AccountColumnMapping | None:
        return self._session.scalars(
            select(AccountColumnMapping).from_statement(_FOR_ACCOUNT),
            {"account_id": account_id, "user_id": user_id},
        ).first()

    def remember(
        self, *, user_id: UUID, account_id: UUID, mapping: dict, label: str | None = None
    ) -> AccountColumnMapping:
        existing = self.for_account(account_id, user_id=user_id)
        if existing is not None:
            existing.mapping = mapping
            existing.label = label
            return existing

        row = AccountColumnMapping(
            user_id=user_id, account_id=account_id, mapping=mapping, label=label
        )
        self._session.add(row)
        self._session.flush()
        return row
