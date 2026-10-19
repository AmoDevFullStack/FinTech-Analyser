"""What an import or a single entry was, and what it changes. See specs/transactions.md.

Three questions this answers, in the order a user asks them:

  1. **What was this payment for?** — the spending purpose, from
     `app/domain/payment_taxonomy.py`: rent, groceries, a medical aid premium, a loan
     instalment.
  2. **What type of payment was it?** — the method: a debit order, a card swipe, an ATM
     withdrawal, an EFT. Separate from the purpose, because it is the evidence about
     whether the payment recurs.
  3. **What does it do to my money?** — the effect on monthly cash flow and on every figure
     derived from it, computed by `app/domain/spending_impact.py` and reported before the
     import is committed as well as after.

Detection runs at **staging**, not at commit. The preview a user approves is therefore
built from the same classification the committed rows carry; classifying twice would let
the two disagree, and the number the user agreed to would not be the number they got.

On the monthly window: a statement covering six months adds six months of rent, and
charging all of it to one month would report a cash-flow collapse that did not happen.
Both sides of the comparison are averaged over the calendar months the file actually spans,
so the answer reads "over the months this file covers, your monthly essential spending goes
from X to Y" — which is the question, rather than "your January is ruined".
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from app.core.db import DbSession
from app.core.events import TRANSACTIONS_RECLASSIFIED, dispatch_pending, record
from app.core.errors import NotFoundError
from app.domain.payment_taxonomy import (
    PURPOSE_KIND,
    PaymentMethod,
    SpendingPurpose,
    classify_payment,
)
from app.domain.spending_impact import MonthlyFlows, SpendingImpact, spending_impact
from app.models.category import Category, CategoryKind
from app.models.import_batch import StagedTransaction
from app.models.transaction import Transaction
from app.repositories.account import AccountRepository
from app.repositories.category import CategoryRepository
from app.repositories.import_batch import ImportBatchRepository
from app.repositories.transaction import TransactionRepository
from app.services.categorisation import CategorisationService

CENTS = Decimal("0.01")
HISTORY_LIMIT = 100_000

LIQUID_ACCOUNT_TYPES = ("transactional", "savings")


def _to_cents(value: Decimal) -> Decimal:
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)


def _month_key(day: date) -> tuple[int, int]:
    return (day.year, day.month)


@dataclass(frozen=True, slots=True)
class DetectedRow:
    """One statement line, read.

    `category_id` is what categorisation chose for it, which is not always the purpose's
    own category — a user correction outranks the shipped taxonomy, so a row detected as
    groceries can legitimately be filed under whatever that user calls it. Both are
    reported so the difference is visible rather than silently reconciled.
    """

    description: str
    merchant: str | None
    occurred_on: date
    amount: Decimal
    payment_method: PaymentMethod
    spending_purpose: SpendingPurpose
    kind: CategoryKind | None
    purpose_confidence: Decimal
    category_id: UUID | None
    category_name: str | None
    category_basis: str
    is_duplicate: bool
    needs_review: bool


@dataclass(frozen=True, slots=True)
class GroupTotal:
    """Total and count for one purpose or one method, over the whole batch."""

    key: str
    label: str
    total: Decimal
    monthly_average: Decimal
    count: int


@dataclass(frozen=True, slots=True)
class Commitment:
    """A payment whose method says it will happen again whether or not the user decides to.

    Recurrence detection (specs/transactions.md step 6) needs three occurrences before it
    will call something a series, which is right — three points is the minimum that
    establishes an interval. But a debit order is a standing arrangement on its first
    appearance, and a preview that cannot say "this file adds a R14,500 monthly commitment"
    until the third month of statements is withholding the most important thing in the file.
    This is the method-level signal, reported as what it is: a commitment implied by the
    payment type, not a detected series.
    """

    label: str
    merchant: str | None
    method: PaymentMethod
    purpose: SpendingPurpose
    monthly_amount: Decimal
    occurrences: int
    is_new: bool


@dataclass(frozen=True, slots=True)
class AffectedArea:
    """One thing downstream of this import that no longer reflects reality, and why."""

    area: str
    effect: str
    detail: str


@dataclass(frozen=True, slots=True)
class SpendingInsight:
    """The full answer for one batch, or for one transaction being previewed."""

    months_covered: int
    period_start: date | None
    period_end: date | None
    rows: tuple[DetectedRow, ...]
    by_purpose: tuple[GroupTotal, ...]
    by_method: tuple[GroupTotal, ...]
    commitments: tuple[Commitment, ...]
    impact: SpendingImpact
    affected: tuple[AffectedArea, ...]
    rows_needing_review: int


class SpendingInsightService:
    def __init__(self, session: DbSession) -> None:
        self._session = session
        self._accounts = AccountRepository(session)
        self._transactions = TransactionRepository(session)
        self._categories = CategoryRepository(session)
        self._batches = ImportBatchRepository(session)
        self._categorisation = CategorisationService(session)

    # ----------------------------------------------------------------------------------
    # Detection
    # ----------------------------------------------------------------------------------
    def classify_transaction(self, transaction: Transaction) -> None:
        """Stamp detection onto a transaction in memory. The caller commits."""
        classification = classify_payment(
            description=transaction.normalised_description or transaction.description,
            amount=transaction.amount,
        )
        transaction.payment_method = classification.method
        transaction.spending_purpose = classification.purpose
        transaction.merchant = classification.merchant
        transaction.purpose_confidence = classification.purpose_confidence

    def reclassify_history(self, *, user_id: UUID) -> int:
        """Re-run detection over every one of a user's transactions.

        The explicit path the 0013 migration deliberately does not take. Detection rules
        change; rewriting a user's history as a side effect of deploying a new rule table
        would move figures with no record of why, so it happens only when someone asks for
        it. Categories are untouched: this rewrites what the statement said, never what the
        user decided it meant.
        """
        rows = self._transactions.for_user(user_id=user_id, limit=HISTORY_LIMIT)
        for transaction in rows:
            self.classify_transaction(transaction)
        # Reclassification moves the essential/discretionary split, which every downstream
        # figure is built on. Recording it as an event means it recomputes the same things
        # an import does, rather than leaving a user looking at a health score computed
        # against the classification they just replaced.
        record(
            self._session,
            user_id=user_id,
            name=TRANSACTIONS_RECLASSIFIED,
            payload={"transactions_reclassified": len(rows)},
        )
        self._session.commit()

        dispatch_pending(self._session, user_id=user_id)
        return len(rows)

    # ----------------------------------------------------------------------------------
    # Impact
    # ----------------------------------------------------------------------------------
    def preview_batch(self, batch_id: UUID, *, user_id: UUID) -> SpendingInsight:
        """What this staged batch was, and what committing it would change.

        Only rows that would actually be written are counted: an exact duplicate is skipped
        at commit and a row the user resolved as "skip" or "merge" does not add a new
        transaction, so neither belongs in a figure describing what the commit adds. They
        still appear in `rows`, flagged, because "we found and ignored eleven duplicates" is
        the reassurance the import flow exists to provide.
        """
        batch = self._batches.get_for_user(batch_id, user_id=user_id)
        if batch is None:
            raise NotFoundError("No import batch with that identifier exists for this user.")

        staged = self._batches.staged_for(batch_id)
        return self._build(
            user_id=user_id,
            account_id=batch.account_id,
            staged=staged,
            is_preview=True,
            exclude_batch_id=batch_id,
        )

    def insight_for_transactions(
        self,
        *,
        user_id: UUID,
        account_id: UUID,
        transactions: list[Transaction],
        exclude_batch_id: UUID | None = None,
    ) -> SpendingInsight:
        """The same report, for rows that have already been written.

        Used by the commit response, so what a user is told after the import is the same
        shape as what they were shown before it, and by manual single-transaction entry.
        """
        staged = [
            StagedTransaction(
                import_batch_id=txn.import_batch_id or account_id,
                occurred_on=txn.occurred_on,
                amount=txn.amount,
                description=txn.description,
                normalised_description=txn.normalised_description,
                fingerprint=txn.fingerprint,
                is_exact_duplicate=False,
                payment_method=txn.payment_method,
                spending_purpose=txn.spending_purpose,
                merchant=txn.merchant,
                purpose_confidence=txn.purpose_confidence,
                raw_row={},
            )
            for txn in transactions
        ]
        return self._build(
            user_id=user_id,
            account_id=account_id,
            staged=staged,
            is_preview=False,
            exclude_batch_id=exclude_batch_id,
        )

    # ----------------------------------------------------------------------------------
    # Internals
    # ----------------------------------------------------------------------------------
    def _build(
        self,
        *,
        user_id: UUID,
        account_id: UUID,
        staged: list[StagedTransaction],
        is_preview: bool,
        exclude_batch_id: UUID | None,
    ) -> SpendingInsight:
        categories = self._categories.list_for_user(user_id=user_id)
        corrections = self._categorisation.corrected_history(user_id=user_id)
        by_category_id = {c.id: c for c in categories}

        importable = [
            row
            for row in staged
            if not row.is_exact_duplicate and row.resolution not in ("skip", "merge")
        ]
        months = sorted({_month_key(row.occurred_on) for row in importable})
        months_covered = max(len(months), 1)
        period_start = min((r.occurred_on for r in importable), default=None)
        period_end = max((r.occurred_on for r in importable), default=None)

        detected = tuple(
            self._detect_row(
                row,
                categories=categories,
                corrections=corrections,
                by_category_id=by_category_id,
            )
            for row in staged
        )
        detected_importable = tuple(
            row
            for row, staged_row in zip(detected, staged, strict=True)
            if not staged_row.is_exact_duplicate
            and staged_row.resolution not in ("skip", "merge")
        )

        added = self._flows_from_detected(detected_importable, months=months_covered)
        before = self._existing_flows(
            user_id=user_id, months=months, exclude_batch_id=exclude_batch_id
        )
        liquid = self._liquid_savings(user_id=user_id)
        # The liquid balance itself does not move on an import: an imported transaction is a
        # record of money that already moved, and the account's stored balance is either
        # manual (the user's own figure) or already derived from the transactions being
        # added. Reporting it unchanged on both sides is what makes the emergency-fund line
        # readable — its movement there comes entirely from the change in essential
        # spending, which is the point being made.
        impact = spending_impact(
            before=before,
            added=added,
            liquid_savings_before=liquid,
            liquid_savings_after=liquid,
        )

        return SpendingInsight(
            months_covered=months_covered,
            period_start=period_start,
            period_end=period_end,
            rows=detected,
            by_purpose=self._group_by_purpose(detected_importable, months=months_covered),
            by_method=self._group_by_method(detected_importable, months=months_covered),
            commitments=self._commitments(
                detected_importable, user_id=user_id, months=months_covered
            ),
            impact=impact,
            affected=self._affected(
                account_id=account_id, impact=impact, is_preview=is_preview
            ),
            rows_needing_review=sum(1 for row in detected_importable if row.needs_review),
        )

    def _detect_row(
        self,
        row: StagedTransaction,
        *,
        categories: list[Category],
        corrections: dict[str, UUID],
        by_category_id: dict[UUID, Category],
    ) -> DetectedRow:
        method = row.payment_method
        purpose = row.spending_purpose
        confidence = row.purpose_confidence
        merchant = row.merchant
        if method is None or purpose is None:
            # A row staged before detection existed, or one built in memory for the
            # post-commit report. Classifying here rather than assuming keeps the two
            # entry points returning the same thing.
            classification = classify_payment(
                description=row.normalised_description or row.description, amount=row.amount
            )
            method = classification.method
            purpose = classification.purpose
            confidence = classification.purpose_confidence
            merchant = classification.merchant

        suggestion = self._categorisation.suggest(
            normalised_description=row.normalised_description,
            categories=categories,
            corrections=corrections,
            amount=row.amount,
        )
        category = suggestion.category
        kind = category.kind if category is not None else self._kind_for_purpose(purpose)

        return DetectedRow(
            description=row.description,
            merchant=merchant,
            occurred_on=row.occurred_on,
            amount=row.amount,
            payment_method=method,
            spending_purpose=purpose,
            kind=kind,
            purpose_confidence=confidence if confidence is not None else Decimal("0.000000"),
            category_id=category.id if category is not None else None,
            category_name=category.name if category is not None else None,
            category_basis=suggestion.basis,
            is_duplicate=row.is_exact_duplicate,
            # Two ways a row earns a look: nothing recognised it, or what recognised it was
            # the low-confidence fallback. Both produce a figure that will be wrong in a way
            # that looks right, which is the failure specs/transactions.md opens by naming.
            needs_review=(
                purpose is SpendingPurpose.UNKNOWN
                or suggestion.basis in ("default", "none")
            ),
        )

    @staticmethod
    def _kind_for_purpose(purpose: SpendingPurpose) -> CategoryKind | None:
        spend_kind = PURPOSE_KIND.get(purpose)
        return CategoryKind(spend_kind.value) if spend_kind is not None else None

    @staticmethod
    def _flows_from_detected(
        rows: tuple[DetectedRow, ...], *, months: int
    ) -> MonthlyFlows:
        """Per-month averages of what these rows add, grouped by kind.

        Signs follow `PositionService.category_kind_sums` exactly, because the two figures
        are added together: income keeps its sign so a salary reversal reduces income, and
        every other kind is reported as the positive magnitude that left the account.
        Transfers contribute to nothing — both legs of an internal transfer repeat perfectly
        and counting them would inflate income and spending at once, which is the corruption
        specs/transactions.md step 4 exists to prevent.
        """
        totals: dict[CategoryKind, Decimal] = defaultdict(lambda: Decimal("0"))
        for row in rows:
            if row.kind is None or row.kind is CategoryKind.TRANSFER:
                continue
            if row.kind is CategoryKind.INCOME:
                totals[row.kind] += row.amount
            else:
                totals[row.kind] += -row.amount if row.amount < 0 else row.amount

        divisor = Decimal(max(months, 1))
        return MonthlyFlows(
            income=_to_cents(totals[CategoryKind.INCOME] / divisor),
            essential=_to_cents(totals[CategoryKind.ESSENTIAL] / divisor),
            discretionary=_to_cents(totals[CategoryKind.DISCRETIONARY] / divisor),
            saving=_to_cents(totals[CategoryKind.SAVING] / divisor),
            debt_service=_to_cents(totals[CategoryKind.DEBT] / divisor),
        )

    def _existing_flows(
        self, *, user_id: UUID, months: list[tuple[int, int]], exclude_batch_id: UUID | None
    ) -> MonthlyFlows:
        """The user's monthly averages over the same calendar months the file covers.

        Comparing against a different window would produce a delta that is mostly the
        difference between two periods rather than the effect of the import.

        `exclude_batch_id` is what makes the report correct when it runs *after* the commit:
        the rows this import just wrote are already in the table by then, and counting them
        on the "before" side too would report every import as changing nothing.
        """
        if not months:
            months = [_month_key(date.today())]

        kind_by_category: dict[UUID, CategoryKind] = {
            c.id: c.kind for c in self._categories.list_for_user(user_id=user_id)
        }
        wanted = set(months)
        totals: dict[CategoryKind, Decimal] = defaultdict(lambda: Decimal("0"))

        for txn in self._transactions.for_user(user_id=user_id, limit=HISTORY_LIMIT):
            if _month_key(txn.occurred_on) not in wanted:
                continue
            if txn.transfer_group_id is not None or txn.category_id is None:
                continue
            if exclude_batch_id is not None and txn.import_batch_id == exclude_batch_id:
                continue
            kind = kind_by_category.get(txn.category_id)
            if kind is None or kind is CategoryKind.TRANSFER:
                continue
            if kind is CategoryKind.INCOME:
                totals[kind] += txn.amount
            else:
                totals[kind] += -txn.amount if txn.amount < 0 else txn.amount

        divisor = Decimal(len(wanted))
        return MonthlyFlows(
            income=_to_cents(totals[CategoryKind.INCOME] / divisor),
            essential=_to_cents(totals[CategoryKind.ESSENTIAL] / divisor),
            discretionary=_to_cents(totals[CategoryKind.DISCRETIONARY] / divisor),
            saving=_to_cents(totals[CategoryKind.SAVING] / divisor),
            debt_service=_to_cents(totals[CategoryKind.DEBT] / divisor),
        )

    def _liquid_savings(self, *, user_id: UUID) -> Decimal:
        total = sum(
            (
                account.current_balance
                for account in self._accounts.list_for_user(user_id=user_id)
                if account.account_type.value in LIQUID_ACCOUNT_TYPES
            ),
            Decimal("0"),
        )
        # `emergency_fund_months` rejects a negative balance, and an overdrawn cheque
        # account is a real state. Nought months of cover is the honest reading of it.
        return max(total, Decimal("0"))

    @staticmethod
    def _group_by_purpose(
        rows: tuple[DetectedRow, ...], *, months: int
    ) -> tuple[GroupTotal, ...]:
        return _group(
            rows,
            key=lambda row: row.spending_purpose.value,
            label=lambda row: row.spending_purpose.value.replace("_", " ").capitalize(),
            months=months,
        )

    @staticmethod
    def _group_by_method(
        rows: tuple[DetectedRow, ...], *, months: int
    ) -> tuple[GroupTotal, ...]:
        return _group(
            rows,
            key=lambda row: row.payment_method.value,
            label=lambda row: row.payment_method.value.replace("_", " ").capitalize(),
            months=months,
        )

    def _commitments(
        self, rows: tuple[DetectedRow, ...], *, user_id: UUID, months: int
    ) -> tuple[Commitment, ...]:
        """Standing arrangements this batch contains, and which of them are new.

        Grouped by merchant rather than by description: one debit order appears with three
        different reference numbers across six months of statements, and reporting it three
        times would triple the commitment the user is being warned about.
        """
        known_merchants = {
            txn.merchant
            for txn in self._transactions.for_user(user_id=user_id, limit=HISTORY_LIMIT)
            if txn.merchant
        }

        grouped: dict[str, list[DetectedRow]] = defaultdict(list)
        for row in rows:
            if not row.payment_method.is_committed:
                continue
            grouped[row.merchant or row.description.lower()].append(row)

        commitments = []
        for label, group in grouped.items():
            total = sum((abs(r.amount) for r in group), Decimal("0"))
            commitments.append(
                Commitment(
                    label=label,
                    merchant=group[0].merchant,
                    method=group[0].payment_method,
                    purpose=group[0].spending_purpose,
                    monthly_amount=_to_cents(total / Decimal(max(months, 1))),
                    occurrences=len(group),
                    is_new=group[0].merchant not in known_merchants,
                )
            )
        return tuple(sorted(commitments, key=lambda c: -c.monthly_amount))

    @staticmethod
    def _affected(
        *, account_id: UUID, impact: SpendingImpact, is_preview: bool
    ) -> tuple[AffectedArea, ...]:
        """Everything downstream that this import moves, named rather than implied.

        specs/transactions.md step 7 requires derived balances to be invalidated and
        forecasts marked stale. It does not require telling the user, and every one of these
        is a figure they have seen and may be about to act on. The verb differs by area
        because what happens to them genuinely differs: the position and health score are
        recomputed inline on commit (see `ImportService.commit`), while the forecast is
        marked stale for the worker to regenerate.
        """
        verb = "will be" if is_preview else "was"
        areas = [
            AffectedArea(
                area="account_balance",
                effect=f"{verb} recalculated",
                detail=f"Derived balance for account {account_id}.",
            ),
            AffectedArea(
                area="position_snapshot",
                effect=f"{verb} recaptured",
                detail="Net worth, liquid savings, total debt, and this month's cash flow.",
            ),
            AffectedArea(
                area="financial_health",
                effect=f"{verb} reassessed",
                detail=(
                    "A committed import is the material change specs/financial-health.md "
                    "triggers reassessment on."
                ),
            ),
            AffectedArea(
                area="forecast",
                effect=f"{verb} marked stale",
                detail="Every projection rests on the baselines these transactions change.",
            ),
            AffectedArea(
                area="recurring_series",
                effect=f"{verb} re-detected",
                detail="Three or more occurrences of the same description form a series.",
            ),
        ]

        cash_flow = impact.change("monthly_cash_flow")
        if cash_flow is not None and cash_flow.after < 0 <= cash_flow.before:
            areas.append(
                AffectedArea(
                    area="risk_flags",
                    effect="turns this month's cash flow negative",
                    detail=(
                        f"Monthly surplus moves from {cash_flow.before} to {cash_flow.after}."
                    ),
                )
            )

        cover = impact.change("emergency_fund_months")
        if cover is not None and cover.delta < 0:
            areas.append(
                AffectedArea(
                    area="emergency_fund",
                    effect="reduces cover",
                    detail=(
                        f"Cover moves from {cover.before} to {cover.after} months, because "
                        f"essential spending is the denominator — the savings balance itself "
                        f"is unchanged."
                    ),
                )
            )

        return tuple(areas)


def _group(
    rows: tuple[DetectedRow, ...],
    *,
    key,
    label,
    months: int,
) -> tuple[GroupTotal, ...]:
    """Total the absolute value of each group, largest first.

    Absolute value, because a grouping is answering "how much went to rent", and a reader
    comparing R14,500 of rent against R3,200 of groceries should not have to hold two
    minus signs in their head to do it. The sign is not lost — it is in each row, and in the
    kind that decides which side of the cash-flow summary the group lands on.
    """
    buckets: dict[str, list[DetectedRow]] = defaultdict(list)
    for row in rows:
        buckets[key(row)].append(row)

    divisor = Decimal(max(months, 1))
    totals = [
        GroupTotal(
            key=group_key,
            label=label(group[0]),
            total=_to_cents(sum((abs(r.amount) for r in group), Decimal("0"))),
            monthly_average=_to_cents(
                sum((abs(r.amount) for r in group), Decimal("0")) / divisor
            ),
            count=len(group),
        )
        for group_key, group in buckets.items()
    ]
    return tuple(sorted(totals, key=lambda t: -t.total))
