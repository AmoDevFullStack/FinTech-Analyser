"""Net worth arithmetic. See docs/database.md §4 (PositionSnapshot) and specs/accounts.md."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

CENTS = Decimal("0.01")


def net_worth(*, asset_values: list[Decimal], debt_balances: list[Decimal]) -> Decimal:
    """Sum assets minus debts.

    Formula:
        net_worth = sum(asset_values) - sum(debt_balances)

    Assumptions:
        - `asset_values` includes every account balance that is a holding (transactional,
          savings, investment, manual_asset), already excluding archived accounts per
          specs/accounts.md.
        - `debt_balances` are positive figures representing amounts owed; credit-card
          balances arrive here as positive even though they are stored negative on the
          account row (docs/database.md §3) — the caller performs that sign conversion,
          not this function, so this engine never has to know about storage convention.

    Rounding:
        Result quantised to two places with ROUND_HALF_UP.

    Raises:
        ValueError: if any debt balance is negative.
    """
    for balance in debt_balances:
        if balance < 0:
            raise ValueError(f"debt_balances must all be >= 0, got {balance}")

    total = sum(asset_values, Decimal("0")) - sum(debt_balances, Decimal("0"))
    return total.quantize(CENTS, rounding=ROUND_HALF_UP)


def credit_utilisation(*, balance_owed: Decimal, credit_limit: Decimal) -> Decimal:
    """Utilisation of a credit facility.

    Formula:
        utilisation = balance_owed / credit_limit

    Rounding:
        Quantised to six places (NUMERIC(9,6)), ROUND_HALF_UP.

    Raises:
        ValueError: if balance_owed < 0 or credit_limit <= 0.
    """
    if balance_owed < 0:
        raise ValueError(f"balance_owed must be >= 0, got {balance_owed}")
    if credit_limit <= 0:
        raise ValueError(f"credit_limit must be > 0, got {credit_limit}")

    return (balance_owed / credit_limit).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
