from decimal import Decimal

import pytest

from app.domain.amortisation import amortisation_schedule
from app.domain.debt_payoff import (
    DebtInput,
    avalanche_schedule,
    compare_strategies,
    consolidation_schedule,
    payment_driven_schedule,
    snowball_schedule,
    what_if,
)


def test_payment_driven_schedule_matches_fixed_term_engine_up_to_its_final_period() -> None:
    """A fixed-term loan's own solved instalment, fed back into the fixed-payment engine,
    must reproduce an identical schedule for every period except possibly the last: the
    fixed-term engine forces closure to exactly zero at `term_months` regardless of the
    natural per-period arithmetic (per its own docstring), while the fixed-payment engine
    has no term to force against and only closes once the natural arithmetic reaches zero
    — so a cent of rounding drift accumulated over the term can cost it one extra period.
    """
    fixed_term = amortisation_schedule(
        principal=Decimal("350000"), annual_rate=Decimal("0.1175"), term_months=72
    )
    driven = payment_driven_schedule(
        principal=Decimal("350000"),
        annual_rate=Decimal("0.1175"),
        monthly_payment=fixed_term[0].instalment,
    )
    assert len(driven) in (len(fixed_term), len(fixed_term) + 1)
    assert driven[-1].closing_balance == Decimal("0.00")
    for a, b in zip(fixed_term[:-1], driven[:-1]):
        assert a.interest == b.interest
        assert a.principal == b.principal
        assert a.closing_balance == b.closing_balance


def test_payment_driven_schedule_rejects_payment_below_interest() -> None:
    with pytest.raises(ValueError, match="does not exceed interest"):
        payment_driven_schedule(
            principal=Decimal("10000"), annual_rate=Decimal("0.24"), monthly_payment=Decimal("100")
        )


def test_what_if_more_payment_never_increases_months_or_interest() -> None:
    results = what_if(
        principal=Decimal("50000"),
        annual_rate=Decimal("0.24"),
        monthly_payment=Decimal("1500"),
        increments=(Decimal("100"), Decimal("500"), Decimal("1000")),
    )
    assert [r.extra_monthly for r in results] == [Decimal("100"), Decimal("500"), Decimal("1000")]
    # More extra payment saves at least as much as less extra payment — monotonic.
    for a, b in zip(results, results[1:]):
        assert b.months_saved >= a.months_saved
        assert b.interest_saved >= a.interest_saved
        assert b.months_saved > 0
        assert b.interest_saved > 0


def _debts() -> list[DebtInput]:
    return [
        DebtInput(id="card", current_balance=Decimal("20000"), annual_rate=Decimal("0.24"), minimum_payment=Decimal("600")),
        DebtInput(id="personal", current_balance=Decimal("60000"), annual_rate=Decimal("0.18"), minimum_payment=Decimal("1800")),
        DebtInput(id="vehicle", current_balance=Decimal("150000"), annual_rate=Decimal("0.1175"), minimum_payment=Decimal("2800")),
    ]


def test_avalanche_targets_highest_rate_debt_first() -> None:
    result = avalanche_schedule(_debts(), total_monthly=Decimal("6000"))
    # "card" has the highest rate (24%) — it must be paid off before the other two.
    assert result.payoff_month_by_debt_id["card"] < result.payoff_month_by_debt_id["personal"]
    assert result.payoff_month_by_debt_id["card"] < result.payoff_month_by_debt_id["vehicle"]


def test_snowball_targets_smallest_balance_debt_first() -> None:
    result = snowball_schedule(_debts(), total_monthly=Decimal("6000"))
    # "card" has the smallest balance (R20,000) — it must be paid off before the other two.
    assert result.payoff_month_by_debt_id["card"] < result.payoff_month_by_debt_id["personal"]
    assert result.payoff_month_by_debt_id["card"] < result.payoff_month_by_debt_id["vehicle"]


def test_avalanche_never_costs_more_interest_than_snowball() -> None:
    """Avalanche is mathematically optimal for total interest — specs/debts.md."""
    debts = _debts()
    avalanche = avalanche_schedule(debts, total_monthly=Decimal("6000"))
    snowball = snowball_schedule(debts, total_monthly=Decimal("6000"))
    assert avalanche.total_interest <= snowball.total_interest


def test_multi_debt_schedule_rejects_total_monthly_below_minimums() -> None:
    with pytest.raises(ValueError, match="less than the sum"):
        avalanche_schedule(_debts(), total_monthly=Decimal("1000"))


def test_multi_debt_schedule_all_debts_reach_zero_by_the_final_month() -> None:
    result = avalanche_schedule(_debts(), total_monthly=Decimal("6000"))
    assert result.schedule[-1].total_balance == Decimal("0")
    assert len(result.payoff_month_by_debt_id) == 3


def test_consolidation_schedule_amortises_to_zero() -> None:
    result = consolidation_schedule(
        total_principal=Decimal("230000"),
        annual_rate=Decimal("0.19"),
        monthly_payment=Decimal("6000"),
        initiation_fee=Decimal("1500"),
    )
    assert result.strategy == "consolidation"
    assert result.schedule[-1].total_balance == Decimal("0")
    assert result.months_to_free == len(result.schedule)


def test_compare_strategies_quantifies_the_avalanche_snowball_difference() -> None:
    comparison = compare_strategies(_debts(), total_monthly=Decimal("6000"))
    assert comparison.interest_difference_avalanche_vs_snowball == (
        comparison.snowball.total_interest - comparison.avalanche.total_interest
    )
    assert comparison.interest_difference_avalanche_vs_snowball >= 0
    assert comparison.consolidation is None


def test_compare_strategies_includes_consolidation_when_rate_supplied() -> None:
    comparison = compare_strategies(
        _debts(), total_monthly=Decimal("6000"), consolidation_rate=Decimal("0.20")
    )
    assert comparison.consolidation is not None
    assert comparison.consolidation.strategy == "consolidation"
