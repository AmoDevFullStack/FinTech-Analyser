"""Financial health assessment. See specs/financial-health.md.

Gathers the six components' inputs from accounts and transactions and hands them to
app/domain/financial_health.py; this service orchestrates, it does not score.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from app.core.db import DbSession
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
from app.models.category import CategoryKind
from app.models.health_assessment import HealthAssessment
from app.repositories.account import AccountRepository
from app.repositories.debt import DebtRepository
from app.repositories.health_assessment import HealthAssessmentRepository
from app.services.position import PositionService

TRAILING_MONTHS = 6


def _preceding_month_starts(as_of: date, count: int) -> list[date]:
    """`count` calendar-month starts ending at `as_of`'s month, oldest first."""
    starts = []
    year, month = as_of.year, as_of.month
    for _ in range(count):
        starts.append(date(year, month, 1))
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    return list(reversed(starts))


def _month_end(month_start: date) -> date:
    if month_start.month == 12:
        return date(month_start.year + 1, 1, 1) - timedelta(days=1)
    return date(month_start.year, month_start.month + 1, 1) - timedelta(days=1)


class FinancialHealthService:
    def __init__(self, session: DbSession) -> None:
        self._session = session
        self._accounts = AccountRepository(session)
        self._debts = DebtRepository(session)
        self._assessments = HealthAssessmentRepository(session)
        self._position = PositionService(session)

    def assess(self, *, user_id: UUID, as_of: date | None = None) -> HealthAssessment:
        as_of = as_of or date.today()
        accounts = self._accounts.list_for_user(user_id=user_id)
        position = self._position.compute_current(user_id=user_id, as_of=as_of)

        current_month_start = as_of.replace(day=1)
        current_sums = self._position.category_kind_sums(
            user_id=user_id, accounts=accounts, since=current_month_start, until=as_of
        )

        emergency_cover = emergency_fund_months(
            liquid_savings=position.liquid_savings,
            monthly_essential_spending=position.monthly_essential,
        )

        dti = self._debt_to_income_ratio(
            monthly_debt_service=self._monthly_debt_service(
                user_id=user_id, transaction_derived=current_sums[CategoryKind.DEBT]
            ),
            monthly_income=position.monthly_income,
        )
        margin = self._cash_flow_margin(position)
        rate = self._savings_rate(current_sums[CategoryKind.SAVING], position.monthly_income)
        utilisation = self._credit_utilisation(accounts)
        variability = self._cash_flow_variability(
            user_id=user_id, accounts=accounts, as_of=as_of, current_income=position.monthly_income
        )

        result = compute_health_score(
            emergency_cover_months=emergency_cover,
            debt_to_income=dti,
            cash_flow_margin=margin,
            savings_rate=rate,
            credit_utilisation=utilisation,
            cash_flow_variability=variability,
        )

        assessment = HealthAssessment(
            user_id=user_id,
            computed_at=datetime.now(UTC),
            score=result.overall_score,
            weights_version=result.weights_version,
            breakdown={
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
            },
        )
        self._assessments.add(assessment)
        self._session.commit()
        return assessment

    def _monthly_debt_service(self, *, user_id: UUID, transaction_derived: Decimal) -> Decimal:
        """Sum of every active `Debt`'s minimum payment where any exist; contractual
        minimums are a truer monthly debt service than transaction categorisation, which
        only sees what was actually paid — a missed or partial payment would understate
        the burden. Falls back to the category-derived sum for a user with no `Debt`
        records yet (see PositionService's module docstring for why that fallback exists).
        """
        debts = self._debts.list_for_user(user_id=user_id)
        if not debts:
            return transaction_derived
        return sum((d.minimum_payment for d in debts), Decimal("0"))

    def _debt_to_income_ratio(
        self, *, monthly_debt_service: Decimal, monthly_income: Decimal
    ) -> Decimal:
        if monthly_income <= 0:
            return Decimal("0")
        return debt_to_income(monthly_debt_service=monthly_debt_service, monthly_income=monthly_income)

    def _cash_flow_margin(self, position) -> Decimal:
        if position.monthly_income <= 0:
            return Decimal("0")
        remaining = (
            position.monthly_income - position.monthly_essential - position.monthly_discretionary
        )
        return cash_flow_margin(remaining=remaining, income=position.monthly_income)

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

    def _cash_flow_variability(
        self,
        *,
        user_id: UUID,
        accounts: list[Account],
        as_of: date,
        current_income: Decimal,
    ) -> Decimal:
        month_starts = _preceding_month_starts(as_of, TRAILING_MONTHS)
        monthly_remaining = []
        for month_start in month_starts:
            month_end = min(_month_end(month_start), as_of)
            sums = self._position.category_kind_sums(
                user_id=user_id, accounts=accounts, since=month_start, until=month_end
            )
            remaining = sums[CategoryKind.INCOME] - sums[CategoryKind.ESSENTIAL] - sums[
                CategoryKind.DISCRETIONARY
            ]
            monthly_remaining.append(remaining)

        if len(monthly_remaining) < 2 or current_income <= 0:
            # Not enough history to say anything about stability. Zero (this component's
            # best score) would overstate confidence for a brand-new user; the band table
            # maps a mid-range ratio to a middling score instead of a false "perfectly
            # stable". See the docstring on cash_flow_variability for the >= 2 months
            # requirement this is working around.
            return Decimal("0.10")

        return cash_flow_variability(monthly_remaining=monthly_remaining, income=current_income)
