"""Emergency fund coverage. See specs/dashboard.md and requirements.md §10."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal


@dataclass(frozen=True, slots=True)
class EmergencyFundProjection:
    months_covered_now: Decimal
    depletion_date: date | None


def emergency_fund_months(
    *, liquid_savings: Decimal, monthly_essential_spending: Decimal
) -> Decimal:
    """Months of essential spending the current liquid savings would cover.

    Formula:
        months = liquid_savings / monthly_essential_spending

    Assumptions:
        - `liquid_savings` is cash the user could access without penalty (specs/dashboard.md
          region 1) — the caller decides what counts as liquid, this engine only divides.
        - When monthly_essential_spending is zero, coverage is defined as zero months
          rather than raising, because a user with no recorded essential spending yet is a
          real (if unusual) state, not an error.

    Rounding:
        Quantised to six places (NUMERIC(9,6)), ROUND_HALF_UP.

    Raises:
        ValueError: if liquid_savings < 0 or monthly_essential_spending < 0.
    """
    if liquid_savings < 0:
        raise ValueError(f"liquid_savings must be >= 0, got {liquid_savings}")
    if monthly_essential_spending < 0:
        raise ValueError(
            f"monthly_essential_spending must be >= 0, got {monthly_essential_spending}"
        )

    if monthly_essential_spending == 0:
        return Decimal("0.000000")

    months = liquid_savings / monthly_essential_spending
    return months.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def project_depletion_date(
    *,
    liquid_savings: Decimal,
    monthly_net_drawdown: Decimal,
    as_of: date,
) -> date | None:
    """Project the date liquid savings reaches zero under a constant monthly drawdown.

    Formula:
        months_to_zero = liquid_savings / monthly_net_drawdown   (only when drawdown > 0)
        depletion_date = as_of + months_to_zero calendar months, day-of-month preserved
        where possible, otherwise clamped to the last day of the resulting month.

    Assumptions:
        - `monthly_net_drawdown` is the amount the fund shrinks by each month, i.e. a
          positive number when spending exceeds income. A drawdown <= 0 means the fund
          never depletes under current behaviour, and this returns None.
        - `as_of` is an explicit argument, never `date.today()` — see the
          financial-domain-engine skill, rule 1.

    Rounding:
        The month count is taken as a whole number of months via `Decimal.to_integral_value`
        with ROUND_HALF_UP before being added to `as_of`; part-month precision does not
        change which month the fund crosses zero in any case that matters to the user.

    Raises:
        ValueError: if liquid_savings < 0.
    """
    if liquid_savings < 0:
        raise ValueError(f"liquid_savings must be >= 0, got {liquid_savings}")

    if monthly_net_drawdown <= 0:
        return None

    months_to_zero = (liquid_savings / monthly_net_drawdown).to_integral_value(
        rounding=ROUND_HALF_UP
    )
    return _add_months(as_of, int(months_to_zero))


def _add_months(start: date, months: int) -> date:
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    day = min(start.day, _days_in_month(year, month))
    return date(year, month, day)


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        next_month_start = date(year + 1, 1, 1)
    else:
        next_month_start = date(year, month + 1, 1)
    return (next_month_start - date(year, month, 1)).days
