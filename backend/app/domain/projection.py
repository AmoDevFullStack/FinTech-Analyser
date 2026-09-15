"""Month-by-month position projection shared by the baseline and scenario paths.

See ADR-005 action item 2: "Define the FinancialPosition value object shared by real and
snapshot paths." This module has no notion of whether `FinancialPosition` came from live
data or a `PositionSnapshot` — that distinction is the service layer's job.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.domain.amortisation import AmortisationPeriod

CENTS = Decimal("0.01")


def _quantise(value: Decimal) -> Decimal:
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class FinancialPosition:
    as_of: date
    liquid_savings: Decimal
    total_debt: Decimal
    net_worth: Decimal
    monthly_income: Decimal
    monthly_essential: Decimal
    monthly_discretionary: Decimal


@dataclass(frozen=True, slots=True)
class PeriodProjection:
    period: int
    month: str
    cash_flow: Decimal
    savings: Decimal
    debt: Decimal
    net_worth: Decimal


def project_forward(
    *,
    position: FinancialPosition,
    horizon_months: int,
    monthly_income_delta: Decimal = Decimal("0"),
    monthly_expense_delta: Decimal = Decimal("0"),
    monthly_debt_service: Decimal = Decimal("0"),
    existing_debt_schedule: tuple[AmortisationPeriod, ...] = (),
    new_debt_schedule: tuple[AmortisationPeriod, ...] = (),
) -> list[PeriodProjection]:
    """Project cash flow, savings, debt, and net worth forward from a position.

    Formula, per period t (1-indexed from the month after `position.as_of`):
        new_t        = new_debt_schedule[t-1]      if t <= len(new_debt_schedule)      else zeros
        existing_t   = existing_debt_schedule[t-1] if t <= len(existing_debt_schedule) else zeros

        existing_service_t = existing_t.instalment if existing_debt_schedule else monthly_debt_service
        existing_closing_t = existing_t.closing_balance if existing_debt_schedule
                             else position.total_debt

        cash_flow_t  = income + income_delta - essential - discretionary
                       - expense_delta - existing_service_t - new_t.instalment
        savings_t    = savings_{t-1} + cash_flow_t                    (savings_0 = liquid_savings)
        debt_t       = existing_closing_t + new_t.closing_balance
        net_worth_t  = net_worth_{t-1} + cash_flow_t
                       + existing_t.principal + new_t.principal       (net_worth_0 = net_worth)

    Assumptions:
        - Debt service is modelled one of two ways. Given `existing_debt_schedule` (from
          app/domain/debt_payoff.py), pre-existing debts amortise period by period: the
          instalment leaves cash flow, the principal component builds net worth, and the
          balance runs down to zero. Given only a flat `monthly_debt_service`, that amount
          leaves cash flow every period and the debt balance is held constant — a coarser
          model for a caller that has payment amounts but no schedule.
        - Both default to zero, which reproduces this engine's original behaviour exactly:
          debt service absent from cash flow and the debt balance flat. That default is
          kept only so stored results computed under it remain reproducible; a caller with
          debt data should pass one of the two, because a projection that ignores debt
          repayments overstates cash flow and savings for every month of the horizon.
        - An asset bought with new debt (a vehicle, a property) is not added to net worth —
          only cash and debt balances are tracked here. Net worth therefore falls by the
          new debt's interest cost and by any cash paid without financing (a deposit), and
          is understated relative to true net worth by the purchased asset's value. This is
          a stated v1 simplification, not an omission.
        - `monthly_income_delta` and `monthly_expense_delta` are constant for the whole
          horizon (they model a recurring change — a raise, a new insurance premium — not a
          one-off).
        - Zero deltas and empty schedules reproduce the do-nothing baseline: this is what
          lets one function serve both the baseline and scenario paths.

    Rounding:
        Every period figure quantised to two places with ROUND_HALF_UP.

    Raises:
        ValueError: if horizon_months < 1, or monthly_debt_service < 0.
    """
    if horizon_months < 1:
        raise ValueError(f"horizon_months must be >= 1, got {horizon_months}")
    if monthly_debt_service < 0:
        raise ValueError(
            f"monthly_debt_service must be >= 0, got {monthly_debt_service}"
        )

    periods: list[PeriodProjection] = []
    savings = position.liquid_savings
    net_worth = position.net_worth
    year, month = position.as_of.year, position.as_of.month

    for t in range(1, horizon_months + 1):
        month = month + 1
        if month > 12:
            month = 1
            year += 1

        if t <= len(new_debt_schedule):
            debt_period = new_debt_schedule[t - 1]
            instalment = debt_period.instalment
            principal_component = debt_period.principal
            new_debt_closing = debt_period.closing_balance
        else:
            instalment = Decimal("0")
            principal_component = Decimal("0")
            new_debt_closing = Decimal("0")

        if existing_debt_schedule:
            if t <= len(existing_debt_schedule):
                existing_period = existing_debt_schedule[t - 1]
                existing_service = existing_period.instalment
                existing_principal = existing_period.principal
                existing_closing = existing_period.closing_balance
            else:
                # The debt set is paid off: no further instalment, nothing outstanding.
                existing_service = Decimal("0")
                existing_principal = Decimal("0")
                existing_closing = Decimal("0")
        else:
            existing_service = monthly_debt_service
            existing_principal = Decimal("0")
            existing_closing = position.total_debt

        cash_flow = _quantise(
            position.monthly_income
            + monthly_income_delta
            - position.monthly_essential
            - position.monthly_discretionary
            - monthly_expense_delta
            - existing_service
            - instalment
        )
        savings = _quantise(savings + cash_flow)
        net_worth = _quantise(
            net_worth + cash_flow + principal_component + existing_principal
        )
        debt = _quantise(existing_closing + new_debt_closing)

        periods.append(
            PeriodProjection(
                period=t,
                month=f"{year:04d}-{month:02d}",
                cash_flow=cash_flow,
                savings=savings,
                debt=debt,
                net_worth=net_worth,
            )
        )

    return periods
