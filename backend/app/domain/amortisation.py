"""Fixed-rate instalment loan amortisation. See specs/scenarios.md and specs/debts.md."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

CENTS = Decimal("0.01")
TWELVE = Decimal("12")


def _quantise(value: Decimal) -> Decimal:
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class AmortisationPeriod:
    period: int
    opening_balance: Decimal
    instalment: Decimal
    interest: Decimal
    principal: Decimal
    closing_balance: Decimal


def amortisation_schedule(
    *,
    principal: Decimal,
    annual_rate: Decimal,
    term_months: int,
    extra_monthly: Decimal = Decimal("0"),
) -> list[AmortisationPeriod]:
    """Build a monthly amortisation schedule for a fixed-rate instalment loan.

    Formula:
        i = annual_rate / 12
        instalment = P * i / (1 - (1 + i) ** -n)          (i == 0: instalment = P / n)
        Each period: interest = opening_balance * i
                     principal = min(instalment - interest + extra_monthly, opening_balance)
                     closing_balance = opening_balance - principal

    Assumptions:
        - Fixed nominal annual rate, compounded and paid monthly.
        - Equal contractual instalments; extra_monthly is applied wholly to principal on
          top of the contractual instalment.
        - No initiation fee, monthly service fee, or insurance — those belong to a
          total-cost-of-ownership engine, not this one.
        - Payments occur at period end.

    Rounding:
        Instalment and per-period interest/principal/closing balance are quantised to two
        places with ROUND_HALF_UP, per the financial-domain-engine skill. The final
        period's principal component is adjusted so the closing balance is exactly zero,
        matching what a lender's statement shows.

    Raises:
        ValueError: if principal <= 0, term_months < 1, annual_rate < 0, or
            extra_monthly < 0.
    """
    if principal <= 0:
        raise ValueError(f"principal must be positive, got {principal}")
    if term_months < 1:
        raise ValueError(f"term_months must be >= 1, got {term_months}")
    if annual_rate < 0:
        raise ValueError(f"annual_rate must be >= 0, got {annual_rate}")
    if extra_monthly < 0:
        raise ValueError(f"extra_monthly must be >= 0, got {extra_monthly}")

    monthly_rate = annual_rate / TWELVE

    if monthly_rate == 0:
        instalment = _quantise(principal / term_months)
    else:
        factor = (1 + monthly_rate) ** term_months
        instalment = _quantise(principal * monthly_rate * factor / (factor - 1))

    periods: list[AmortisationPeriod] = []
    balance = principal
    period = 1
    while balance > 0:
        interest = _quantise(balance * monthly_rate)
        principal_component = instalment - interest + extra_monthly
        is_final = principal_component >= balance or period == term_months
        if is_final:
            principal_component = balance
        closing = _quantise(balance - principal_component)
        periods.append(
            AmortisationPeriod(
                period=period,
                opening_balance=_quantise(balance),
                instalment=_quantise(interest + principal_component),
                interest=interest,
                principal=_quantise(principal_component),
                closing_balance=closing,
            )
        )
        balance = closing
        period += 1
        if period > term_months * 4:
            raise ValueError("amortisation did not converge — check extra_monthly and rate")

    return periods
