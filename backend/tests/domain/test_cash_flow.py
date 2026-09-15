from decimal import Decimal

import pytest

from app.domain.cash_flow import cash_flow_summary, debt_to_income


def test_cash_flow_summary_matches_dashboard_worked_example() -> None:
    """Reference: the published dashboard mock (.design/Main.dc.html) — income R52,000,
    essential R31,400, discretionary R9,800, remaining R10,800.
    """
    summary = cash_flow_summary(
        income=Decimal("52000.00"),
        essential=Decimal("31400.00"),
        discretionary=Decimal("9800.00"),
    )
    assert summary.remaining == Decimal("10800.00")


def test_remaining_can_be_negative() -> None:
    summary = cash_flow_summary(
        income=Decimal("1000"), essential=Decimal("800"), discretionary=Decimal("500")
    )
    assert summary.remaining == Decimal("-300.00")


def test_debt_to_income_matches_worked_example() -> None:
    ratio = debt_to_income(
        monthly_debt_service=Decimal("14764.41"), monthly_income=Decimal("52000.00")
    )
    assert ratio == Decimal("0.283931")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"income": Decimal("-1"), "essential": Decimal("0"), "discretionary": Decimal("0")},
        {"income": Decimal("0"), "essential": Decimal("-1"), "discretionary": Decimal("0")},
        {"income": Decimal("0"), "essential": Decimal("0"), "discretionary": Decimal("-1")},
    ],
)
def test_cash_flow_summary_rejects_negative_inputs(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        cash_flow_summary(**kwargs)


def test_debt_to_income_rejects_non_positive_income() -> None:
    with pytest.raises(ValueError):
        debt_to_income(monthly_debt_service=Decimal("100"), monthly_income=Decimal("0"))
