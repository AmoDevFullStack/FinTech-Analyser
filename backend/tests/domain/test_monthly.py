"""Month-to-month comparison and the balance walk. Pure, so no database.

Reference case throughout: the demo household in `app/cli.py` — R52,000 income, R16,900
essential, R9,800 discretionary — over three consecutive months, with July taking on
R14,500 of rent. Every expected value is hand-computed and the arithmetic is written out
beside it.
"""

from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.domain.monthly import (
    MonthMovement,
    balance_history,
    compare_months,
    month_totals,
)


def _totals(month, income="52000", essential="16900", discretionary="9800", saving="0", debt_service="0"):
    return month_totals(
        month=month,
        income=Decimal(income),
        essential=Decimal(essential),
        discretionary=Decimal(discretionary),
        saving=Decimal(saving),
        debt_service=Decimal(debt_service),
    )


MAY = _totals("2026-05")
JUNE = _totals("2026-06")
JULY = _totals("2026-07", essential="31400")  # 16,900 + 14,500 rent


# ---------------------------------------------------------------------------------------
# Totals
# ---------------------------------------------------------------------------------------
def test_month_totals_reference_case():
    """spending = 16,900 + 9,800 + 0 + 0 = 26,700; net = 52,000 - 26,700 = 25,300."""
    assert JUNE.spending == Decimal("26700.00")
    assert JUNE.net == Decimal("25300.00")


def test_saving_counts_as_money_that_left():
    """A month that saved R3,000 had R3,000 less available, so spending includes it:
    16,900 + 9,800 + 3,000 = 29,700, and net falls to 22,300."""
    saved = _totals("2026-06", saving="3000")
    assert saved.spending == Decimal("29700.00")
    assert saved.net == Decimal("22300.00")


def test_a_month_that_overspent_reports_a_negative_net():
    """52,000 income against 31,400 + 9,800 + 15,000 = 56,200 leaves -4,200. Never
    clamped: an overspent month is exactly the month a user needs to see."""
    overspent = _totals("2026-07", essential="31400", debt_service="15000")
    assert overspent.net == Decimal("-4200.00")


def test_income_keeps_its_sign_so_a_reversed_salary_shows():
    reversed_salary = _totals("2026-07", income="-52000")
    assert reversed_salary.income == Decimal("-52000.00")


@pytest.mark.parametrize(
    "field", ["essential", "discretionary", "saving", "debt_service"]
)
def test_a_negative_spending_kind_is_rejected(field):
    """The sign convention applied twice upstream is a bug, not a number to pass on."""
    with pytest.raises(ValueError, match=field):
        _totals("2026-06", **{field: "-1"})


@pytest.mark.parametrize("month", ["2026-6", "202606", "", "2026-06-01", "abcd-ef"])
def test_a_malformed_month_is_rejected(month):
    with pytest.raises(ValueError, match="YYYY-MM"):
        _totals(month)


# ---------------------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------------------
def test_comparison_reference_case():
    """June to July, rent added: essential 16,900 -> 31,400.

    change            = 31,400 - 16,900 = 14,500
    percentage_change = 14,500 / 16,900 = 0.857988...  -> 0.857988
    net               = 25,300 -> 10,800, a change of -14,500
    """
    comparison = compare_months(current=JULY, previous=JUNE)
    changes = {change.metric: change for change in comparison.changes}

    assert comparison.month == "2026-07"
    assert comparison.previous_month == "2026-06"
    assert changes["essential"].change == Decimal("14500.00")
    assert changes["essential"].percentage_change == Decimal("0.857988")
    assert changes["net"].current == Decimal("10800.00")
    assert changes["net"].change == Decimal("-14500.00")


def test_an_unchanged_figure_reports_zero_not_absence():
    comparison = compare_months(current=JULY, previous=JUNE)
    changes = {change.metric: change for change in comparison.changes}
    assert changes["income"].change == Decimal("0.00")
    assert changes["income"].percentage_change == Decimal("0.000000")


def test_a_percentage_is_withheld_when_last_month_was_zero():
    """From nothing to something has no percentage. Reporting 0% would read as "no
    change", which is the opposite of what happened."""
    started_saving = _totals("2026-07", saving="3000")
    changes = {
        change.metric: change
        for change in compare_months(current=started_saving, previous=JUNE).changes
    }
    assert changes["saving"].change == Decimal("3000.00")
    assert changes["saving"].percentage_change is None


def test_the_first_month_has_nothing_to_compare_against():
    comparison = compare_months(current=MAY, previous=None)
    assert comparison.previous_month is None
    assert comparison.changes == ()


def test_a_month_cannot_be_compared_against_itself():
    with pytest.raises(ValueError, match="itself"):
        compare_months(current=JUNE, previous=JUNE)


# ---------------------------------------------------------------------------------------
# Balance walk
# ---------------------------------------------------------------------------------------
MOVEMENTS = (
    MonthMovement(month="2026-05", inflow=Decimal("52000"), outflow=Decimal("26700")),
    MonthMovement(month="2026-06", inflow=Decimal("52000"), outflow=Decimal("26700")),
    MonthMovement(month="2026-07", inflow=Decimal("52000"), outflow=Decimal("41200")),
)


def test_balance_history_reference_case():
    """Closing R48,200 at the end of July, walked backwards.

    July:  opening = 48,200 - (52,000 - 41,200) = 37,400
    June:  opening = 37,400 - (52,000 - 26,700) = 12,100
    May:   opening = 12,100 - (52,000 - 26,700) = -13,200
    """
    history = balance_history(closing_balance=Decimal("48200"), movements=MOVEMENTS)

    assert [balance.month for balance in history] == ["2026-05", "2026-06", "2026-07"]
    assert history[2].opening == Decimal("37400.00")
    assert history[2].closing == Decimal("48200.00")
    assert history[1].opening == Decimal("12100.00")
    assert history[0].opening == Decimal("-13200.00")


def test_each_month_opens_where_the_previous_one_closed():
    history = balance_history(closing_balance=Decimal("48200"), movements=MOVEMENTS)
    for earlier, later in zip(history, history[1:]):
        assert later.opening == earlier.closing


def test_a_month_with_no_transactions_carries_the_balance_across():
    quiet = MonthMovement(month="2026-06", inflow=Decimal("0"), outflow=Decimal("0"))
    history = balance_history(
        closing_balance=Decimal("48200"), movements=[MOVEMENTS[0], quiet, MOVEMENTS[2]]
    )
    assert history[1].opening == history[1].closing


def test_movements_out_of_order_are_rejected():
    """Walking an unordered sequence produces a plausible series of wrong balances, which
    is the failure mode worth refusing outright."""
    with pytest.raises(ValueError, match="ascending"):
        balance_history(
            closing_balance=Decimal("48200"),
            movements=[MOVEMENTS[2], MOVEMENTS[0], MOVEMENTS[1]],
        )


def test_a_repeated_month_is_rejected():
    with pytest.raises(ValueError, match="repeats"):
        balance_history(
            closing_balance=Decimal("48200"), movements=[MOVEMENTS[0], MOVEMENTS[0]]
        )


def test_an_empty_window_produces_no_balances():
    assert balance_history(closing_balance=Decimal("48200"), movements=[]) == ()


# ---------------------------------------------------------------------------------------
# Invariants
# ---------------------------------------------------------------------------------------
_MONEY = st.decimals(
    min_value=Decimal("0"), max_value=Decimal("250000"), places=2, allow_nan=False, allow_infinity=False
)


@settings(max_examples=100)
@given(inflows=st.lists(_MONEY, min_size=1, max_size=12), closing=_MONEY)
def test_the_walk_always_returns_to_the_balance_it_started_from(inflows, closing):
    """Whatever moved, the final month closes on the balance that was passed in, and the
    first month's opening plus every net movement gets back to it."""
    movements = [
        MonthMovement(month=f"2026-{index + 1:02d}", inflow=inflow, outflow=Decimal("0"))
        for index, inflow in enumerate(inflows)
    ]
    history = balance_history(closing_balance=closing, movements=movements)

    assert history[-1].closing == closing
    walked = history[0].opening + sum(
        balance.inflow - balance.outflow for balance in history
    )
    assert walked == closing


@settings(max_examples=100)
@given(
    income=_MONEY,
    essential=_MONEY,
    discretionary=_MONEY,
    saving=_MONEY,
    debt_service=_MONEY,
)
def test_the_parts_of_a_month_always_sum_to_the_whole(
    income, essential, discretionary, saving, debt_service
):
    totals = month_totals(
        month="2026-06",
        income=income,
        essential=essential,
        discretionary=discretionary,
        saving=saving,
        debt_service=debt_service,
    )
    assert totals.spending == (
        totals.essential + totals.discretionary + totals.saving + totals.debt_service
    )
    assert totals.net == totals.income - totals.spending


@settings(max_examples=100)
@given(previous=_MONEY, current=_MONEY)
def test_a_change_is_always_the_difference_it_reports(previous, current):
    before = month_totals(
        month="2026-06",
        income=Decimal("0"),
        essential=previous,
        discretionary=Decimal("0"),
        saving=Decimal("0"),
        debt_service=Decimal("0"),
    )
    after = month_totals(
        month="2026-07",
        income=Decimal("0"),
        essential=current,
        discretionary=Decimal("0"),
        saving=Decimal("0"),
        debt_service=Decimal("0"),
    )
    change = next(
        c for c in compare_months(current=after, previous=before).changes if c.metric == "essential"
    )
    assert change.change == change.current - change.previous
