from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, text

from app.core.db import DbSession
from app.domain.payment_taxonomy import PaymentMethod, SpendingPurpose
from app.domain.text_match import rank_matches
from app.models.transaction import Direction, Transaction

_BY_ACCOUNT = text(
    """
    SELECT *
      FROM ledger.transactions
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
      FROM ledger.transactions
     WHERE user_id = :user_id
       AND deleted_at IS NULL
       AND (CAST(:since AS date) IS NULL OR occurred_on >= CAST(:since AS date))
       AND (CAST(:until AS date) IS NULL OR occurred_on <= CAST(:until AS date))
     ORDER BY occurred_on DESC
     LIMIT :limit
    """
)

# One statement behind every filtered list. Every predicate is null-guarded, so an omitted
# filter costs a constant-folded `NULL IS NULL` rather than a separate query per
# combination of filters — the alternative is sixteen near-identical statements that drift.
#
# Enum columns are compared as text: the driver binds a Python string, and Postgres will
# not compare `text` to an enum type without an explicit cast on one side. Casting the
# column rather than the parameter keeps the parameter a plain string, which is what makes
# the null-guard above it work.
_SEARCH = text(
    """
    SELECT *
      FROM ledger.transactions
     WHERE user_id = :user_id
       AND deleted_at IS NULL
       AND (CAST(:account_id AS uuid) IS NULL OR account_id = CAST(:account_id AS uuid))
       AND (CAST(:since AS date) IS NULL OR occurred_on >= CAST(:since AS date))
       AND (CAST(:until AS date) IS NULL OR occurred_on <= CAST(:until AS date))
       AND (CAST(:category_id AS uuid) IS NULL OR category_id = CAST(:category_id AS uuid))
       AND (CAST(:min_amount AS numeric) IS NULL OR amount >= CAST(:min_amount AS numeric))
       AND (CAST(:max_amount AS numeric) IS NULL OR amount <= CAST(:max_amount AS numeric))
       AND (CAST(:direction AS text) IS NULL OR direction::text = CAST(:direction AS text))
       AND (
         CAST(:payment_method AS text) IS NULL
         OR payment_method::text = CAST(:payment_method AS text)
       )
       AND (
         CAST(:spending_purpose AS text) IS NULL
         OR spending_purpose::text = CAST(:spending_purpose AS text)
       )
       AND (
         CAST(:is_recurring AS boolean) IS NULL
         OR is_recurring = CAST(:is_recurring AS boolean)
       )
       AND (NOT CAST(:uncategorised_only AS boolean) OR category_id IS NULL)
       AND (
         CAST(:q AS text) IS NULL
         OR normalised_description ILIKE CAST(:q AS text)
         OR description ILIKE CAST(:q AS text)
         OR merchant ILIKE CAST(:q AS text)
       )
     ORDER BY occurred_on DESC, created_at DESC
     LIMIT :limit
    """
)

_GET_FOR_USER = text(
    """
    SELECT *
      FROM ledger.transactions
     WHERE id = :transaction_id
       AND user_id = :user_id
       AND deleted_at IS NULL
    """
)

_FINGERPRINT_EXISTS = text(
    """
    SELECT id
      FROM ledger.transactions
     WHERE user_id = :user_id
       AND fingerprint = :fingerprint
       AND deleted_at IS NULL
     LIMIT 1
    """
)

# Aggregates by calendar month. These are grouped in Postgres rather than by reading rows
# and summing in Python: a month-by-month view over three years is a few dozen rows out of
# tens of thousands, and pulling all of them across to add them up is the one place this
# repository would be paying for a comfortable API in seconds.
#
# `date_trunc('month', occurred_on)` groups on the date the bank reported, never on
# `created_at` — importing March's statement in July does not make those transactions July's
# (docs/database.md §1, dates versus timestamps).

_ACTIVITY_SPAN = text(
    """
    SELECT MIN(occurred_on) AS first_on,
           MAX(occurred_on) AS last_on,
           COUNT(DISTINCT date_trunc('month', occurred_on)) AS months_with_activity,
           COUNT(*) AS transaction_count
      FROM ledger.transactions
     WHERE user_id = :user_id
       AND deleted_at IS NULL
    """
)

_MONTHLY_KIND_TOTALS = text(
    """
    SELECT to_char(date_trunc('month', t.occurred_on), 'YYYY-MM') AS month,
           c.kind::text AS kind,
           SUM(t.amount) AS total
      FROM ledger.transactions t
      JOIN ledger.categories c ON c.id = t.category_id
     WHERE t.user_id = :user_id
       AND t.deleted_at IS NULL
       AND t.transfer_group_id IS NULL
       AND (CAST(:since AS date) IS NULL OR t.occurred_on >= CAST(:since AS date))
       AND (CAST(:until AS date) IS NULL OR t.occurred_on <= CAST(:until AS date))
       AND (
         CAST(:account_ids AS uuid[]) IS NULL
         OR t.account_id = ANY(CAST(:account_ids AS uuid[]))
       )
     GROUP BY 1, 2
     ORDER BY 1, 2
    """
)

_MONTHLY_MOVEMENTS = text(
    """
    SELECT to_char(date_trunc('month', occurred_on), 'YYYY-MM') AS month,
           COALESCE(SUM(amount) FILTER (WHERE amount > 0), 0) AS inflow,
           COALESCE(-SUM(amount) FILTER (WHERE amount < 0), 0) AS outflow,
           COUNT(*) AS transaction_count
      FROM ledger.transactions
     WHERE user_id = :user_id
       AND deleted_at IS NULL
       AND (CAST(:since AS date) IS NULL OR occurred_on >= CAST(:since AS date))
       AND (CAST(:until AS date) IS NULL OR occurred_on <= CAST(:until AS date))
       AND (
         CAST(:account_ids AS uuid[]) IS NULL
         OR account_id = ANY(CAST(:account_ids AS uuid[]))
       )
     GROUP BY 1
     ORDER BY 1
    """
)

_MONTHLY_IMPORT_BATCHES = text(
    """
    SELECT to_char(date_trunc('month', occurred_on), 'YYYY-MM') AS month,
           ARRAY_AGG(DISTINCT import_batch_id::text) AS batch_ids
      FROM ledger.transactions
     WHERE user_id = :user_id
       AND deleted_at IS NULL
       AND import_batch_id IS NOT NULL
       AND (CAST(:since AS date) IS NULL OR occurred_on >= CAST(:since AS date))
       AND (CAST(:until AS date) IS NULL OR occurred_on <= CAST(:until AS date))
       AND (
         CAST(:account_ids AS uuid[]) IS NULL
         OR account_id = ANY(CAST(:account_ids AS uuid[]))
       )
     GROUP BY 1
     ORDER BY 1
    """
)

# How many rows a fuzzy search reads before ranking. Edit distance cannot be pushed into
# the query without the `fuzzystrmatch` or `pg_trgm` extension, which this deployment does
# not require, so the ranking happens in Python over a bounded window. 5,000 rows is
# roughly four years of a busy transactional account, is read date-descending so the window
# is the recent history a search is nearly always about, and costs single-digit
# milliseconds to rank.
FUZZY_SCAN_LIMIT = 5_000


@dataclass(frozen=True, slots=True)
class TransactionMatch:
    """A transaction and why it came back from a search.

    `score` is 1 for a substring hit and the edit-distance similarity otherwise; `basis`
    is "exact", "fuzzy", or "filter" for a row that matched the filters with no search term
    at all. The client renders the difference, because "contains what you typed" and "looks
    like what you typed" are different claims and a user deciding whether a result is
    relevant needs to know which one they are being shown.
    """

    transaction: Transaction
    score: Decimal
    basis: str


@dataclass(frozen=True, slots=True)
class ActivitySpan:
    """What transaction history a user actually has.

    Every monthly figure in this product is derived from transactions, so "how far back do
    these go, and how many months of them are there" is the honest measure of how much a
    figure can be trusted — and the only way a reader can tell a settled picture from one
    built on three weeks of data.
    """

    first_on: date | None
    last_on: date | None
    months_with_activity: int
    transaction_count: int

    @property
    def has_history(self) -> bool:
        return self.last_on is not None


@dataclass(frozen=True, slots=True)
class MonthlyMovementRow:
    """One month of cash across the accounts in scope, transfers included.

    `inflow` and `outflow` are both positive magnitudes, which is what
    `app.domain.monthly.MonthMovement` expects — the query does the sign flip so no caller
    has to remember it.
    """

    month: str
    inflow: Decimal
    outflow: Decimal
    transaction_count: int


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

    def search(
        self,
        *,
        user_id: UUID,
        account_id: UUID | None = None,
        since: date | None = None,
        until: date | None = None,
        category_id: UUID | None = None,
        min_amount: Decimal | None = None,
        max_amount: Decimal | None = None,
        direction: Direction | None = None,
        payment_method: PaymentMethod | None = None,
        spending_purpose: SpendingPurpose | None = None,
        is_recurring: bool | None = None,
        uncategorised_only: bool = False,
        q: str | None = None,
        fuzzy: bool = True,
        min_score: Decimal = Decimal("0.62"),
        limit: int = 50,
    ) -> list[TransactionMatch]:
        """Filtered transaction search, optionally matching descriptions by edit distance.

        Without `q`, this is the filtered list and every row comes back with basis
        "filter".

        With `q` and `fuzzy=False`, matching is the SQL `ILIKE` it has always been.

        With `q` and `fuzzy=True` — the default — the SQL predicate is dropped and up to
        FUZZY_SCAN_LIMIT of the user's most recent rows are ranked in Python against the
        query by `app.domain.text_match.rank_matches`. A substring hit still scores 1 and
        still sorts first; below that, "woolwrths" finds the Woolworths rows and "capitec
        eft nadai" finds the payment to Nadia. Without this, a search only finds
        descriptions the user can already spell exactly as their bank does, which for a
        statement line like "POS PURCH 4471 WW CLAREMNT" is nobody.

        Fuzzy results are ordered by score first and date second, so the best match leads
        even when it is the oldest; filtered and exact-only results stay in date order,
        which is what a list with no search term is expected to be.
        """
        wants_fuzzy = fuzzy and bool(q and q.strip())
        params = {
            "user_id": user_id,
            "account_id": account_id,
            "since": since,
            "until": until,
            "category_id": category_id,
            "min_amount": min_amount,
            "max_amount": max_amount,
            "direction": direction.value if direction is not None else None,
            "payment_method": payment_method.value if payment_method is not None else None,
            "spending_purpose": (
                spending_purpose.value if spending_purpose is not None else None
            ),
            "is_recurring": is_recurring,
            "uncategorised_only": uncategorised_only,
            # The text predicate is deliberately not applied for a fuzzy search: a row
            # whose description merely resembles the query would be filtered out here
            # before it could ever be ranked.
            "q": None if wants_fuzzy or not q else f"%{q}%",
            "limit": FUZZY_SCAN_LIMIT if wants_fuzzy else limit,
        }
        rows = list(
            self._session.scalars(select(Transaction).from_statement(_SEARCH), params)
        )

        if not wants_fuzzy:
            basis = "exact" if q else "filter"
            score = Decimal("1.000000")
            return [TransactionMatch(row, score, basis) for row in rows[:limit]]

        assert q is not None
        by_id = {str(row.id): row for row in rows}
        candidates = {
            str(row.id): " ".join(
                part
                for part in (row.normalised_description, row.merchant, row.description)
                if part
            )
            for row in rows
        }
        ranked = rank_matches(query=q, candidates=candidates, threshold=min_score)
        return [
            TransactionMatch(by_id[match.key], match.score, match.basis)
            for match in ranked[:limit]
        ]

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

    # ----------------------------------------------------------------------------------
    # Monthly aggregates
    # ----------------------------------------------------------------------------------
    def activity_span(self, *, user_id: UUID) -> ActivitySpan:
        """The first and last transaction dates, and how many months carry any.

        One row, computed in Postgres. The alternative — reading the transactions to find
        out how many there are — is the shape of query this repository exists to avoid.
        """
        row = self._session.execute(_ACTIVITY_SPAN, {"user_id": user_id}).one()
        return ActivitySpan(
            first_on=row.first_on,
            last_on=row.last_on,
            months_with_activity=int(row.months_with_activity or 0),
            transaction_count=int(row.transaction_count or 0),
        )

    def monthly_kind_totals(
        self,
        *,
        user_id: UUID,
        since: date | None = None,
        until: date | None = None,
        account_ids: list[UUID] | None = None,
    ) -> dict[str, dict[str, Decimal]]:
        """`{"2026-07": {"income": ..., "essential": ...}}`, transfers excluded.

        Sums are raw: income arrives positive, spending negative, exactly as stored. The
        caller applies the sign convention, because it is the caller that knows which view
        it is building — see app/domain/monthly.py.

        Uncategorised transactions are not counted. An inner join is deliberate: a row with
        no category has no kind, and putting it in a bucket would be a guess presented as a
        figure. `GET /transactions?uncategorised_only=true` is where those are dealt with.
        """
        rows = self._session.execute(
            _MONTHLY_KIND_TOTALS,
            {
                "user_id": user_id,
                "since": since,
                "until": until,
                "account_ids": [str(account_id) for account_id in account_ids]
                if account_ids is not None
                else None,
            },
        ).all()

        totals: dict[str, dict[str, Decimal]] = defaultdict(dict)
        for row in rows:
            totals[row.month][row.kind] = Decimal(row.total)
        return dict(totals)

    def monthly_movements(
        self,
        *,
        user_id: UUID,
        since: date | None = None,
        until: date | None = None,
        account_ids: list[UUID] | None = None,
    ) -> dict[str, MonthlyMovementRow]:
        """Every transaction that touched the account, per month — transfers included.

        This is the cash view, and it is a different question from `monthly_kind_totals`.
        A transfer is not income and not spending, but it did leave the account it left,
        and a balance that ignores it does not reconcile to a statement.
        """
        rows = self._session.execute(
            _MONTHLY_MOVEMENTS,
            {
                "user_id": user_id,
                "since": since,
                "until": until,
                "account_ids": [str(account_id) for account_id in account_ids]
                if account_ids is not None
                else None,
            },
        ).all()

        return {
            row.month: MonthlyMovementRow(
                month=row.month,
                inflow=Decimal(row.inflow),
                outflow=Decimal(row.outflow),
                transaction_count=int(row.transaction_count),
            )
            for row in rows
        }

    def monthly_import_batches(
        self,
        *,
        user_id: UUID,
        since: date | None = None,
        until: date | None = None,
        account_ids: list[UUID] | None = None,
    ) -> dict[str, tuple[str, ...]]:
        """Which uploads a month's figures were built from.

        The traceability half of the month view: a user looking at a month that changed
        should be able to get from the figure back to the statement it came from.
        """
        rows = self._session.execute(
            _MONTHLY_IMPORT_BATCHES,
            {
                "user_id": user_id,
                "since": since,
                "until": until,
                "account_ids": [str(account_id) for account_id in account_ids]
                if account_ids is not None
                else None,
            },
        ).all()
        return {row.month: tuple(row.batch_ids) for row in rows}
