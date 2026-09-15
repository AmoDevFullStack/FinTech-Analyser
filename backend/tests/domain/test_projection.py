from datetime import date
from decimal import Decimal

import pytest

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


def test_default_arguments_keep_debt_service_out_of_cash_flow() -> None:
    """Engine 1.0.0 behaviour, preserved so results stored under it stay reproducible:
    with neither monthly_debt_service nor a schedule, no debt repayment leaves cash flow
    and the debt balance is flat.
    """
    position = FinancialPosition(
        as_of=date(2026, 1, 31),
        liquid_savings=Decimal("10000.00"),
        total_debt=Decimal("100000.00"),
        net_worth=Decimal("50000.00"),
        monthly_income=Decimal("30000.00"),
        monthly_essential=Decimal("12000.00"),
        monthly_discretionary=Decimal("5000.00"),
    )

    periods = project_forward(position=position, horizon_months=3)

    assert periods[0].cash_flow == Decimal("13000.00")
    assert all(p.debt == Decimal("100000.00") for p in periods)


def test_flat_monthly_debt_service_reduces_cash_flow_every_period() -> None:
    position = FinancialPosition(
        as_of=date(2026, 1, 31),
        liquid_savings=Decimal("10000.00"),
        total_debt=Decimal("100000.00"),
        net_worth=Decimal("50000.00"),
        monthly_income=Decimal("30000.00"),
        monthly_essential=Decimal("12000.00"),
        monthly_discretionary=Decimal("5000.00"),
    )

    periods = project_forward(
        position=position, horizon_months=3, monthly_debt_service=Decimal("4000.00")
    )

    assert periods[0].cash_flow == Decimal("9000.00")
    # The balance is held constant under the flat model; only a schedule runs it down.
    assert all(p.debt == Decimal("100000.00") for p in periods)


def test_an_existing_debt_schedule_runs_the_balance_down_and_builds_net_worth() -> None:
    from app.domain.amortisation import amortisation_schedule

    schedule = tuple(
        amortisation_schedule(
            principal=Decimal("100000"), annual_rate=Decimal("0.12"), term_months=24
        )
    )
    position = FinancialPosition(
        as_of=date(2026, 1, 31),
        liquid_savings=Decimal("10000.00"),
        total_debt=Decimal("100000.00"),
        net_worth=Decimal("50000.00"),
        monthly_income=Decimal("30000.00"),
        monthly_essential=Decimal("12000.00"),
        monthly_discretionary=Decimal("5000.00"),
    )

    periods = project_forward(
        position=position, horizon_months=30, existing_debt_schedule=schedule
    )

    # The instalment leaves cash flow ...
    assert periods[0].cash_flow == Decimal("13000.00") - schedule[0].instalment
    # ... the balance runs down to zero by the end of the schedule ...
    assert periods[23].debt == Decimal("0.00")
    # ... and stays there once the debt is gone, with the instalment no longer payable.
    assert periods[24].debt == Decimal("0.00")
    assert periods[24].cash_flow == Decimal("13000.00")


def test_a_schedule_builds_more_net_worth_than_the_same_payments_as_flat_service() -> None:
    """Paying a debt down converts cash into equity; treating the payment as a flat
    outflow makes the same money vanish. The schedule path must therefore end richer.
    """
    from app.domain.amortisation import amortisation_schedule

    schedule = tuple(
        amortisation_schedule(
            principal=Decimal("100000"), annual_rate=Decimal("0.12"), term_months=24
        )
    )
    position = FinancialPosition(
        as_of=date(2026, 1, 31),
        liquid_savings=Decimal("10000.00"),
        total_debt=Decimal("100000.00"),
        net_worth=Decimal("50000.00"),
        monthly_income=Decimal("30000.00"),
        monthly_essential=Decimal("12000.00"),
        monthly_discretionary=Decimal("5000.00"),
    )

    with_schedule = project_forward(
        position=position, horizon_months=24, existing_debt_schedule=schedule
    )
    with_flat = project_forward(
        position=position,
        horizon_months=24,
        monthly_debt_service=schedule[0].instalment,
    )

    assert with_schedule[-1].net_worth > with_flat[-1].net_worth
    assert with_schedule[-1].debt == Decimal("0.00")
    assert with_flat[-1].debt == Decimal("100000.00")


def test_negative_monthly_debt_service_is_rejected() -> None:
    position = FinancialPosition(
        as_of=date(2026, 1, 31),
        liquid_savings=Decimal("0.00"),
        total_debt=Decimal("0.00"),
        net_worth=Decimal("0.00"),
        monthly_income=Decimal("100.00"),
        monthly_essential=Decimal("0.00"),
        monthly_discretionary=Decimal("0.00"),
    )
    with pytest.raises(ValueError, match="monthly_debt_service"):
        project_forward(
            position=position, horizon_months=1, monthly_debt_service=Decimal("-1")
        )
