from decimal import Decimal

import pytest

from app.domain.net_worth import credit_utilisation, net_worth


def test_net_worth_matches_dashboard_worked_example() -> None:
    """Reference: the published dashboard mock — net worth R412,500 from assets against
    total debt R287,300, i.e. assets sum to R699,800.
    """
    result = net_worth(
        asset_values=[Decimal("699800.00")],
        debt_balances=[Decimal("287300.00")],
    )
    assert result == Decimal("412500.00")


def test_net_worth_sums_multiple_accounts_and_debts() -> None:
    result = net_worth(
        asset_values=[Decimal("100.50"), Decimal("200.25")],
        debt_balances=[Decimal("50.00"), Decimal("25.75")],
    )
    assert result == Decimal("225.00")


def test_net_worth_rejects_negative_debt_balance() -> None:
    with pytest.raises(ValueError):
        net_worth(asset_values=[Decimal("100")], debt_balances=[Decimal("-1")])


def test_credit_utilisation() -> None:
    assert credit_utilisation(
        balance_owed=Decimal("4500"), credit_limit=Decimal("18000")
    ) == Decimal("0.250000")


def test_credit_utilisation_rejects_zero_limit() -> None:
    with pytest.raises(ValueError):
        credit_utilisation(balance_owed=Decimal("1"), credit_limit=Decimal("0"))
