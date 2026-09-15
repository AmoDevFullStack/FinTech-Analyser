"""Pure-function pieces of ScenarioService — no DB needed, unlike test_scenario_isolation.py.

Regression for a real crash: a user with no savings/transactional account (liquid_savings
== 0) creating a vehicle-purchase scenario with any deposit drives the scenario's first
projected period negative. emergency_fund_months (app/domain/) rightly rejects a negative
*real* balance, but a negative *projected* one is a legitimate "this scenario leaves you
insolvent" result, not invalid input — see the docstring on _emergency_fund_months_after.
"""

from datetime import date
from decimal import Decimal

from app.domain.projection import PeriodProjection
from app.services.scenario import FinancialPosition, _emergency_fund_months_after


def _position(**overrides) -> FinancialPosition:
    base = dict(
        as_of=date(2026, 9, 14),
        liquid_savings=Decimal("0"),
        total_debt=Decimal("0"),
        net_worth=Decimal("0"),
        monthly_income=Decimal("52000.00"),
        monthly_essential=Decimal("31400.00"),
        monthly_discretionary=Decimal("9800.00"),
    )
    base.update(overrides)
    return FinancialPosition(**base)


def _period(savings: Decimal) -> PeriodProjection:
    return PeriodProjection(
        period=1,
        month="2026-10",
        cash_flow=Decimal("0"),
        savings=savings,
        debt=Decimal("0"),
        net_worth=Decimal("0"),
    )


def test_negative_projected_savings_reports_zero_months_not_a_crash() -> None:
    result = _emergency_fund_months_after(_position(), _period(Decimal("-50000.00")))
    assert result == Decimal("0.000000")


def test_positive_projected_savings_still_computes_normally() -> None:
    result = _emergency_fund_months_after(
        _position(monthly_essential=Decimal("31400.00")), _period(Decimal("62800.00"))
    )
    assert result == Decimal("2.000000")
