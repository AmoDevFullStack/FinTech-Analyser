from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, text

from app.core.db import DbSession

from app.models.transaction import Transaction

_BY_ACCOUNT = text(
    """
    SELECT *
      FROM transactions
     WHERE account_id = :account_id
       AND user_id = :user_id
       AND deleted_at IS NULL
       AND (CAST(:since AS date) IS NULL OR occurred_on >= CAST(:since AS date))
       AND (CAST(:until AS date) IS NULL OR occurred_on <= CAST(:until AS date))
       AND (CAST(:category_id AS uuid) IS NULL OR category_id = CAST(:category_id AS uuid))
       AND (CAST(:min_amount AS numeric) IS NULL OR amount >= CAST(:min_amount AS numeric))
       AND (CAST(:max_amount AS numeric) IS NULL OR amount <= CAST(:max_amount AS numeric))
       AND (
         CAST(:q AS text) IS NULL
         OR normalised_description ILIKE CAST(:q AS text)
       )
     ORDER BY occurred_on DESC
     LIMIT :limit
    """
)

_FOR_USER = text(
    """
    SELECT *
      FROM transactions
     WHERE user_id = :user_id
       AND deleted_at IS NULL
       AND (CAST(:since AS date) IS NULL OR occurred_on >= CAST(:since AS date))
       AND (CAST(:until AS date) IS NULL OR occurred_on <= CAST(:until AS date))
     ORDER BY occurred_on DESC
     LIMIT :limit
    """
)

_GET_FOR_USER = text(
    """
    SELECT *
      FROM transactions
     WHERE id = :transaction_id
       AND user_id = :user_id
       AND deleted_at IS NULL
    """
)

_FINGERPRINT_EXISTS = text(
    """
    SELECT id
      FROM transactions
     WHERE user_id = :user_id
       AND fingerprint = :fingerprint
       AND deleted_at IS NULL
     LIMIT 1
    """
)


class TransactionRepository:
    def __init__(self, session: DbSession) -> None:
        self._session = session

    def by_account(
        self,
        account_id: UUID,
        *,
        user_id: UUID,
        since: date | None = None,
        until: date | None = None,
        category_id: UUID | None = None,
        min_amount: Decimal | None = None,
        max_amount: Decimal | None = None,
        q: str | None = None,
        limit: int = 50,
    ) -> list[Transaction]:
        return list(
            self._session.scalars(
                select(Transaction).from_statement(_BY_ACCOUNT),
                {
                    "account_id": account_id,
                    "user_id": user_id,
                    "since": since,
                    "until": until,
                    "category_id": category_id,
                    "min_amount": min_amount,
                    "max_amount": max_amount,
                    "q": f"%{q}%" if q is not None else None,
                    "limit": limit,
                },
            )
        )

    def for_user(
        self,
        *,
        user_id: UUID,
        since: date | None = None,
        until: date | None = None,
        limit: int = 50,
    ) -> list[Transaction]:
        return list(
            self._session.scalars(
                select(Transaction).from_statement(_FOR_USER),
                {"user_id": user_id, "since": since, "until": until, "limit": limit},
            )
        )

    def get_for_user(self, transaction_id: UUID, *, user_id: UUID) -> Transaction | None:
        return self._session.scalars(
            select(Transaction).from_statement(_GET_FOR_USER),
            {"transaction_id": transaction_id, "user_id": user_id},
        ).first()

    def fingerprint_exists(self, fingerprint: str, *, user_id: UUID) -> bool:
        row = self._session.execute(
            _FINGERPRINT_EXISTS, {"user_id": user_id, "fingerprint": fingerprint}
        ).first()
        return row is not None

    def sum_by_account(self, account_id: UUID, *, user_id: UUID) -> Decimal:
        transactions = self.by_account(account_id, user_id=user_id, limit=1_000_000)
        return sum((t.amount for t in transactions), Decimal("0"))

    def add(self, transaction: Transaction) -> Transaction:
        self._session.add(transaction)
        self._session.flush()
        return transaction

    def add_all(self, transactions: list[Transaction]) -> None:
        self._session.add_all(transactions)
        self._session.flush()
