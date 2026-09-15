"""Cash-flow arithmetic over a period. See specs/dashboard.md region 2."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

CENTS = Decimal("0.01")


def _quantise(value: Decimal) -> Decimal:
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class CashFlowSummary:
    income: Decimal
    essential: Decimal
    discretionary: Decimal
    remaining: Decimal


def cash_flow_summary(
    *,
    income: Decimal,
    essential: Decimal,
    discretionary: Decimal,
) -> CashFlowSummary:
    """Summarise a period's cash flow.

    Formula:
        remaining = income - essential - discretionary

    Assumptions:
        - `income`, `essential`, and `discretionary` are already the period's totals —
          transfers are excluded upstream, per specs/transactions.md step 4.
        - `remaining` may be negative; a negative remaining is a real, meaningful figure
          and is never clamped to zero.

    Rounding:
        All fields quantised to two places with ROUND_HALF_UP.

    Raises:
        ValueError: if income, essential, or discretionary is negative.
    """
    if income < 0:
        raise ValueError(f"income must be >= 0, got {income}")
    if essential < 0:
        raise ValueError(f"essential must be >= 0, got {essential}")
    if discretionary < 0:
        raise ValueError(f"discretionary must be >= 0, got {discretionary}")

    remaining = income - essential - discretionary
    return CashFlowSummary(
        income=_quantise(income),
        essential=_quantise(essential),
        discretionary=_quantise(discretionary),
        remaining=_quantise(remaining),
    )


def debt_to_income(*, monthly_debt_service: Decimal, monthly_income: Decimal) -> Decimal:
    """Ratio of monthly debt service to monthly income.

    Formula:
        debt_to_income = monthly_debt_service / monthly_income

    Rounding:
        Quantised to six places (NUMERIC(9,6) per docs/database.md), ROUND_HALF_UP.

    Raises:
        ValueError: if monthly_debt_service < 0 or monthly_income <= 0.
    """
    if monthly_debt_service < 0:
        raise ValueError(f"monthly_debt_service must be >= 0, got {monthly_debt_service}")
    if monthly_income <= 0:
        raise ValueError(f"monthly_income must be > 0, got {monthly_income}")

    ratio = monthly_debt_service / monthly_income
    return ratio.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


RATE_PLACES = Decimal("0.000001")


def cash_flow_margin(*, remaining: Decimal, income: Decimal) -> Decimal:
    """Surplus as a fraction of income. See specs/financial-health.md's cash-flow-margin
    component.

    Formula:
        cash_flow_margin = remaining / income

    Assumptions:
        - `remaining` may be negative (a deficit month); the ratio is then negative too,
          which the health engine's band table maps to a score of 0 (see its clamping).

    Rounding:
        Six places, ROUND_HALF_UP.

    Raises:
        ValueError: if income <= 0.
    """
    if income <= 0:
        raise ValueError(f"income must be > 0, got {income}")
    return (remaining / income).quantize(RATE_PLACES, rounding=ROUND_HALF_UP)


def savings_rate(*, saved: Decimal, income: Decimal) -> Decimal:
    """Amount saved as a fraction of income. See specs/financial-health.md.

    Formula:
        savings_rate = saved / income

    Rounding:
        Six places, ROUND_HALF_UP.

    Raises:
        ValueError: if saved < 0 or income <= 0.
    """
    if saved < 0:
        raise ValueError(f"saved must be >= 0, got {saved}")
    if income <= 0:
        raise ValueError(f"income must be > 0, got {income}")
    return (saved / income).quantize(RATE_PLACES, rounding=ROUND_HALF_UP)


def cash_flow_variability(*, monthly_remaining: list[Decimal], income: Decimal) -> Decimal:
    """Month-to-month variability of surplus, as a fraction of income.

    Formula:
        mean = sum(monthly_remaining) / n
        variance = sum((x - mean) ** 2 for x in monthly_remaining) / n   (population, not
                    sample — these are the actual observed months, not a sample of a
                    larger population)
        cash_flow_variability = sqrt(variance) / income

    Assumptions:
        - Expressed relative to income, not to the mean of `monthly_remaining`, because
          the mean can be at or near zero (a break-even household), which would make a
          mean-relative coefficient of variation blow up or flip sign for a
          textbook-stable budget. Income is a stable denominator every user has.
        - Requires at least two months of data — with one month there is nothing to vary
          against. The caller decides what to report when history is thin (see
          app/services/financial_health.py).

    Rounding:
        Six places, ROUND_HALF_UP.

    Raises:
        ValueError: if fewer than two months are supplied, or income <= 0.
    """
    if len(monthly_remaining) < 2:
        raise ValueError("monthly_remaining must have at least two months of data")
    if income <= 0:
        raise ValueError(f"income must be > 0, got {income}")

    n = Decimal(len(monthly_remaining))
    mean = sum(monthly_remaining, Decimal("0")) / n
    variance = sum(((x - mean) ** 2 for x in monthly_remaining), Decimal("0")) / n
    stdev = variance.sqrt()
    return (stdev / income).quantize(RATE_PLACES, rounding=ROUND_HALF_UP)
