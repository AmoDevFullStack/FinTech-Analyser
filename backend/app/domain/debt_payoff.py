"""Multi-debt payoff strategies and open-ended (no-fixed-term) single-debt schedules.

See specs/debts.md. `app/domain/amortisation.py` covers a single fixed-term instalment
loan where the instalment is solved from principal/rate/term (a vehicle or home loan).
This module covers the two things that engine cannot: a schedule driven by a *fixed
payment* rather than a solved instalment (a credit card or store account has no fixed
term — the payoff date falls out of the payment, not the other way round), and comparing
avalanche, snowball, and consolidation across a user's whole debt set.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.domain.amortisation import AmortisationPeriod

CENTS = Decimal("0.01")
TWELVE = Decimal("12")
MAX_MONTHS = 1200  # 100 years — a converging schedule never approaches this; a guard only.


def _quantise(value: Decimal) -> Decimal:
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)


def payment_driven_schedule(
    *,
    principal: Decimal,
    annual_rate: Decimal,
    monthly_payment: Decimal,
    extra_monthly: Decimal = Decimal("0"),
) -> list[AmortisationPeriod]:
    """Amortise a balance at a fixed monthly payment rather than a fixed term.

    Formula: identical per-period mechanics to `amortisation_schedule` — interest on the
    opening balance, principal as the remainder, the final period's principal component
    adjusted so the closing balance is exactly zero — but the instalment is the caller's
    `monthly_payment` directly, not solved from a term. This is the shape a credit card or
    store account minimum payment actually takes: no contractual term, the number of
    months falls out of the payment instead of the other way round.

    Raises:
        ValueError: if principal <= 0, annual_rate < 0, monthly_payment <= 0,
            extra_monthly < 0, or the payment does not exceed the first period's interest
            (the balance would never reduce).
    """
    if principal <= 0:
        raise ValueError(f"principal must be positive, got {principal}")
    if annual_rate < 0:
        raise ValueError(f"annual_rate must be >= 0, got {annual_rate}")
    if monthly_payment <= 0:
        raise ValueError(f"monthly_payment must be positive, got {monthly_payment}")
    if extra_monthly < 0:
        raise ValueError(f"extra_monthly must be >= 0, got {extra_monthly}")

    monthly_rate = annual_rate / TWELVE
    first_interest = _quantise(principal * monthly_rate)
    if monthly_payment + extra_monthly <= first_interest:
        raise ValueError(
            "monthly_payment does not exceed interest on the opening balance — "
            "the balance would never reduce"
        )

    periods: list[AmortisationPeriod] = []
    balance = principal
    period = 1
    while balance > 0:
        interest = _quantise(balance * monthly_rate)
        principal_component = monthly_payment - interest + extra_monthly
        is_final = principal_component >= balance
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
        if period > MAX_MONTHS:
            raise ValueError("schedule did not converge within 100 years — check inputs")

    return periods


@dataclass(frozen=True, slots=True)
class WhatIfResult:
    extra_monthly: Decimal
    months_to_free: int
    total_interest: Decimal
    months_saved: int
    interest_saved: Decimal


def what_if(
    *,
    principal: Decimal,
    annual_rate: Decimal,
    monthly_payment: Decimal,
    term_months: int | None = None,
    increments: tuple[Decimal, ...] = (Decimal("100"), Decimal("500"), Decimal("1000")),
) -> list[WhatIfResult]:
    """The marginal effect of paying `increments` more per month than the baseline.

    Uses the fixed-term engine when `term_months` is known (a vehicle or home loan with a
    contractual term), and the fixed-payment engine otherwise (a credit card or store
    account, where only the minimum payment and rate are known). Either way the baseline
    is `extra_monthly=0` and each increment is compared against it.
    """

    def _schedule(extra: Decimal) -> list[AmortisationPeriod]:
        if term_months is not None:
            from app.domain.amortisation import amortisation_schedule

            return amortisation_schedule(
                principal=principal,
                annual_rate=annual_rate,
                term_months=term_months,
                extra_monthly=extra,
            )
        return payment_driven_schedule(
            principal=principal,
            annual_rate=annual_rate,
            monthly_payment=monthly_payment,
            extra_monthly=extra,
        )

    baseline = _schedule(Decimal("0"))
    baseline_months = len(baseline)
    baseline_interest = sum((p.interest for p in baseline), Decimal("0"))

    results = []
    for extra in increments:
        variant = _schedule(extra)
        variant_interest = sum((p.interest for p in variant), Decimal("0"))
        results.append(
            WhatIfResult(
                extra_monthly=extra,
                months_to_free=len(variant),
                total_interest=variant_interest,
                months_saved=baseline_months - len(variant),
                interest_saved=baseline_interest - variant_interest,
            )
        )
    return results


@dataclass(frozen=True, slots=True)
class DebtInput:
    id: str
    current_balance: Decimal
    annual_rate: Decimal
    minimum_payment: Decimal


@dataclass(frozen=True, slots=True)
class MultiDebtPeriod:
    month: int
    total_balance: Decimal
    interest: Decimal
    principal: Decimal
    payment: Decimal


@dataclass(frozen=True, slots=True)
class MultiDebtResult:
    strategy: str
    months_to_free: int
    total_interest: Decimal
    schedule: tuple[MultiDebtPeriod, ...]
    payoff_month_by_debt_id: dict[str, int]


def _simulate(
    debts: list[DebtInput], total_monthly: Decimal, *, priority: Callable[[DebtInput], Decimal]
) -> MultiDebtResult:
    """Simulate every debt together, one shared monthly budget, allocating the surplus
    above the sum of minimum payments to whichever debt `priority` ranks first among the
    still-active ones. When a debt is paid off, its minimum payment is not spent again —
    the sum of active minimums shrinks, so the surplus available to the remaining debts
    grows automatically the next month. This is the "roll the freed payment forward"
    behaviour both avalanche and snowball depend on; only the ranking differs between them.
    """
    if not debts:
        raise ValueError("at least one debt is required")

    order = sorted(debts, key=priority)
    balances = {d.id: d.current_balance for d in order}
    monthly_rates = {d.id: d.annual_rate / TWELVE for d in order}
    minimums = {d.id: d.minimum_payment for d in order}
    active_ids = [d.id for d in order]

    total_minimum = sum(minimums.values(), Decimal("0"))
    if total_monthly < total_minimum:
        raise ValueError(
            f"total_monthly ({total_monthly}) is less than the sum of minimum "
            f"payments ({total_minimum})"
        )

    schedule: list[MultiDebtPeriod] = []
    payoff_month: dict[str, int] = {}
    total_interest = Decimal("0")
    month = 0

    while active_ids:
        month += 1
        if month > MAX_MONTHS:
            raise ValueError("multi-debt schedule did not converge within 100 years")

        month_interest = Decimal("0")
        for debt_id in active_ids:
            interest = _quantise(balances[debt_id] * monthly_rates[debt_id])
            balances[debt_id] += interest
            month_interest += interest
        total_interest += month_interest

        month_payment = Decimal("0")
        for debt_id in active_ids:
            pay = min(minimums[debt_id], balances[debt_id])
            balances[debt_id] -= pay
            month_payment += pay

        surplus = total_monthly - sum(minimums[debt_id] for debt_id in active_ids)
        for debt_id in active_ids:
            if surplus <= 0:
                break
            pay = min(surplus, balances[debt_id])
            balances[debt_id] -= pay
            month_payment += pay
            surplus -= pay

        newly_paid = [debt_id for debt_id in active_ids if balances[debt_id] <= 0]
        for debt_id in newly_paid:
            balances[debt_id] = Decimal("0")
            payoff_month[debt_id] = month
        active_ids = [debt_id for debt_id in active_ids if debt_id not in newly_paid]

        total_balance = sum((balances[d.id] for d in order), Decimal("0"))
        month_principal = month_payment - month_interest
        schedule.append(
            MultiDebtPeriod(
                month=month,
                total_balance=total_balance,
                interest=month_interest,
                principal=month_principal,
                payment=month_payment,
            )
        )

    return MultiDebtResult(
        strategy="",  # filled in by the caller
        months_to_free=month,
        total_interest=total_interest,
        schedule=tuple(schedule),
        payoff_month_by_debt_id=payoff_month,
    )


def avalanche_schedule(debts: list[DebtInput], total_monthly: Decimal) -> MultiDebtResult:
    """Surplus to the highest annual rate first — mathematically optimal total interest."""
    result = _simulate(debts, total_monthly, priority=lambda d: -d.annual_rate)
    return _with_strategy(result, "avalanche")


def snowball_schedule(debts: list[DebtInput], total_monthly: Decimal) -> MultiDebtResult:
    """Surplus to the smallest current balance first — slower, but produces the early
    payoffs that measurably improve adherence (specs/debts.md)."""
    result = _simulate(debts, total_monthly, priority=lambda d: d.current_balance)
    return _with_strategy(result, "snowball")


def consolidation_schedule(
    *,
    total_principal: Decimal,
    annual_rate: Decimal,
    monthly_payment: Decimal,
    initiation_fee: Decimal = Decimal("0"),
) -> MultiDebtResult:
    """A single facility at a blended rate, replacing the whole debt set.

    The initiation fee is added to the principal being financed, per specs/debts.md
    ("a rate and any initiation fee"), then amortised as one fixed-payment schedule.
    """
    if total_principal <= 0:
        raise ValueError(f"total_principal must be positive, got {total_principal}")
    if initiation_fee < 0:
        raise ValueError(f"initiation_fee must be >= 0, got {initiation_fee}")

    financed = total_principal + initiation_fee
    periods = payment_driven_schedule(
        principal=financed, annual_rate=annual_rate, monthly_payment=monthly_payment
    )
    schedule = tuple(
        MultiDebtPeriod(
            month=p.period,
            total_balance=p.closing_balance,
            interest=p.interest,
            principal=p.principal,
            payment=p.instalment,
        )
        for p in periods
    )
    total_interest = sum((p.interest for p in periods), Decimal("0"))
    return MultiDebtResult(
        strategy="consolidation",
        months_to_free=len(periods),
        total_interest=total_interest,
        schedule=schedule,
        payoff_month_by_debt_id={},
    )


def _with_strategy(result: MultiDebtResult, strategy: str) -> MultiDebtResult:
    return MultiDebtResult(
        strategy=strategy,
        months_to_free=result.months_to_free,
        total_interest=result.total_interest,
        schedule=result.schedule,
        payoff_month_by_debt_id=result.payoff_month_by_debt_id,
    )


@dataclass(frozen=True, slots=True)
class StrategyComparison:
    avalanche: MultiDebtResult
    snowball: MultiDebtResult
    consolidation: MultiDebtResult | None
    interest_difference_avalanche_vs_snowball: Decimal
    months_difference_avalanche_vs_snowball: int
    difference_is_material: bool


MATERIALITY_INTEREST = Decimal("500")  # rand; below this the ranking is noise, not a choice
MATERIALITY_MONTHS = 2


def compare_strategies(
    debts: list[DebtInput],
    total_monthly: Decimal,
    *,
    consolidation_rate: Decimal | None = None,
    consolidation_fee: Decimal = Decimal("0"),
) -> StrategyComparison:
    """Compare avalanche and snowball, and consolidation when a blended rate is supplied.

    Per specs/debts.md: "states the cost difference between avalanche and snowball in
    rand and in months" and, "where the difference is small, the system says so, because
    a strategy the user abandons is worse than a slightly suboptimal one they finish."
    `difference_is_material` is that judgement, made once here rather than left to every
    caller to reimplement.
    """
    avalanche = avalanche_schedule(debts, total_monthly)
    snowball = snowball_schedule(debts, total_monthly)

    interest_diff = snowball.total_interest - avalanche.total_interest
    months_diff = snowball.months_to_free - avalanche.months_to_free
    material = interest_diff > MATERIALITY_INTEREST or abs(months_diff) > MATERIALITY_MONTHS

    consolidation = None
    if consolidation_rate is not None:
        total_balance = sum((d.current_balance for d in debts), Decimal("0"))
        consolidation = consolidation_schedule(
            total_principal=total_balance,
            annual_rate=consolidation_rate,
            monthly_payment=total_monthly,
            initiation_fee=consolidation_fee,
        )

    return StrategyComparison(
        avalanche=avalanche,
        snowball=snowball,
        consolidation=consolidation,
        interest_difference_avalanche_vs_snowball=interest_diff,
        months_difference_avalanche_vs_snowball=months_diff,
        difference_is_material=material,
    )
