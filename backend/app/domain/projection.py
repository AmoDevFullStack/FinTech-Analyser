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
    new_debt_schedule: tuple[AmortisationPeriod, ...] = (),
) -> list[PeriodProjection]:
    """Project cash flow, savings, debt, and net worth forward from a position.

    Formula, per period t (1-indexed from the month after `position.as_of`):
        instalment_t = new_debt_schedule[t-1].instalment if t <= len(new_debt_schedule) else 0
        principal_t  = new_debt_schedule[t-1].principal  if t <= len(new_debt_schedule) else 0
        debt_closing_t = new_debt_schedule[t-1].closing_balance if t <= len(new_debt_schedule) else 0
        cash_flow_t  = income + income_delta - essential - discretionary
                       - expense_delta - instalment_t
        savings_t    = savings_{t-1} + cash_flow_t                    (savings_0 = liquid_savings)
        debt_t       = existing_total_debt + debt_closing_t
        net_worth_t  = net_worth_{t-1} + cash_flow_t + principal_t    (net_worth_0 = net_worth)

    Assumptions:
        - Pre-existing debts (other than a scenario's own new debt) are held constant over
          the horizon; this engine does not yet amortise them period by period. Full
          multi-debt scheduling is a Next-phase engine, per PLAN.md.
        - An asset bought with new debt (a vehicle, a property) is not added to net worth —
          only cash and debt balances are tracked here. Net worth therefore falls by the
          new debt's interest cost and by any cash paid without financing (a deposit), and
          is understated relative to true net worth by the purchased asset's value. This is
          a stated v1 simplification, not an omission.
        - `monthly_income_delta` and `monthly_expense_delta` are constant for the whole
          horizon (they model a recurring change — a raise, a new insurance premium — not a
          one-off).
        - Zero deltas and an empty `new_debt_schedule` reproduce the do-nothing baseline:
          this is what lets one function serve both the baseline and scenario paths.

    Rounding:
        Every period figure quantised to two places with ROUND_HALF_UP.

    Raises:
        ValueError: if horizon_months < 1.
    """
    if horizon_months < 1:
        raise ValueError(f"horizon_months must be >= 1, got {horizon_months}")

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

        cash_flow = _quantise(
            position.monthly_income
            + monthly_income_delta
            - position.monthly_essential
            - position.monthly_discretionary
            - monthly_expense_delta
            - instalment
        )
        savings = _quantise(savings + cash_flow)
        net_worth = _quantise(net_worth + cash_flow + principal_component)
        debt = _quantise(position.total_debt + new_debt_closing)

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
