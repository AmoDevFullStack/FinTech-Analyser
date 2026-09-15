from datetime import date
from decimal import Decimal

import pytest

from app.domain.emergency_fund import emergency_fund_months, project_depletion_date


def test_emergency_fund_months_matches_dashboard_worked_example() -> None:
    """Reference: R48,200 liquid savings against R31,400 monthly essential spending is
    48200/31400 = 1.535031847... months, independently divided by hand.

    Note: the published dashboard mock (.design/Main.dc.html) shows this pair as "1.53
    months" — that figure was written as illustrative sample copy and was never actually
    divided; the correct value rounds to 1.54, asserted here.
    """
    months = emergency_fund_months(
        liquid_savings=Decimal("48200.00"), monthly_essential_spending=Decimal("31400.00")
    )
    assert months.quantize(Decimal("0.01")) == Decimal("1.54")


def test_zero_essential_spending_yields_zero_months_not_an_error() -> None:
    months = emergency_fund_months(
        liquid_savings=Decimal("1000"), monthly_essential_spending=Decimal("0")
    )
    assert months == Decimal("0.000000")


def test_negative_liquid_savings_rejected() -> None:
    with pytest.raises(ValueError):
        emergency_fund_months(
            liquid_savings=Decimal("-1"), monthly_essential_spending=Decimal("100")
        )


def test_project_depletion_date_projects_by_whole_months() -> None:
    """R2,000 drawn down at R1,000/month reaches zero in exactly 2 months, by hand."""
    depletion = project_depletion_date(
        liquid_savings=Decimal("2000"),
        monthly_net_drawdown=Decimal("1000"),
        as_of=date(2026, 1, 1),
    )
    assert depletion == date(2026, 3, 1)


def test_non_positive_drawdown_never_depletes() -> None:
    assert (
        project_depletion_date(
            liquid_savings=Decimal("1000"),
            monthly_net_drawdown=Decimal("0"),
            as_of=date(2026, 1, 1),
        )
        is None
    )
