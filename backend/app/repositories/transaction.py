from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from app.core.db import DbSession

from app.models.transaction import Transaction


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
        stmt = select(Transaction).where(
            Transaction.account_id == account_id,
            Transaction.user_id == user_id,
            Transaction.deleted_at.is_(None),
        )
        if since is not None:
            stmt = stmt.where(Transaction.occurred_on >= since)
        if until is not None:
            stmt = stmt.where(Transaction.occurred_on <= until)
        if category_id is not None:
            stmt = stmt.where(Transaction.category_id == category_id)
        if min_amount is not None:
            stmt = stmt.where(Transaction.amount >= min_amount)
        if max_amount is not None:
            stmt = stmt.where(Transaction.amount <= max_amount)
        if q is not None:
            stmt = stmt.where(Transaction.normalised_description.ilike(f"%{q}%"))
        stmt = stmt.order_by(Transaction.occurred_on.desc()).limit(limit)
        return list(self._session.scalars(stmt))

    def for_user(
        self,
        *,
        user_id: UUID,
        since: date | None = None,
        until: date | None = None,
        limit: int = 50,
    ) -> list[Transaction]:
        stmt = select(Transaction).where(
            Transaction.user_id == user_id, Transaction.deleted_at.is_(None)
        )
        if since is not None:
            stmt = stmt.where(Transaction.occurred_on >= since)
        if until is not None:
            stmt = stmt.where(Transaction.occurred_on <= until)
        stmt = stmt.order_by(Transaction.occurred_on.desc()).limit(limit)
        return list(self._session.scalars(stmt))

    def fingerprint_exists(self, fingerprint: str, *, user_id: UUID) -> bool:
        stmt = select(Transaction.id).where(
            Transaction.user_id == user_id,
            Transaction.fingerprint == fingerprint,
            Transaction.deleted_at.is_(None),
        )
        return self._session.scalars(stmt).first() is not None

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
