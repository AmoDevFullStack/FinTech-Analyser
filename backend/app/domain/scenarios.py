"""Scenario assumptions and the deltas they imply. See specs/scenarios.md.

Every scenario type reduces to the same four questions the projection engine can answer:
what cash leaves today, what changes monthly income, what changes monthly spending, and
what new debt is taken on. This module does that reduction — it is arithmetic over money
(a financed principal is a purchase price less a deposit less a trade-in), so it belongs
in the domain, not in the service that reads the assumptions out of the database.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ScenarioDeltas:
    """What a scenario does to a position, in the terms `project_forward` understands.

    `upfront_cash` is money that leaves liquid savings at t0 — a deposit, transfer costs,
    a one-off purchase. `new_debt_*` describe a facility taken on at t0; a zero principal
    means the scenario adds no debt.
    """

    upfront_cash: Decimal = Decimal("0")
    monthly_income_delta: Decimal = Decimal("0")
    monthly_expense_delta: Decimal = Decimal("0")
    new_debt_principal: Decimal = Decimal("0")
    new_debt_annual_rate: Decimal = Decimal("0")
    new_debt_term_months: int = 0
    additional_debt_repayment: Decimal = Decimal("0")


class ScenarioAssumptions(ABC):
    """Base for every scenario type's typed assumption set.

    `as_dict` is the storage form (`ScenarioAssumption` key-value rows, all strings, per
    docs/database.md), and `deltas` is the computation form. Keeping both on one object is
    what makes a stored scenario reproducible: the same keys always rebuild the same
    object, which always produces the same deltas.
    """

    @abstractmethod
    def as_dict(self) -> dict[str, str]: ...

    @abstractmethod
    def deltas(self) -> ScenarioDeltas: ...

    def validate(self) -> None:
        """Raise `ValueError` if the assumption set cannot produce a meaningful run."""
        return None


@dataclass(frozen=True, slots=True)
class VehiclePurchaseAssumptions(ScenarioAssumptions):
    """specs/scenarios.md's worked example: price, deposit, rate, term, running costs."""

    purchase_price: Decimal
    deposit: Decimal = Decimal("0")
    annual_rate: Decimal = Decimal("0")
    term_months: int = 0
    insurance_monthly: Decimal = Decimal("0")
    fuel_monthly: Decimal = Decimal("0")
    maintenance_monthly: Decimal = Decimal("0")
    trade_in_value: Decimal = Decimal("0")

    @property
    def financed_principal(self) -> Decimal:
        return self.purchase_price - self.deposit - self.trade_in_value

    @property
    def recurring_monthly_cost(self) -> Decimal:
        return self.insurance_monthly + self.fuel_monthly + self.maintenance_monthly

    def validate(self) -> None:
        if self.purchase_price <= 0:
            raise ValueError(f"purchase_price must be positive, got {self.purchase_price}")
        if self.financed_principal <= 0:
            raise ValueError(
                "Deposit and trade-in together must be less than the purchase price."
            )
        if self.term_months < 1:
            raise ValueError(f"term_months must be >= 1, got {self.term_months}")

    def as_dict(self) -> dict[str, str]:
        return {
            "purchase_price": str(self.purchase_price),
            "deposit": str(self.deposit),
            "annual_rate": str(self.annual_rate),
            "term_months": str(self.term_months),
            "insurance_monthly": str(self.insurance_monthly),
            "fuel_monthly": str(self.fuel_monthly),
            "maintenance_monthly": str(self.maintenance_monthly),
            "trade_in_value": str(self.trade_in_value),
        }

    def deltas(self) -> ScenarioDeltas:
        return ScenarioDeltas(
            upfront_cash=self.deposit,
            monthly_expense_delta=self.recurring_monthly_cost,
            new_debt_principal=self.financed_principal,
            new_debt_annual_rate=self.annual_rate,
            new_debt_term_months=self.term_months,
        )


@dataclass(frozen=True, slots=True)
class PropertyPurchaseAssumptions(ScenarioAssumptions):
    """A purchase or a move. Rent currently paid stops, which is why it is an input:
    modelling a bond without removing the rent it replaces overstates the cost of moving
    by the whole rent.
    """

    purchase_price: Decimal
    deposit: Decimal = Decimal("0")
    annual_rate: Decimal = Decimal("0")
    term_months: int = 0
    transfer_costs: Decimal = Decimal("0")
    rates_monthly: Decimal = Decimal("0")
    levies_monthly: Decimal = Decimal("0")
    insurance_monthly: Decimal = Decimal("0")
    maintenance_monthly: Decimal = Decimal("0")
    current_rent_monthly: Decimal = Decimal("0")

    @property
    def financed_principal(self) -> Decimal:
        return self.purchase_price - self.deposit

    @property
    def recurring_monthly_cost(self) -> Decimal:
        return (
            self.rates_monthly
            + self.levies_monthly
            + self.insurance_monthly
            + self.maintenance_monthly
            - self.current_rent_monthly
        )

    def validate(self) -> None:
        if self.purchase_price <= 0:
            raise ValueError(f"purchase_price must be positive, got {self.purchase_price}")
        if self.financed_principal <= 0:
            raise ValueError("Deposit must be less than the purchase price.")
        if self.term_months < 1:
            raise ValueError(f"term_months must be >= 1, got {self.term_months}")
        if self.current_rent_monthly < 0:
            raise ValueError(
                f"current_rent_monthly must be >= 0, got {self.current_rent_monthly}"
            )

    def as_dict(self) -> dict[str, str]:
        return {
            "purchase_price": str(self.purchase_price),
            "deposit": str(self.deposit),
            "annual_rate": str(self.annual_rate),
            "term_months": str(self.term_months),
            "transfer_costs": str(self.transfer_costs),
            "rates_monthly": str(self.rates_monthly),
            "levies_monthly": str(self.levies_monthly),
            "insurance_monthly": str(self.insurance_monthly),
            "maintenance_monthly": str(self.maintenance_monthly),
            "current_rent_monthly": str(self.current_rent_monthly),
        }

    def deltas(self) -> ScenarioDeltas:
        return ScenarioDeltas(
            upfront_cash=self.deposit + self.transfer_costs,
            monthly_expense_delta=self.recurring_monthly_cost,
            new_debt_principal=self.financed_principal,
            new_debt_annual_rate=self.annual_rate,
            new_debt_term_months=self.term_months,
        )


@dataclass(frozen=True, slots=True)
class IncomeChangeAssumptions(ScenarioAssumptions):
    """A raise, a new job, a reduction in hours, or losing an income entirely.

    Stated as a delta rather than a new absolute so the scenario stays meaningful against
    a snapshot whose income was measured from transactions and may not match the user's
    idea of their salary to the cent.
    """

    monthly_income_delta: Decimal
    monthly_expense_delta: Decimal = Decimal("0")

    def as_dict(self) -> dict[str, str]:
        return {
            "monthly_income_delta": str(self.monthly_income_delta),
            "monthly_expense_delta": str(self.monthly_expense_delta),
        }

    def deltas(self) -> ScenarioDeltas:
        return ScenarioDeltas(
            monthly_income_delta=self.monthly_income_delta,
            monthly_expense_delta=self.monthly_expense_delta,
        )


@dataclass(frozen=True, slots=True)
class NewLoanAssumptions(ScenarioAssumptions):
    """Borrowing, where the money borrowed is received as cash rather than spent on an
    asset. `upfront_cash` is negative: the principal arrives in the bank account.
    """

    principal: Decimal
    annual_rate: Decimal = Decimal("0")
    term_months: int = 0
    initiation_fee: Decimal = Decimal("0")
    monthly_cost: Decimal = Decimal("0")
    proceeds_received: bool = True

    def validate(self) -> None:
        if self.principal <= 0:
            raise ValueError(f"principal must be positive, got {self.principal}")
        if self.term_months < 1:
            raise ValueError(f"term_months must be >= 1, got {self.term_months}")

    def as_dict(self) -> dict[str, str]:
        return {
            "principal": str(self.principal),
            "annual_rate": str(self.annual_rate),
            "term_months": str(self.term_months),
            "initiation_fee": str(self.initiation_fee),
            "monthly_cost": str(self.monthly_cost),
            "proceeds_received": "true" if self.proceeds_received else "false",
        }

    def deltas(self) -> ScenarioDeltas:
        cash_in = self.principal if self.proceeds_received else Decimal("0")
        return ScenarioDeltas(
            upfront_cash=-cash_in,
            monthly_expense_delta=self.monthly_cost,
            new_debt_principal=self.principal + self.initiation_fee,
            new_debt_annual_rate=self.annual_rate,
            new_debt_term_months=self.term_months,
        )


@dataclass(frozen=True, slots=True)
class DebtRepaymentChangeAssumptions(ScenarioAssumptions):
    """Paying more (or less) toward existing debt every month.

    This does not move through `monthly_expense_delta`: an extra repayment is not
    consumption, it converts cash into a smaller liability. It is carried as
    `additional_debt_repayment`, which the caller applies to the existing debt set's
    amortisation, so the effect shows up as a shorter schedule and less interest rather
    than as money vanishing.
    """

    additional_monthly_payment: Decimal

    def validate(self) -> None:
        if self.additional_monthly_payment == 0:
            raise ValueError("additional_monthly_payment must be non-zero to model a change.")

    def as_dict(self) -> dict[str, str]:
        return {"additional_monthly_payment": str(self.additional_monthly_payment)}

    def deltas(self) -> ScenarioDeltas:
        return ScenarioDeltas(additional_debt_repayment=self.additional_monthly_payment)


@dataclass(frozen=True, slots=True)
class SavingsChangeAssumptions(ScenarioAssumptions):
    """Saving more each month, funded by spending less.

    Carried as a negative expense delta, because that is what saving more actually is in
    this model: money not spent stays in the savings balance the projection accumulates.
    Treating it as a new outflow would count it twice — once leaving cash flow and once
    arriving in savings.
    """

    additional_monthly_saving: Decimal

    def validate(self) -> None:
        if self.additional_monthly_saving == 0:
            raise ValueError("additional_monthly_saving must be non-zero to model a change.")

    def as_dict(self) -> dict[str, str]:
        return {"additional_monthly_saving": str(self.additional_monthly_saving)}

    def deltas(self) -> ScenarioDeltas:
        return ScenarioDeltas(monthly_expense_delta=-self.additional_monthly_saving)


@dataclass(frozen=True, slots=True)
class DiscretionaryExpenseAssumptions(ScenarioAssumptions):
    """A holiday, a wedding, school fees — one-off or recurring.

    The AI CFO's worked example ("Can I afford a R15,000 holiday in December?") runs
    through this type.
    """

    amount: Decimal
    is_recurring: bool = False

    def validate(self) -> None:
        if self.amount <= 0:
            raise ValueError(f"amount must be positive, got {self.amount}")

    def as_dict(self) -> dict[str, str]:
        return {
            "amount": str(self.amount),
            "is_recurring": "true" if self.is_recurring else "false",
        }

    def deltas(self) -> ScenarioDeltas:
        if self.is_recurring:
            return ScenarioDeltas(monthly_expense_delta=self.amount)
        return ScenarioDeltas(upfront_cash=self.amount)
