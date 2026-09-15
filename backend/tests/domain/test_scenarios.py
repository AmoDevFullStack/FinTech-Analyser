from decimal import Decimal

import pytest

from app.domain.scenarios import (
    DebtRepaymentChangeAssumptions,
    DiscretionaryExpenseAssumptions,
    IncomeChangeAssumptions,
    NewLoanAssumptions,
    PropertyPurchaseAssumptions,
    SavingsChangeAssumptions,
    VehiclePurchaseAssumptions,
)


def test_vehicle_purchase_finances_price_less_deposit_and_trade_in() -> None:
    """specs/scenarios.md's worked example: R350,000 vehicle, R50,000 deposit."""
    assumptions = VehiclePurchaseAssumptions(
        purchase_price=Decimal("350000"),
        deposit=Decimal("50000"),
        annual_rate=Decimal("0.1175"),
        term_months=72,
        insurance_monthly=Decimal("1450"),
        fuel_monthly=Decimal("2200"),
        maintenance_monthly=Decimal("650"),
        trade_in_value=Decimal("30000"),
    )
    deltas = assumptions.deltas()

    assert deltas.new_debt_principal == Decimal("270000")  # 350k - 50k deposit - 30k trade-in
    assert deltas.upfront_cash == Decimal("50000")
    assert deltas.monthly_expense_delta == Decimal("4300")  # 1450 + 2200 + 650
    assert deltas.new_debt_term_months == 72


def test_vehicle_purchase_rejects_a_deposit_covering_the_whole_price() -> None:
    assumptions = VehiclePurchaseAssumptions(
        purchase_price=Decimal("100000"),
        deposit=Decimal("100000"),
        annual_rate=Decimal("0.1"),
        term_months=12,
    )
    with pytest.raises(ValueError, match="less than the purchase price"):
        assumptions.validate()


def test_property_purchase_nets_off_the_rent_it_replaces() -> None:
    """Modelling a bond without removing the rent it replaces overstates the move's cost."""
    assumptions = PropertyPurchaseAssumptions(
        purchase_price=Decimal("1800000"),
        deposit=Decimal("200000"),
        annual_rate=Decimal("0.1125"),
        term_months=240,
        transfer_costs=Decimal("65000"),
        rates_monthly=Decimal("1800"),
        levies_monthly=Decimal("1200"),
        insurance_monthly=Decimal("600"),
        maintenance_monthly=Decimal("1500"),
        current_rent_monthly=Decimal("12000"),
    )
    deltas = assumptions.deltas()

    assert deltas.new_debt_principal == Decimal("1600000")
    assert deltas.upfront_cash == Decimal("265000")  # deposit + transfer costs
    # 1800 + 1200 + 600 + 1500 = 5100 of new costs, less 12000 of rent no longer paid.
    assert deltas.monthly_expense_delta == Decimal("-6900")


def test_income_change_moves_income_not_spending() -> None:
    deltas = IncomeChangeAssumptions(monthly_income_delta=Decimal("8000")).deltas()

    assert deltas.monthly_income_delta == Decimal("8000")
    assert deltas.monthly_expense_delta == Decimal("0")
    assert deltas.new_debt_principal == Decimal("0")


def test_income_loss_is_a_negative_delta() -> None:
    deltas = IncomeChangeAssumptions(monthly_income_delta=Decimal("-25000")).deltas()
    assert deltas.monthly_income_delta == Decimal("-25000")


def test_new_loan_brings_cash_in_and_debt_on() -> None:
    """The proceeds land in the account, so upfront cash is negative."""
    deltas = NewLoanAssumptions(
        principal=Decimal("80000"),
        annual_rate=Decimal("0.185"),
        term_months=48,
        initiation_fee=Decimal("1207"),
    ).deltas()

    assert deltas.upfront_cash == Decimal("-80000")
    assert deltas.new_debt_principal == Decimal("81207")  # fee is financed


def test_new_loan_not_received_as_cash_leaves_savings_untouched() -> None:
    deltas = NewLoanAssumptions(
        principal=Decimal("80000"),
        annual_rate=Decimal("0.185"),
        term_months=48,
        proceeds_received=False,
    ).deltas()

    assert deltas.upfront_cash == Decimal("0")
    assert deltas.new_debt_principal == Decimal("80000")


def test_debt_repayment_change_is_not_modelled_as_an_expense() -> None:
    """An extra repayment converts cash into a smaller liability; it is not consumption,
    so it must not reduce net worth through the expense channel.
    """
    deltas = DebtRepaymentChangeAssumptions(
        additional_monthly_payment=Decimal("1500")
    ).deltas()

    assert deltas.additional_debt_repayment == Decimal("1500")
    assert deltas.monthly_expense_delta == Decimal("0")


def test_savings_change_is_a_reduction_in_spending() -> None:
    """Saving more is spending less — counting it as a new outflow would double-count it."""
    deltas = SavingsChangeAssumptions(additional_monthly_saving=Decimal("2000")).deltas()

    assert deltas.monthly_expense_delta == Decimal("-2000")
    assert deltas.upfront_cash == Decimal("0")


def test_one_off_discretionary_expense_leaves_savings_once() -> None:
    deltas = DiscretionaryExpenseAssumptions(amount=Decimal("15000")).deltas()

    assert deltas.upfront_cash == Decimal("15000")
    assert deltas.monthly_expense_delta == Decimal("0")


def test_recurring_discretionary_expense_leaves_savings_every_month() -> None:
    deltas = DiscretionaryExpenseAssumptions(
        amount=Decimal("15000"), is_recurring=True
    ).deltas()

    assert deltas.upfront_cash == Decimal("0")
    assert deltas.monthly_expense_delta == Decimal("15000")


def test_every_assumption_set_round_trips_through_its_stored_form() -> None:
    """Reproducibility (specs/scenarios.md) depends on the stored keys rebuilding the
    same object, so every type's as_dict must name every field its constructor takes.
    """
    from app.services.scenario import build_assumptions
    from app.models.scenario import ScenarioType

    cases = [
        (
            ScenarioType.VEHICLE_PURCHASE,
            VehiclePurchaseAssumptions(
                purchase_price=Decimal("350000"),
                deposit=Decimal("50000"),
                annual_rate=Decimal("0.1175"),
                term_months=72,
            ),
        ),
        (
            ScenarioType.PROPERTY_PURCHASE,
            PropertyPurchaseAssumptions(
                purchase_price=Decimal("1800000"),
                deposit=Decimal("200000"),
                annual_rate=Decimal("0.1125"),
                term_months=240,
            ),
        ),
        (ScenarioType.INCOME_CHANGE, IncomeChangeAssumptions(Decimal("8000"))),
        (
            ScenarioType.NEW_LOAN,
            NewLoanAssumptions(
                principal=Decimal("80000"), annual_rate=Decimal("0.185"), term_months=48
            ),
        ),
        (
            ScenarioType.DEBT_REPAYMENT_CHANGE,
            DebtRepaymentChangeAssumptions(Decimal("1500")),
        ),
        (ScenarioType.SAVINGS_CHANGE, SavingsChangeAssumptions(Decimal("2000"))),
        (
            ScenarioType.DISCRETIONARY_EXPENSE,
            DiscretionaryExpenseAssumptions(Decimal("15000"), is_recurring=True),
        ),
    ]

    for scenario_type, original in cases:
        rebuilt = build_assumptions(scenario_type, original.as_dict())
        assert rebuilt == original, scenario_type
        assert rebuilt.deltas() == original.deltas(), scenario_type
