"""Month-to-month history: what each month was, what changed, and what the cash did.

The product could show a window of transactions and what one import changed, but not "how
did July compare with June" — the question a person actually asks of their own statements.
This service answers it over whole calendar months, and links each month back to the
uploads its figures were built from, so a figure that moved can be traced to the statement
that moved it.

The arithmetic is in app/domain/monthly.py. This service does what a service does: reads,
applies the sign convention, fills the gaps, and hands whole values to the engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from app.core.db import DbSession
from app.core.errors import ValidationError
from app.domain.monthly import (
    MonthBalance,
    MonthComparison,
    MonthMovement,
    balance_history,
    compare_months,
    month_totals,
)
from app.models.account import AccountType
from app.models.category import CategoryKind
from app.repositories.account import AccountRepository
from app.repositories.transaction import TransactionRepository

_ONE_DAY = timedelta(days=1)

#: The default window. Twelve months is one full seasonal cycle — school fees, December,
#: annual insurance increases — which is the shortest window in which a month can be
#: compared against anything other than its immediate neighbour.
DEFAULT_MONTHS = 12

#: The most months one request will return. A window is a reading, not an export.
MAX_MONTHS = 60

#: Which accounts "cash" means when no account is named. A loan or a vehicle-finance
#: balance is money owed, not money available, and walking it alongside a cheque account
#: would produce a "cash" line that is neither.
CASH_ACCOUNT_TYPES = frozenset({AccountType.TRANSACTIONAL, AccountType.SAVINGS})

#: Category kind to the field it feeds on `MonthTotals`. `TRANSFER` is deliberately absent:
#: both legs of an internal transfer are real rows, and counting them would add to income
#: and spending at once (specs/transactions.md step 4).
_KIND_FIELDS: dict[CategoryKind, str] = {
    CategoryKind.INCOME: "income",
    CategoryKind.ESSENTIAL: "essential",
    CategoryKind.DISCRETIONARY: "discretionary",
    CategoryKind.SAVING: "saving",
    CategoryKind.DEBT: "debt_service",
}


@dataclass(frozen=True, slots=True)
class MonthReport:
    """One month, as the API returns it."""

    comparison: MonthComparison
    #: `None` when the accounts in scope hold no balance to walk — a window over a credit
    #: card alone, for instance. The flows are still real; there is simply no cash line.
    balance: MonthBalance | None
    transaction_count: int
    #: The uploads whose rows fall in this month. Empty for a month made up entirely of
    #: transactions entered by hand.
    import_batch_ids: tuple[str, ...]


class MonthlySummaryService:
    def __init__(self, session: DbSession) -> None:
        self._session = session
        self._transactions = TransactionRepository(session)
        self._accounts = AccountRepository(session)

    def summary(
        self,
        *,
        user_id: UUID,
        since: date | None = None,
        until: date | None = None,
        account_id: UUID | None = None,
        as_of: date | None = None,
    ) -> list[MonthReport]:
        """Every month in the window, each compared against the month before it.

        The comparison for the first month in the window is against the month before the
        window, not against nothing: a window starting in July would otherwise report July
        as having nothing to compare to, although June's figures are sitting in the same
        table. Only the requested months are returned.
        """
        as_of = as_of or date.today()
        window_start, window_end = self._resolve_window(since=since, until=until, as_of=as_of)
        account_ids = self._accounts_in_scope(user_id=user_id, account_id=account_id)

        # One month earlier than asked for, so the first month in the window has a
        # predecessor to be compared against.
        read_from = _add_months(window_start, -1)

        kind_totals = self._transactions.monthly_kind_totals(
            user_id=user_id,
            since=read_from,
            until=window_end,
            account_ids=account_ids,
        )
        batches = self._transactions.monthly_import_batches(
            user_id=user_id,
            since=window_start,
            until=window_end,
            account_ids=account_ids,
        )

        months = _months_between(read_from, window_end)
        totals = {month: self._totals_for(month, kind_totals.get(month, {})) for month in months}

        balances, counts = self._cash(
            user_id=user_id,
            account_ids=account_ids,
            read_from=read_from,
            as_of=as_of,
        )

        reports: list[MonthReport] = []
        for index, month in enumerate(months):
            if index == 0:
                continue  # the extra month read for context, not part of the window
            reports.append(
                MonthReport(
                    comparison=compare_months(
                        current=totals[month], previous=totals[months[index - 1]]
                    ),
                    balance=balances.get(month),
                    transaction_count=counts.get(month, 0),
                    import_batch_ids=batches.get(month, ()),
                )
            )
        return reports

    # ----------------------------------------------------------------------------------
    # Internals
    # ----------------------------------------------------------------------------------
    def _resolve_window(
        self, *, since: date | None, until: date | None, as_of: date
    ) -> tuple[date, date]:
        end = _month_end(until or as_of)
        start = _month_start(since) if since is not None else _add_months(
            _month_start(end), -(DEFAULT_MONTHS - 1)
        )

        if start > end:
            raise ValidationError(
                "'from' is after 'to'.", details={"from": str(start), "to": str(end)}
            )
        if len(_months_between(start, end)) > MAX_MONTHS:
            raise ValidationError(
                f"A window may cover at most {MAX_MONTHS} months.",
                details={"from": str(start), "to": str(end)},
            )
        return start, end

    def _accounts_in_scope(self, *, user_id: UUID, account_id: UUID | None) -> list[UUID]:
        accounts = self._accounts.list_for_user(user_id=user_id)
        if account_id is not None:
            if not any(account.id == account_id for account in accounts):
                raise ValidationError("No account with that identifier exists for this user.")
            return [account_id]
        return [account.id for account in accounts]

    def _totals_for(self, month: str, sums: dict[str, Decimal]):
        """Apply the sign convention, then hand whole values to the engine.

        Income keeps its sign so a reversed salary reduces the month's income; every other
        kind is the positive magnitude that left the account. This mirrors
        `SpendingInsightService._existing_flows` exactly, because the two figures are read
        side by side and a different convention between them would be invisible and wrong.
        """
        fields = {field: Decimal("0") for field in _KIND_FIELDS.values()}
        for kind, field in _KIND_FIELDS.items():
            total = sums.get(kind.value)
            if total is None:
                continue
            fields[field] = total if kind is CategoryKind.INCOME else abs(total)

        return month_totals(month=month, **fields)

    def _cash(
        self,
        *,
        user_id: UUID,
        account_ids: list[UUID],
        read_from: date,
        as_of: date,
    ) -> tuple[dict[str, MonthBalance], dict[str, int]]:
        """The cash line, walked back from what the accounts hold today.

        Read to `as_of` rather than to the end of the window: the balance on an account is
        what it is now, so walking back from it has to account for everything that has
        happened since the window closed. Slicing afterwards is what keeps a window that
        ends in March from being dated by April onwards.
        """
        cash_accounts = [
            account
            for account in self._accounts.list_for_user(user_id=user_id)
            if account.id in set(account_ids) and account.account_type in CASH_ACCOUNT_TYPES
        ]

        movements = self._transactions.monthly_movements(
            user_id=user_id,
            since=read_from,
            until=as_of,
            account_ids=account_ids,
        )
        counts = {month: row.transaction_count for month, row in movements.items()}

        if not cash_accounts:
            return {}, counts

        closing_balance = sum(
            (account.current_balance for account in cash_accounts), Decimal("0")
        )
        cash_movements = self._transactions.monthly_movements(
            user_id=user_id,
            since=read_from,
            until=as_of,
            account_ids=[account.id for account in cash_accounts],
        )

        series = [
            MonthMovement(
                month=month,
                inflow=cash_movements[month].inflow if month in cash_movements else Decimal("0"),
                outflow=cash_movements[month].outflow if month in cash_movements else Decimal("0"),
            )
            for month in _months_between(read_from, as_of)
        ]
        history = balance_history(closing_balance=closing_balance, movements=series)
        return {balance.month: balance for balance in history}, counts


# ---------------------------------------------------------------------------------------
# Calendar helpers
# ---------------------------------------------------------------------------------------
def _month_start(day: date) -> date:
    return day.replace(day=1)


def _month_end(day: date) -> date:
    return _add_months(_month_start(day), 1).replace(day=1) - _ONE_DAY


def _add_months(day: date, months: int) -> date:
    month_index = day.year * 12 + (day.month - 1) + months
    return date(month_index // 12, month_index % 12 + 1, 1)


def _months_between(start: date, end: date) -> list[str]:
    """Every calendar month from `start` to `end`, inclusive, with no gaps.

    Gaps matter: `balance_history` walks consecutive months, and a month with no
    transactions left out of the sequence would silently join two months that are not
    adjacent.
    """
    months: list[str] = []
    cursor = _month_start(start)
    last = _month_start(end)
    while cursor <= last:
        months.append(f"{cursor.year:04d}-{cursor.month:02d}")
        cursor = _add_months(cursor, 1)
    return months
