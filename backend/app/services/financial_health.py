"""Financial health assessment, one calendar month at a time. See specs/financial-health.md.

Gathers the six components' inputs and hands them to app/domain/financial_health.py; this
service orchestrates, it does not score.

The score used to describe "now", computed over the current calendar month. That made it
unreadable on the 3rd of a month and wrong for anyone whose last statement was a while ago:
with no transactions this month, income and essential spending were zero, so emergency
cover was zero months however much was in savings, and cash-flow margin, savings rate and
debt-to-income all divided by a zero income. A user who added an emergency fund watched the
score not move, correctly and uselessly.

Now each month is scored on its own transactions and its own closing balance, stored
against that month, and re-scored when later data changes it. The flows come from
`MonthlySummaryService` — the same aggregate the month-by-month view reads, so the score
and the figures a user is looking at cannot disagree.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from app.core.db import DbSession
from app.core.errors import ValidationError
from app.domain.cash_flow import (
    cash_flow_margin,
    cash_flow_variability,
    debt_to_income,
    savings_rate,
)
from app.domain.emergency_fund import emergency_fund_months
from app.domain.financial_health import compute_health_score
from app.domain.net_worth import credit_utilisation
from app.models.account import Account, AccountType
from app.models.health_assessment import HealthAssessment
from app.repositories.account import AccountRepository
from app.repositories.debt import DebtRepository
from app.repositories.transaction import TransactionRepository
from app.repositories.health_assessment import HealthAssessmentRepository
from app.services.monthly_summary import MonthlySummaryService

TRAILING_MONTHS = 6

#: How many months back a ledger change re-scores. A statement imported in September
#: usually carries July and August, whose scores were computed before those transactions
#: existed; re-scoring the window is what keeps the series true rather than merely old.
ASSESSED_MONTHS = 12


def _month_key(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


def _month_start(month: str) -> date:
    """`2026-07` to 1 July 2026."""
    year, index = month.split("-")
    return date(int(year), int(index), 1)


def _add_months(day: date, months: int) -> date:
    index = day.year * 12 + (day.month - 1) + months
    return date(index // 12, index % 12 + 1, 1)


def _recent_month_keys(as_of: date, count: int) -> list[str]:
    """`count` month keys ending with `as_of`'s month, oldest first."""
    start = _add_months(as_of.replace(day=1), -(count - 1))
    return [_month_key(_add_months(start, offset)) for offset in range(count)]


def _month_end(month_start: date) -> date:
    if month_start.month == 12:
        return date(month_start.year + 1, 1, 1) - timedelta(days=1)
    return date(month_start.year, month_start.month + 1, 1) - timedelta(days=1)


class FinancialHealthService:
    def __init__(self, session: DbSession) -> None:
        self._session = session
        self._accounts = AccountRepository(session)
        self._debts = DebtRepository(session)
        self._transactions = TransactionRepository(session)
        self._assessments = HealthAssessmentRepository(session)

    def assess(
        self, *, user_id: UUID, as_of: date | None = None, month: str | None = None
    ) -> HealthAssessment:
        """Score one calendar month. Defaults to the month `as_of` falls in.

        Re-assessing a month corrects that month's stored row rather than adding a second
        opinion about the same period.
        """
        as_of = as_of or date.today()
        target = month or _month_key(as_of)
        if target > _month_key(as_of):
            raise ValidationError(
                f"Cannot assess {target}: it has not happened yet.",
                details={"month": target, "as_of": as_of.isoformat()},
            )

        assessed = self.assess_months(user_id=user_id, months=[target], as_of=as_of)
        return assessed[0]

    def assess_recent(
        self, *, user_id: UUID, as_of: date | None = None, months: int = ASSESSED_MONTHS
    ) -> list[HealthAssessment]:
        """Score the current month and the months before it, oldest first.

        Every ledger change re-runs this rather than only the current month: a statement
        imported in September usually carries July and August, and those months' scores
        were computed against transactions that had not arrived yet. Re-scoring is cheap
        (the figures come from one aggregate query) and idempotent, so the series is always
        as right as the data allows rather than as right as it was on the day it first ran.
        """
        as_of = as_of or date.today()
        return self.assess_months(
            user_id=user_id, months=_recent_month_keys(as_of, months), as_of=as_of
        )

    def assess_months(
        self, *, user_id: UUID, months: list[str], as_of: date | None = None
    ) -> list[HealthAssessment]:
        """Score each named month, oldest first.

        What is and is not historical, stated plainly because it decides what a comparison
        across months means:

        - **Historical, per month:** income, essential, discretionary, saving and debt
          payments, all from that month's own transactions; and liquid savings, taken from
          that month's closing balance, walked back from today's balance through everything
          that has moved since (app/domain/monthly.py).
        - **As they stand today, for every month:** the debts' contractual minimum payments
          and the credit-card balances and limits. Neither can be reconstructed — a card's
          balance in May is not recorded anywhere, and a debt carries one minimum payment,
          not a history of them. Each stored assessment says so in
          `breakdown["historical_basis"]`, so a reader comparing March with September knows
          which components could move and which could not.
        """
        as_of = as_of or date.today()
        if not months:
            return []

        accounts = self._accounts.list_for_user(user_id=user_id)
        # Enough extra history for the variability window of the oldest month requested.
        earliest = _month_start(min(months))
        reports = MonthlySummaryService(self._session).summary(
            user_id=user_id,
            since=_add_months(earliest, -(TRAILING_MONTHS - 1)),
            until=min(_month_end(_month_start(max(months))), as_of),
            as_of=as_of,
        )
        by_month = {report.comparison.month: report for report in reports}

        # Current values, the same for every month scored. See the docstring.
        minimum_payments = self._contractual_debt_service(user_id=user_id)
        utilisation = self._credit_utilisation(accounts)
        months_of_history = self._transactions.activity_span(user_id=user_id).months_with_activity

        assessed = []
        for month in sorted(months):
            if month > _month_key(as_of):
                continue
            report = by_month.get(month)
            if report is None:
                continue
            assessed.append(
                self._assess_one(
                    user_id=user_id,
                    month=month,
                    report=report,
                    by_month=by_month,
                    minimum_payments=minimum_payments,
                    utilisation=utilisation,
                    months_of_history=months_of_history,
                )
            )

        self._session.commit()
        return assessed

    def _assess_one(
        self,
        *,
        user_id: UUID,
        month: str,
        report,
        by_month: dict,
        minimum_payments: Decimal | None,
        utilisation: Decimal,
        months_of_history: int,
    ) -> HealthAssessment:
        totals = report.comparison.totals
        # The month's closing cash. `None` when nothing in scope holds a cash balance, in
        # which case there is no emergency cover to speak of rather than an unknown one.
        liquid_savings = report.balance.closing if report.balance is not None else Decimal("0")

        emergency_cover = emergency_fund_months(
            liquid_savings=max(liquid_savings, Decimal("0")),
            monthly_essential_spending=totals.essential,
        )
        dti = self._debt_to_income_ratio(
            monthly_debt_service=(
                minimum_payments if minimum_payments is not None else totals.debt_service
            ),
            monthly_income=totals.income,
        )
        margin = self._margin(totals)
        rate = self._savings_rate(totals.saving, totals.income)
        variability = self._variability_from(by_month, month=month, income=totals.income)

        result = compute_health_score(
            emergency_cover_months=emergency_cover,
            debt_to_income=dti,
            cash_flow_margin=margin,
            savings_rate=rate,
            credit_utilisation=utilisation,
            cash_flow_variability=variability,
        )

        breakdown = {
            "components": [
                {
                    "name": c.name,
                    "ratio": str(c.ratio),
                    "score": str(c.score),
                    "weight": str(c.weight),
                    "contribution": str(c.contribution),
                }
                for c in result.components
            ],
            "largest_positive_contributor": result.largest_positive_contributor,
            "largest_negative_contributor": result.largest_negative_contributor,
            # Which inputs are this month's and which are today's, per assess_months'
            # docstring. Stored rather than inferred, so an assessment stays readable after
            # the rule changes.
            "historical_basis": {
                "monthly_flows": month,
                "liquid_savings": month,
                "debt_minimum_payments": "current",
                "credit_utilisation": "current",
            },
            # How much of this score is standing on actual statement lines. A month scored
            # from 140 transactions and a month scored from four are not the same claim,
            # and the difference is invisible in the score itself.
            "evidence": {
                "transactions_in_month": report.transaction_count,
                "months_of_history": months_of_history,
                "imports_behind_month": len(report.import_batch_ids),
            },
        }

        existing = self._assessments.for_month(user_id=user_id, month=month)
        if existing is not None:
            existing.computed_at = datetime.now(UTC)
            existing.score = result.overall_score
            existing.weights_version = result.weights_version
            existing.breakdown = breakdown
            return existing

        return self._assessments.add(
            HealthAssessment(
                user_id=user_id,
                month=month,
                computed_at=datetime.now(UTC),
                score=result.overall_score,
                weights_version=result.weights_version,
                breakdown=breakdown,
            )
        )

    def _margin(self, totals) -> Decimal:
        if totals.income <= 0:
            return Decimal("0")
        remaining = totals.income - totals.essential - totals.discretionary
        return cash_flow_margin(remaining=remaining, income=totals.income)

    def _contractual_debt_service(self, *, user_id: UUID) -> Decimal | None:
        """Sum of every tracked debt's minimum payment, or `None` where none are tracked.

        Contractual minimums are a truer monthly debt service than transaction
        categorisation, which only sees what was actually paid — a missed or partial
        payment would understate the burden. `None` rather than zero so the caller knows to
        fall back to the month's categorised debt payments instead of scoring a user with
        untracked debt as having none.
        """
        debts = self._debts.list_for_user(user_id=user_id)
        if not debts:
            return None
        return sum((d.minimum_payment for d in debts), Decimal("0"))

    def _variability_from(self, by_month: dict, *, month: str, income: Decimal) -> Decimal:
        """How much the surplus moved over the six months ending with this one."""
        window = [m for m in sorted(by_month) if m <= month][-TRAILING_MONTHS:]
        remaining = []
        for key in window:
            totals = by_month[key].comparison.totals
            remaining.append(totals.income - totals.essential - totals.discretionary)

        if len(remaining) < 2 or income <= 0:
            # Not enough history to say anything about stability. Zero (this component's
            # best score) would overstate confidence for a brand-new user; the band table
            # maps a mid-range ratio to a middling score instead of a false "perfectly
            # stable". See the docstring on cash_flow_variability for the >= 2 months
            # requirement this is working around.
            return Decimal("0.10")

        return cash_flow_variability(monthly_remaining=remaining, income=income)

    def _debt_to_income_ratio(
        self, *, monthly_debt_service: Decimal, monthly_income: Decimal
    ) -> Decimal:
        if monthly_income <= 0:
            return Decimal("0")
        return debt_to_income(monthly_debt_service=monthly_debt_service, monthly_income=monthly_income)

    def _savings_rate(self, saved: Decimal, income: Decimal) -> Decimal:
        if income <= 0:
            return Decimal("0")
        return savings_rate(saved=saved, income=income)

    def _credit_utilisation(self, accounts: list[Account]) -> Decimal:
        credit_accounts = [a for a in accounts if a.account_type is AccountType.CREDIT_CARD]
        total_limit = sum((a.credit_limit or Decimal("0") for a in credit_accounts), Decimal("0"))
        if total_limit <= 0:
            return Decimal("0")
        total_owed = sum(
            (max(Decimal("0"), -a.current_balance) for a in credit_accounts), Decimal("0")
        )
        return credit_utilisation(balance_owed=total_owed, credit_limit=total_limit)

