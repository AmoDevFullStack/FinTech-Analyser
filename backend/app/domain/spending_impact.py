"""What a set of new transactions does to the figures a user reads. Pure and deterministic.

An import is not an act of bookkeeping, it is a change to every derived number on the
dashboard at once. Adding one R14,500 rent debit order moves the month's essential
spending, the surplus, the cash-flow margin, the savings rate's denominator, and the
emergency fund's monthly requirement — and therefore how many months of cover the same
untouched savings balance represents. specs/dashboard.md and specs/financial-health.md
each describe those figures in isolation; this engine is where the arithmetic of "what
changed, and by how much" lives, so that the answer shown before a commit is produced by
the same code as the answer shown after it.

It computes only the arithmetic. Which transactions are in the "added" set, whether the
forecast is now stale, and whether a risk flag fires are decisions for
app/services/spending_insight.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.domain.cash_flow import (
    cash_flow_margin,
    cash_flow_summary,
    debt_to_income,
    savings_rate,
)
from app.domain.emergency_fund import emergency_fund_months

CENTS = Decimal("0.01")
RATE_PLACES = Decimal("0.000001")


def _to_cents(value: Decimal) -> Decimal:
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)


def _to_rate(value: Decimal) -> Decimal:
    return value.quantize(RATE_PLACES, rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class MonthlyFlows:
    """One month of money movement, grouped the way the health engine consumes it.

    Every field is a positive magnitude except `income`, which is signed so that a salary
    reversal reduces income rather than adding to it — the same convention
    `PositionService.category_kind_sums` already applies when it reads these out of the
    transaction table.
    """

    income: Decimal
    essential: Decimal
    discretionary: Decimal
    saving: Decimal
    debt_service: Decimal


ZERO_FLOWS = MonthlyFlows(
    income=Decimal("0.00"),
    essential=Decimal("0.00"),
    discretionary=Decimal("0.00"),
    saving=Decimal("0.00"),
    debt_service=Decimal("0.00"),
)


def combine_flows(*, base: MonthlyFlows, added: MonthlyFlows) -> MonthlyFlows:
    """Add two months of flows field by field.

    Formula:
        Field-wise addition, each result quantised to two places.

    Assumptions:
        - Both arguments describe the same month. Adding a month of flows to a quarter of
          flows is a caller error this engine cannot detect.

    Rounding:
        Two places, ROUND_HALF_UP, per field.

    Raises:
        Nothing.
    """
    return MonthlyFlows(
        income=_to_cents(base.income + added.income),
        essential=_to_cents(base.essential + added.essential),
        discretionary=_to_cents(base.discretionary + added.discretionary),
        saving=_to_cents(base.saving + added.saving),
        debt_service=_to_cents(base.debt_service + added.debt_service),
    )


@dataclass(frozen=True, slots=True)
class MetricChange:
    """One figure, before and after, with the movement between them.

    `unit` is carried so the presentation layer never has to infer from the name whether
    0.12 is twelve cents, twelve percent, or a tenth of a month. It is one of "money",
    "rate", or "months".
    """

    name: str
    unit: str
    before: Decimal
    after: Decimal
    delta: Decimal

    @property
    def is_material(self) -> bool:
        """Whether the figure moved at all. A zero delta is reported, not hidden — "this
        import changed nothing here" is an answer a user asked for."""
        return self.delta != 0


@dataclass(frozen=True, slots=True)
class SpendingImpact:
    """The full before/after picture for one set of added transactions."""

    before: MonthlyFlows
    after: MonthlyFlows
    added: MonthlyFlows
    changes: tuple[MetricChange, ...]

    def change(self, name: str) -> MetricChange | None:
        return next((c for c in self.changes if c.name == name), None)


def _safe_margin(*, remaining: Decimal, income: Decimal) -> Decimal:
    """Cash-flow margin, defined as zero when there is no income to divide by.

    `cash_flow_margin` raises on non-positive income by design — a margin against no
    income is not a meaningful ratio. An impact preview still has to render for a user
    whose first import has not yet included a salary, so the undefined case is reported as
    zero here rather than propagated as an exception. The caller can tell the two apart by
    reading the income figure, which is in the same report.
    """
    if income <= 0:
        return Decimal("0.000000")
    return cash_flow_margin(remaining=remaining, income=income)


def _safe_savings_rate(*, saved: Decimal, income: Decimal) -> Decimal:
    if income <= 0 or saved < 0:
        return Decimal("0.000000")
    return savings_rate(saved=saved, income=income)


def _safe_debt_to_income(*, monthly_debt_service: Decimal, monthly_income: Decimal) -> Decimal:
    if monthly_income <= 0 or monthly_debt_service < 0:
        return Decimal("0.000000")
    return debt_to_income(
        monthly_debt_service=monthly_debt_service, monthly_income=monthly_income
    )


def spending_impact(
    *,
    before: MonthlyFlows,
    added: MonthlyFlows,
    liquid_savings_before: Decimal,
    liquid_savings_after: Decimal,
) -> SpendingImpact:
    """Every derived figure a set of added transactions moves, before and after.

    Formula:
        after = before + added, field by field, then for each side:
            remaining            = income - essential - discretionary      (cash_flow.py)
            cash_flow_margin     = remaining / income
            savings_rate         = saving / income
            debt_to_income       = debt_service / income
            emergency_fund_months = liquid_savings / essential
        The reported delta for each is after - before.

    Assumptions:
        - `before` is the month as it already stands and `added` is what the import or the
          new transaction contributes to that same month. Passing a partial month as
          `before` produces a partial-month answer, which is the honest result — the
          caller chooses the window.
        - Debt service here is what was actually paid in the month, from categorised
          transactions. `FinancialHealthService._monthly_debt_service` deliberately prefers
          contractual minimums over this when any `Debt` records exist, so a debt-to-income
          figure from this engine can differ from the stored health assessment's. That is
          not a discrepancy to reconcile: one answers "what did this import change about
          what you paid", the other "what are you contractually committed to".
        - Emergency-fund cover moves on an import even when no savings balance changed,
          because the denominator is essential spending. That is the point of reporting it.
        - Ratios against zero income are reported as zero rather than raising; see
          `_safe_margin`.

    Rounding:
        Money to two places, ratios and month counts to six, all ROUND_HALF_UP, applied by
        the engines each figure comes from.

    Raises:
        ValueError: if either liquid savings figure is negative, or if any non-income field
            of `before` or `added` is negative. A negative magnitude means the caller
            mixed up the sign convention, and silently accepting it would produce a
            plausible wrong number.
    """
    for label, flows in (("before", before), ("added", added)):
        for field in ("essential", "discretionary", "saving", "debt_service"):
            value = getattr(flows, field)
            if value < 0:
                raise ValueError(f"{label}.{field} must be >= 0, got {value}")
    if liquid_savings_before < 0:
        raise ValueError(f"liquid_savings_before must be >= 0, got {liquid_savings_before}")
    if liquid_savings_after < 0:
        raise ValueError(f"liquid_savings_after must be >= 0, got {liquid_savings_after}")

    after = combine_flows(base=before, added=added)

    before_cash_flow = cash_flow_summary(
        income=max(before.income, Decimal("0")),
        essential=before.essential,
        discretionary=before.discretionary,
    )
    after_cash_flow = cash_flow_summary(
        income=max(after.income, Decimal("0")),
        essential=after.essential,
        discretionary=after.discretionary,
    )

    rows: list[tuple[str, str, Decimal, Decimal]] = [
        ("monthly_income", "money", before.income, after.income),
        ("monthly_essential", "money", before.essential, after.essential),
        ("monthly_discretionary", "money", before.discretionary, after.discretionary),
        ("monthly_saving", "money", before.saving, after.saving),
        ("monthly_debt_service", "money", before.debt_service, after.debt_service),
        (
            "monthly_cash_flow",
            "money",
            before_cash_flow.remaining,
            after_cash_flow.remaining,
        ),
        ("liquid_savings", "money", liquid_savings_before, liquid_savings_after),
        (
            "cash_flow_margin",
            "rate",
            _safe_margin(remaining=before_cash_flow.remaining, income=before.income),
            _safe_margin(remaining=after_cash_flow.remaining, income=after.income),
        ),
        (
            "savings_rate",
            "rate",
            _safe_savings_rate(saved=before.saving, income=before.income),
            _safe_savings_rate(saved=after.saving, income=after.income),
        ),
        (
            "debt_to_income",
            "rate",
            _safe_debt_to_income(
                monthly_debt_service=before.debt_service, monthly_income=before.income
            ),
            _safe_debt_to_income(
                monthly_debt_service=after.debt_service, monthly_income=after.income
            ),
        ),
        (
            "emergency_fund_months",
            "months",
            emergency_fund_months(
                liquid_savings=liquid_savings_before,
                monthly_essential_spending=before.essential,
            ),
            emergency_fund_months(
                liquid_savings=liquid_savings_after,
                monthly_essential_spending=after.essential,
            ),
        ),
    ]

    changes = tuple(
        MetricChange(
            name=name,
            unit=unit,
            before=_to_cents(before_value) if unit == "money" else _to_rate(before_value),
            after=_to_cents(after_value) if unit == "money" else _to_rate(after_value),
            delta=(
                _to_cents(after_value - before_value)
                if unit == "money"
                else _to_rate(after_value - before_value)
            ),
        )
        for name, unit, before_value, after_value in rows
    )

    return SpendingImpact(before=before, after=after, added=added, changes=changes)
