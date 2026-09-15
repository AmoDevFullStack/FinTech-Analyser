"""Recurring series detection over a user's transaction history.

See specs/transactions.md step 6. This service groups transactions and persists the
detection result onto them; `app/domain/recurrence.py` decides what is and is not a
series. Transfers are excluded before grouping — both legs of an internal transfer repeat
perfectly regularly and would otherwise detect as the strongest "commitment" a user has.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from app.core.db import DbSession
from app.core.ids import uuid7
from app.domain.recurrence import Occurrence, RecurringSeries, detect_all, upcoming_occurrences
from app.models.category import CategoryKind
from app.models.transaction import Transaction
from app.repositories.category import CategoryRepository
from app.repositories.transaction import TransactionRepository

HISTORY_LIMIT = 10_000


@dataclass(frozen=True, slots=True)
class SeriesView:
    """A detected series plus the bookkeeping the domain engine has no business knowing:
    which stored transactions it covers, and what kind of spending it is.
    """

    series: RecurringSeries
    transaction_ids: list[UUID]
    category_id: UUID | None
    category_kind: CategoryKind | None


class RecurrenceService:
    def __init__(self, session: DbSession) -> None:
        self._session = session
        self._transactions = TransactionRepository(session)
        self._categories = CategoryRepository(session)

    def _history(self, *, user_id: UUID) -> list[Transaction]:
        return [
            txn
            for txn in self._transactions.for_user(user_id=user_id, limit=HISTORY_LIMIT)
            if txn.transfer_group_id is None and txn.deleted_at is None
        ]

    def detect(self, *, user_id: UUID) -> list[SeriesView]:
        """Detect every recurring series in the user's history, without persisting."""
        history = self._history(user_id=user_id)
        by_description: dict[str, list[Transaction]] = defaultdict(list)
        for txn in history:
            by_description[txn.normalised_description].append(txn)

        groups = {
            description: [
                Occurrence(occurred_on=t.occurred_on, amount=t.amount) for t in rows
            ]
            for description, rows in by_description.items()
        }
        kinds = {c.id: c.kind for c in self._categories.list_for_user(user_id=user_id)}

        views = []
        for series in detect_all(groups=groups):
            rows = by_description[series.key]
            category_id = next((t.category_id for t in rows if t.category_id), None)
            views.append(
                SeriesView(
                    series=series,
                    transaction_ids=[t.id for t in rows],
                    category_id=category_id,
                    category_kind=kinds.get(category_id) if category_id else None,
                )
            )
        return views

    def apply(self, *, user_id: UUID) -> int:
        """Detect series and stamp `is_recurring`/`recurrence_group_id` onto their rows.

        A series keeps whatever group id its transactions already carry, so a re-run after
        a later import extends the existing series rather than renaming it. Rows that are
        no longer part of any series (a standing order cancelled, leaving gaps that break
        the interval test) have the flag cleared, or the projection keeps treating a dead
        commitment as live.
        """
        history = self._history(user_id=user_id)
        by_description: dict[str, list[Transaction]] = defaultdict(list)
        for txn in history:
            by_description[txn.normalised_description].append(txn)

        recurring_ids: set[UUID] = set()
        for view in self.detect(user_id=user_id):
            rows = by_description[view.series.key]
            group_id = next(
                (t.recurrence_group_id for t in rows if t.recurrence_group_id), uuid7()
            )
            for txn in rows:
                txn.is_recurring = True
                txn.recurrence_group_id = group_id
                recurring_ids.add(txn.id)

        for txn in history:
            if txn.id not in recurring_ids and txn.is_recurring:
                txn.is_recurring = False
                txn.recurrence_group_id = None

        return len(recurring_ids)

    def upcoming(self, *, user_id: UUID, from_date: date, days_ahead: int = 30) -> list[dict]:
        """Expected occurrences of every detected series inside the window.

        Outflows only: what the dashboard's "what is coming" region asks is what money
        must leave, not when the salary lands.
        """
        views = self.detect(user_id=user_id)
        outflows = [v for v in views if v.series.median_amount < 0]
        by_key = {v.series.key: v for v in outflows}

        expected = upcoming_occurrences(
            [v.series for v in outflows], from_date=from_date, days_ahead=days_ahead
        )
        return [
            {
                "label": series.key,
                "amount": str(abs(series.median_amount)),
                "due_on": due.isoformat(),
                "source": "recurring_series",
                "category_id": (
                    str(by_key[series.key].category_id)
                    if by_key[series.key].category_id
                    else None
                ),
            }
            for series, due in expected
        ]
