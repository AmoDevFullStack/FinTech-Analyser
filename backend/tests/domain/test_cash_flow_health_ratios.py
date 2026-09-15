from decimal import Decimal

import pytest

from app.domain.cash_flow import cash_flow_margin, cash_flow_variability, savings_rate


def test_cash_flow_margin_matches_hand_calculation() -> None:
    assert cash_flow_margin(remaining=Decimal("10800.00"), income=Decimal("52000.00")) == Decimal(
        "0.207692"
    )


def test_cash_flow_margin_negative_remaining_gives_negative_ratio() -> None:
    assert cash_flow_margin(remaining=Decimal("-1000"), income=Decimal("2000")) == Decimal("-0.5")


def test_savings_rate_matches_hand_calculation() -> None:
    assert savings_rate(saved=Decimal("5000"), income=Decimal("50000")) == Decimal("0.1")


def test_cash_flow_variability_zero_for_identical_months() -> None:
    result = cash_flow_variability(
        monthly_remaining=[Decimal("1000"), Decimal("1000"), Decimal("1000")],
        income=Decimal("50000"),
    )
    assert result == Decimal("0")


def test_cash_flow_variability_matches_hand_calculation() -> None:
    """Reference: remaining = [0, 2000], mean = 1000, variance = ((0-1000)^2 +
    (2000-1000)^2)/2 = (1_000_000 + 1_000_000)/2 = 1_000_000, stdev = 1000.
    Expressed against income 10000: 1000/10000 = 0.1, hand-derived.
    """
    result = cash_flow_variability(
        monthly_remaining=[Decimal("0"), Decimal("2000")], income=Decimal("10000")
    )
    assert result == Decimal("0.1")


def test_cash_flow_variability_requires_at_least_two_months() -> None:
    with pytest.raises(ValueError):
        cash_flow_variability(monthly_remaining=[Decimal("100")], income=Decimal("1000"))
