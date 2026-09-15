"""Debt CRUD, single-debt schedules, and whole-debt-set strategy comparison.

See specs/debts.md and docs/api.md. All arithmetic lives in app/domain/amortisation.py
and app/domain/debt_payoff.py; this service only assembles their inputs and shapes their
outputs — it computes nothing itself, per the financial-domain-engine skill.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from app.core.db import DbSession
from app.core.errors import NotFoundError, ValidationError
from app.domain.amortisation import AmortisationPeriod, amortisation_schedule
from app.domain.debt_payoff import (
    DebtInput,
    StrategyComparison,
    WhatIfResult,
    compare_strategies,
    payment_driven_schedule,
    what_if,
)
from app.models.debt import Debt, DebtType
from app.repositories.debt import DebtRepository
from app.services.financial_health import FinancialHealthService
from app.services.forecast import ForecastService
from app.services.position import PositionService

DEFAULT_WHAT_IF_INCREMENTS = (Decimal("100"), Decimal("500"), Decimal("1000"))


@dataclass(frozen=True, slots=True)
class CreateDebtInput:
    debt_type: DebtType
    original_principal: Decimal
    current_balance: Decimal
    annual_rate: Decimal
    minimum_payment: Decimal
    started_on: date
    account_id: UUID | None = None
    instalment: Decimal | None = None
    term_months: int | None = None


@dataclass(frozen=True, slots=True)
class UpdateDebtInput:
    """Every field is optional and left unchanged when omitted."""

    debt_type: DebtType | None = None
    current_balance: Decimal | None = None
    annual_rate: Decimal | None = None
    minimum_payment: Decimal | None = None
    instalment: Decimal | None = None
    term_months: int | None = None


class DebtService:
    def __init__(self, session: DbSession) -> None:
        self._session = session
        self._debts = DebtRepository(session)
        self._position = PositionService(session)
        self._health = FinancialHealthService(session)

    def _sync_position(self, user_id: UUID) -> None:
        """A debt mutation moves both the health score's debt-burden component (see
        FinancialHealthService._monthly_debt_service) and the dashboard's total_debt
        figure where the debt is also a tracked account — see AccountService._sync_position
        for why both are refreshed together rather than only one.
        """
        self._position.capture_snapshot(user_id=user_id)
        self._health.assess(user_id=user_id)
        ForecastService(self._session).mark_stale(user_id=user_id)

    def create(self, *, user_id: UUID, data: CreateDebtInput) -> Debt:
        if data.current_balance < 0:
            raise ValidationError("current_balance must be >= 0.")
        if data.annual_rate < 0:
            raise ValidationError("annual_rate must be >= 0.")
        if data.minimum_payment <= 0:
            raise ValidationError("minimum_payment must be positive.")

        debt = Debt(
            user_id=user_id,
            account_id=data.account_id,
            debt_type=data.debt_type,
            original_principal=data.original_principal,
            current_balance=data.current_balance,
            annual_rate=data.annual_rate,
            minimum_payment=data.minimum_payment,
            instalment=data.instalment,
            term_months=data.term_months,
            started_on=data.started_on,
        )
        self._debts.add(debt)
        self._session.commit()
        self._sync_position(user_id)
        return debt

    def list_for_user(self, *, user_id: UUID) -> list[Debt]:
        return self._debts.list_for_user(user_id=user_id)

    def get(self, debt_id: UUID, *, user_id: UUID) -> Debt:
        debt = self._debts.get_for_user(debt_id, user_id=user_id)
        if debt is None:
            raise NotFoundError("No debt with that identifier exists for this user.")
        return debt

    def update(self, debt_id: UUID, *, user_id: UUID, data: UpdateDebtInput) -> Debt:
        debt = self.get(debt_id, user_id=user_id)

        if data.debt_type is not None:
            debt.debt_type = data.debt_type
        if data.current_balance is not None:
            if data.current_balance < 0:
                raise ValidationError("current_balance must be >= 0.")
            debt.current_balance = data.current_balance
        if data.annual_rate is not None:
            if data.annual_rate < 0:
                raise ValidationError("annual_rate must be >= 0.")
            debt.annual_rate = data.annual_rate
        if data.minimum_payment is not None:
            if data.minimum_payment <= 0:
                raise ValidationError("minimum_payment must be positive.")
            debt.minimum_payment = data.minimum_payment
        if data.instalment is not None:
            debt.instalment = data.instalment
        if data.term_months is not None:
            debt.term_months = data.term_months

        self._session.commit()
        self._sync_position(user_id)
        return debt

    def soft_delete(self, debt_id: UUID, *, user_id: UUID) -> None:
        debt = self.get(debt_id, user_id=user_id)
        debt.deleted_at = datetime.now(UTC)
        self._session.commit()
        self._sync_position(user_id)

    def schedule(
        self, debt_id: UUID, *, user_id: UUID, extra_monthly: Decimal = Decimal("0")
    ) -> list[AmortisationPeriod]:
        """`GET /debts/{id}/schedule?extra_monthly=` — computed synchronously per
        docs/api.md, since it is fast and deterministic.

        A debt with a known `term_months` (a vehicle or home loan) uses the fixed-term
        engine, which solves the instalment. A debt with no fixed term (a credit card or
        store account) uses the fixed-payment engine, driven by its instalment where the
        lender has set one, or its minimum payment otherwise.
        """
        debt = self.get(debt_id, user_id=user_id)
        if debt.term_months is not None:
            return amortisation_schedule(
                principal=debt.current_balance,
                annual_rate=debt.annual_rate,
                term_months=debt.term_months,
                extra_monthly=extra_monthly,
            )
        payment = debt.instalment if debt.instalment is not None else debt.minimum_payment
        return payment_driven_schedule(
            principal=debt.current_balance,
            annual_rate=debt.annual_rate,
            monthly_payment=payment,
            extra_monthly=extra_monthly,
        )

    def what_if(
        self,
        debt_id: UUID,
        *,
        user_id: UUID,
        increments: tuple[Decimal, ...] = DEFAULT_WHAT_IF_INCREMENTS,
    ) -> list[WhatIfResult]:
        debt = self.get(debt_id, user_id=user_id)
        payment = debt.instalment if debt.instalment is not None else debt.minimum_payment
        return what_if(
            principal=debt.current_balance,
            annual_rate=debt.annual_rate,
            monthly_payment=payment,
            term_months=debt.term_months,
            increments=increments,
        )

    def compare_strategies(
        self,
        *,
        user_id: UUID,
        total_monthly: Decimal | None = None,
        consolidation_rate: Decimal | None = None,
        consolidation_fee: Decimal = Decimal("0"),
    ) -> StrategyComparison:
        """`GET /debts/strategies`. `total_monthly` defaults to the sum of every debt's
        minimum payment (i.e. the user's current commitment, with no surplus) when not
        supplied, so the comparison is meaningful even before the user states a budget —
        though with no surplus, avalanche and snowball necessarily tie.
        """
        debts = self.list_for_user(user_id=user_id)
        if not debts:
            raise ValidationError("No debts exist for this user to compare strategies over.")

        inputs = [
            DebtInput(
                id=str(d.id),
                current_balance=d.current_balance,
                annual_rate=d.annual_rate,
                minimum_payment=d.minimum_payment,
            )
            for d in debts
        ]
        if total_monthly is None:
            total_monthly = sum((d.minimum_payment for d in inputs), Decimal("0"))
        elif total_monthly < sum((d.minimum_payment for d in inputs), Decimal("0")):
            raise ValidationError(
                "total_monthly must cover at least the sum of all minimum payments."
            )

        return compare_strategies(
            inputs,
            total_monthly,
            consolidation_rate=consolidation_rate,
            consolidation_fee=consolidation_fee,
        )
