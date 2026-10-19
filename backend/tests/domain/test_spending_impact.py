"""What a set of new transactions does to the derived figures. Pure, so no database.

Reference case throughout: the demo household in `app/cli.py` — R52,000 income, R16,900
essential, R9,800 discretionary, R48,200 liquid — taking on R14,500 of rent. Every expected
value below is hand-computed and the arithmetic is written out with it.
"""

from decimal import Decimal

import pytest

from app.domain.spending_impact import (
    ZERO_FLOWS,
    MonthlyFlows,
    combine_flows,
    spending_impact,
)


def _flows(
    income="0", essential="0", discretionary="0", saving="0", debt_service="0"
) -> MonthlyFlows:
    return MonthlyFlows(
        income=Decimal(income),
        essential=Decimal(essential),
        discretionary=Decimal(discretionary),
        saving=Decimal(saving),
        debt_service=Decimal(debt_service),
    )


BEFORE = _flows(income="52000.00", essential="16900.00", discretionary="9800.00")
RENT = _flows(essential="14500.00")
LIQUID = Decimal("48200.00")


def _impact(before=BEFORE, added=RENT, liquid=LIQUID):
    return spending_impact(
        before=before,
        added=added,
        liquid_savings_before=liquid,
        liquid_savings_after=liquid,
    )


# --------------------------------------------------------------------------------------
# Reference figures
# --------------------------------------------------------------------------------------
def test_adding_rent_moves_cash_flow_by_exactly_the_rent() -> None:
    """Hand-computed:
        before remaining = 52,000 - 16,900 - 9,800 = 25,300.00
        after  remaining = 52,000 - 31,400 - 9,800 = 10,800.00
        delta = -14,500.00
    """
    change = _impact().change("monthly_cash_flow")

    assert change.before == Decimal("25300.00")
    assert change.after == Decimal("10800.00")
    assert change.delta == Decimal("-14500.00")


def test_essential_spending_rises_by_the_added_amount() -> None:
    change = _impact().change("monthly_essential")

    assert change.before == Decimal("16900.00")
    assert change.after == Decimal("31400.00")
    assert change.delta == Decimal("14500.00")


def test_cash_flow_margin_matches_the_ratio_of_the_two_surpluses() -> None:
    """Hand-computed:
        before = 25,300 / 52,000 = 0.4865384615... -> 0.486538
        after  = 10,800 / 52,000 = 0.2076923077... -> 0.207692
    """
    change = _impact().change("cash_flow_margin")

    assert change.before == Decimal("0.486538")
    assert change.after == Decimal("0.207692")
    assert change.delta == Decimal("-0.278846")


def test_emergency_fund_cover_falls_although_the_savings_balance_is_untouched() -> None:
    """The point of reporting cover at all. Essential spending is the denominator.

    Hand-computed:
        before = 48,200 / 16,900 = 2.8520710059... -> 2.852071
        after  = 48,200 / 31,400 = 1.5350318471... -> 1.535032
    """
    impact = _impact()
    cover = impact.change("emergency_fund_months")
    savings = impact.change("liquid_savings")

    assert cover.before == Decimal("2.852071")
    assert cover.after == Decimal("1.535032")
    assert cover.delta < 0
    assert savings.delta == Decimal("0.00")


def test_debt_service_moves_debt_to_income() -> None:
    """Hand-computed: 6,430 / 52,000 = 0.1236538462... -> 0.123654."""
    change = _impact(added=_flows(debt_service="6430.00")).change("debt_to_income")

    assert change.before == Decimal("0.000000")
    assert change.after == Decimal("0.123654")


def test_saving_moves_the_savings_rate() -> None:
    """Hand-computed: 3,000 / 52,000 = 0.0576923077... -> 0.057692."""
    change = _impact(added=_flows(saving="3000.00")).change("savings_rate")

    assert change.after == Decimal("0.057692")


# --------------------------------------------------------------------------------------
# Invariants
# --------------------------------------------------------------------------------------
def test_adding_nothing_changes_nothing() -> None:
    impact = _impact(added=ZERO_FLOWS)

    assert all(change.delta == 0 for change in impact.changes)
    assert not any(change.is_material for change in impact.changes)


def test_every_money_change_is_quantised_to_two_places() -> None:
    for change in _impact().changes:
        if change.unit == "money":
            assert change.after.as_tuple().exponent == -2, change.name
        else:
            assert change.after.as_tuple().exponent == -6, change.name


def test_the_delta_is_always_after_minus_before() -> None:
    for change in _impact(added=_flows(income="1000", essential="500", saving="250")).changes:
        assert change.delta == change.after - change.before, change.name


def test_combine_is_field_wise_addition() -> None:
    combined = combine_flows(base=BEFORE, added=_flows(essential="14500.00", saving="250.00"))

    assert combined.essential == Decimal("31400.00")
    assert combined.saving == Decimal("250.00")
    assert combined.income == BEFORE.income


# --------------------------------------------------------------------------------------
# Edge cases the dashboard actually hits
# --------------------------------------------------------------------------------------
def test_a_user_with_no_income_yet_gets_zero_ratios_rather_than_an_exception() -> None:
    """A first import that contains only spending is a real state. The ratios are
    undefined, and the honest report is zero alongside a visible zero income — not a 500.
    """
    impact = spending_impact(
        before=ZERO_FLOWS,
        added=_flows(essential="14500.00"),
        liquid_savings_before=Decimal("0"),
        liquid_savings_after=Decimal("0"),
    )

    assert impact.change("cash_flow_margin").after == Decimal("0.000000")
    assert impact.change("savings_rate").after == Decimal("0.000000")
    assert impact.change("debt_to_income").after == Decimal("0.000000")
    assert impact.change("monthly_essential").after == Decimal("14500.00")


def test_a_negative_income_month_does_not_produce_a_negative_cash_flow_summary_input() -> None:
    """A salary reversal can drive net income below zero. `cash_flow_summary` rejects a
    negative income by design, so the surplus is computed against zero and the negative
    income itself is still reported in its own row."""
    impact = spending_impact(
        before=_flows(income="-500.00"),
        added=ZERO_FLOWS,
        liquid_savings_before=Decimal("0"),
        liquid_savings_after=Decimal("0"),
    )

    assert impact.change("monthly_income").after == Decimal("-500.00")
    assert impact.change("monthly_cash_flow").after == Decimal("0.00")


@pytest.mark.parametrize(
    "field", ["essential", "discretionary", "saving", "debt_service"]
)
def test_a_negative_magnitude_is_rejected_by_name(field: str) -> None:
    """A negative magnitude means the caller mixed up the sign convention. Accepting it
    would produce a plausible wrong number rather than an error."""
    with pytest.raises(ValueError, match=field):
        spending_impact(
            before=_flows(**{field: "-1"}),
            added=ZERO_FLOWS,
            liquid_savings_before=Decimal("0"),
            liquid_savings_after=Decimal("0"),
        )


def test_negative_liquid_savings_is_rejected() -> None:
    with pytest.raises(ValueError, match="liquid_savings_before"):
        spending_impact(
            before=ZERO_FLOWS,
            added=ZERO_FLOWS,
            liquid_savings_before=Decimal("-1"),
            liquid_savings_after=Decimal("0"),
        )
