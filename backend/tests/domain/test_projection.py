from datetime import date
from decimal import Decimal

from app.domain.amortisation import amortisation_schedule
from app.domain.projection import FinancialPosition, project_forward


def _base_position() -> FinancialPosition:
    return FinancialPosition(
        as_of=date(2026, 9, 14),
        liquid_savings=Decimal("48200.00"),
        total_debt=Decimal("287300.00"),
        net_worth=Decimal("412500.00"),
        monthly_income=Decimal("52000.00"),
        monthly_essential=Decimal("31400.00"),
        monthly_discretionary=Decimal("9800.00"),
    )


def test_zero_delta_projection_has_constant_cash_flow() -> None:
    periods = project_forward(position=_base_position(), horizon_months=12)
    assert all(p.cash_flow == Decimal("10800.00") for p in periods)
    assert periods[0].month == "2026-10"
    assert periods[-1].month == "2027-09"


def test_savings_accumulates_by_cash_flow() -> None:
    periods = project_forward(position=_base_position(), horizon_months=3)
    assert periods[0].savings == Decimal("59000.00")
    assert periods[1].savings == Decimal("69800.00")
    assert periods[2].savings == Decimal("80600.00")


def test_new_debt_schedule_reduces_cash_flow_and_appears_in_debt_balance() -> None:
    schedule = amortisation_schedule(
        principal=Decimal("300000"), annual_rate=Decimal("0.1175"), term_months=72
    )
    periods = project_forward(
        position=_base_position(), horizon_months=3, new_debt_schedule=tuple(schedule)
    )
    instalment = schedule[0].instalment
    assert periods[0].cash_flow == Decimal("10800.00") - instalment
    assert periods[0].debt == Decimal("287300.00") + schedule[0].closing_balance


def test_debt_drops_to_baseline_after_new_debt_term_ends() -> None:
    schedule = amortisation_schedule(
        principal=Decimal("1000"), annual_rate=Decimal("0.12"), term_months=2
    )
    periods = project_forward(
        position=_base_position(), horizon_months=3, new_debt_schedule=tuple(schedule)
    )
    assert periods[2].debt == Decimal("287300.00")
