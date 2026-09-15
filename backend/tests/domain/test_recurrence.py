from datetime import date
from decimal import Decimal

import pytest

from app.domain.recurrence import (
    Frequency,
    Occurrence,
    detect_all,
    detect_series,
    upcoming_occurrences,
)


def _monthly(day_of_month: int, months: list[int], amount: str) -> list[Occurrence]:
    return [
        Occurrence(occurred_on=date(2026, m, day_of_month), amount=Decimal(amount))
        for m in months
    ]


def test_monthly_debit_order_is_detected() -> None:
    """Reference: a R900 gym debit order on the 3rd of March, April, May and June 2026.

    Source: hand-constructed from the calendar — gaps are 31, 30 and 31 days, whose median
    is 31, inside the 26-35 monthly band. Verified against a printed 2026 calendar.
    """
    series = detect_series(
        key="gym membership",
        occurrences=_monthly(3, [3, 4, 5, 6], "-900.00"),
    )

    assert series is not None
    assert series.frequency is Frequency.MONTHLY
    assert series.median_amount == Decimal("-900.00")
    assert series.occurrence_count == 4
    assert series.first_seen == date(2026, 3, 3)
    assert series.last_seen == date(2026, 6, 3)
    assert series.interval_days == 31
    assert series.next_expected_on == date(2026, 7, 4)


def test_monthly_series_annualises_to_twelve_times_the_amount() -> None:
    series = detect_series(key="gym", occurrences=_monthly(3, [3, 4, 5, 6], "-900.00"))
    assert series is not None
    assert series.annual_cost == Decimal("10800.00")
    assert series.monthly_equivalent == Decimal("900.00")


def test_weekly_series_annualises_to_fifty_two_times_the_amount() -> None:
    occurrences = [
        Occurrence(occurred_on=date(2026, 3, d), amount=Decimal("-250.00"))
        for d in (2, 9, 16, 23)
    ]
    series = detect_series(key="weekly cleaner", occurrences=occurrences)

    assert series is not None
    assert series.frequency is Frequency.WEEKLY
    assert series.annual_cost == Decimal("13000.00")
    # 52 * 250 / 12, quantised: R1,083.33
    assert series.monthly_equivalent == Decimal("1083.33")


def test_two_occurrences_are_not_a_series() -> None:
    assert detect_series(key="rent", occurrences=_monthly(1, [3, 4], "-9000.00")) is None


def test_irregular_intervals_are_not_a_series() -> None:
    """Three restaurant visits are not a debit order — the spec's whole point."""
    occurrences = [
        Occurrence(occurred_on=date(2026, 3, 2), amount=Decimal("-900.00")),
        Occurrence(occurred_on=date(2026, 3, 19), amount=Decimal("-900.00")),
        Occurrence(occurred_on=date(2026, 5, 27), amount=Decimal("-900.00")),
    ]
    assert detect_series(key="restaurant", occurrences=occurrences) is None


def test_varying_amounts_beyond_tolerance_are_not_a_series() -> None:
    occurrences = [
        Occurrence(occurred_on=date(2026, 3, 3), amount=Decimal("-900.00")),
        Occurrence(occurred_on=date(2026, 4, 3), amount=Decimal("-2400.00")),
        Occurrence(occurred_on=date(2026, 5, 3), amount=Decimal("-150.00")),
    ]
    assert detect_series(key="groceries", occurrences=occurrences) is None


def test_small_amount_variation_within_tolerance_still_detects() -> None:
    """A debit order that escalates slightly, or a utility bill, is still a series."""
    occurrences = [
        Occurrence(occurred_on=date(2026, 3, 3), amount=Decimal("-900.00")),
        Occurrence(occurred_on=date(2026, 4, 3), amount=Decimal("-945.00")),
        Occurrence(occurred_on=date(2026, 5, 3), amount=Decimal("-990.00")),
    ]
    series = detect_series(key="insurance", occurrences=occurrences)
    assert series is not None
    assert series.median_amount == Decimal("-945.00")


def test_same_day_occurrences_are_not_a_series() -> None:
    occurrences = [
        Occurrence(occurred_on=date(2026, 3, 3), amount=Decimal("-100.00")),
        Occurrence(occurred_on=date(2026, 3, 3), amount=Decimal("-100.00")),
        Occurrence(occurred_on=date(2026, 3, 3), amount=Decimal("-100.00")),
    ]
    assert detect_series(key="split payment", occurrences=occurrences) is None


def test_zero_median_amount_is_not_a_series() -> None:
    occurrences = [
        Occurrence(occurred_on=date(2026, 3, 3), amount=Decimal("0.00")),
        Occurrence(occurred_on=date(2026, 4, 3), amount=Decimal("0.00")),
        Occurrence(occurred_on=date(2026, 5, 3), amount=Decimal("0.00")),
    ]
    assert detect_series(key="reversal", occurrences=occurrences) is None


def test_detect_all_orders_by_descending_monthly_equivalent() -> None:
    groups = {
        "gym": _monthly(3, [3, 4, 5, 6], "-900.00"),
        "bond": _monthly(1, [3, 4, 5, 6], "-12000.00"),
        "once off": [Occurrence(occurred_on=date(2026, 3, 9), amount=Decimal("-50.00"))],
    }
    series = detect_all(groups=groups)

    assert [s.key for s in series] == ["bond", "gym"]


def test_upcoming_occurrences_lists_every_expected_date_in_the_window() -> None:
    weekly = detect_series(
        key="cleaner",
        occurrences=[
            Occurrence(occurred_on=date(2026, 3, d), amount=Decimal("-250.00"))
            for d in (2, 9, 16, 23)
        ],
    )
    assert weekly is not None

    expected = upcoming_occurrences([weekly], from_date=date(2026, 3, 24), days_ahead=30)

    assert [d for _, d in expected] == [
        date(2026, 3, 30),
        date(2026, 4, 6),
        date(2026, 4, 13),
        date(2026, 4, 20),
    ]


def test_upcoming_occurrences_rolls_a_stale_series_forward_rather_than_reporting_it_overdue() -> None:
    monthly = detect_series(key="gym", occurrences=_monthly(3, [3, 4, 5, 6], "-900.00"))
    assert monthly is not None

    # Next expected was 2026-07-04; asking from September must not return a past date.
    expected = upcoming_occurrences([monthly], from_date=date(2026, 9, 1), days_ahead=40)

    assert all(due >= date(2026, 9, 1) for _, due in expected)
    assert expected


def test_upcoming_occurrences_rejects_a_non_positive_window() -> None:
    with pytest.raises(ValueError, match="days_ahead"):
        upcoming_occurrences([], from_date=date(2026, 3, 1), days_ahead=0)
