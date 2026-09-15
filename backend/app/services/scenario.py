"""Scenario orchestration. See specs/scenarios.md and ADR-005.

This service loads the snapshot and assumptions and calls domain engines; it does not
calculate. Every figure in a `ScenarioResult` traces back to `app/domain/`.

Engine version history:
    1.0.0 — vehicle purchase only; projections ignored existing debt service.
    1.1.0 — all seven scenario types (app/domain/scenarios.py); existing debts amortise
            through the horizon in both the baseline and the scenario, so a comparison is
            no longer distorted by debt repayments being absent from both sides.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from app.core.db import DbSession
from app.core.errors import NotFoundError, SemanticError, ValidationError
from app.domain.amortisation import AmortisationPeriod, amortisation_schedule
from app.domain.cash_flow import debt_to_income
from app.domain.debt_payoff import DebtInput, avalanche_schedule
from app.domain.emergency_fund import emergency_fund_months
from app.domain.projection import FinancialPosition, PeriodProjection, project_forward
from app.domain.scenarios import (
    DebtRepaymentChangeAssumptions,
    DiscretionaryExpenseAssumptions,
    IncomeChangeAssumptions,
    NewLoanAssumptions,
    PropertyPurchaseAssumptions,
    SavingsChangeAssumptions,
    ScenarioAssumptions,
    ScenarioDeltas,
    VehiclePurchaseAssumptions,
)
from app.models.scenario import (
    Scenario,
    ScenarioAssumption,
    ScenarioResult,
    ScenarioStatus,
    ScenarioType,
)
from app.repositories.debt import DebtRepository
from app.repositories.position_snapshot import PositionSnapshotRepository
from app.repositories.scenario import ScenarioRepository
from app.services.position import PositionService

ENGINE_VERSION = "1.1.0"
DEFAULT_HORIZON_MONTHS = 60
RE_BASELINE_AFTER_DAYS = 30

_ASSUMPTION_TYPES: dict[ScenarioType, type[ScenarioAssumptions]] = {
    ScenarioType.VEHICLE_PURCHASE: VehiclePurchaseAssumptions,
    ScenarioType.PROPERTY_PURCHASE: PropertyPurchaseAssumptions,
    ScenarioType.INCOME_CHANGE: IncomeChangeAssumptions,
    ScenarioType.NEW_LOAN: NewLoanAssumptions,
    ScenarioType.DEBT_REPAYMENT_CHANGE: DebtRepaymentChangeAssumptions,
    ScenarioType.SAVINGS_CHANGE: SavingsChangeAssumptions,
    ScenarioType.DISCRETIONARY_EXPENSE: DiscretionaryExpenseAssumptions,
}

_DECIMAL_FIELDS = {
    "purchase_price",
    "deposit",
    "annual_rate",
    "insurance_monthly",
    "fuel_monthly",
    "maintenance_monthly",
    "trade_in_value",
    "transfer_costs",
    "rates_monthly",
    "levies_monthly",
    "current_rent_monthly",
    "monthly_income_delta",
    "monthly_expense_delta",
    "principal",
    "initiation_fee",
    "monthly_cost",
    "additional_monthly_payment",
    "additional_monthly_saving",
    "amount",
}
_INT_FIELDS = {"term_months"}
_BOOL_FIELDS = {"is_recurring", "proceeds_received"}


def build_assumptions(
    scenario_type: ScenarioType, values: Mapping[str, str | Decimal | int | bool]
) -> ScenarioAssumptions:
    """Rebuild a typed assumption set from stored (or submitted) key-value pairs.

    One conversion table for both paths — storage and API — so a scenario rebuilt from
    the database is the same object that was run when it was created. That identity is
    what specs/scenarios.md's reproducibility requirement rests on.
    """
    assumption_type = _ASSUMPTION_TYPES[scenario_type]
    fields = {f.name for f in assumption_type.__dataclass_fields__.values()}  # type: ignore[attr-defined]

    kwargs: dict[str, object] = {}
    for key, raw in values.items():
        if key not in fields:
            continue
        if key in _DECIMAL_FIELDS:
            kwargs[key] = Decimal(str(raw))
        elif key in _INT_FIELDS:
            kwargs[key] = int(raw)
        elif key in _BOOL_FIELDS:
            kwargs[key] = str(raw).lower() == "true" if not isinstance(raw, bool) else raw
        else:
            kwargs[key] = raw

    missing = [
        name
        for name, field in assumption_type.__dataclass_fields__.items()  # type: ignore[attr-defined]
        if name not in kwargs and field.default is field.default_factory is None
    ]
    if missing:
        raise ValidationError(f"Missing assumption: {missing[0]}")

    try:
        return assumption_type(**kwargs)  # type: ignore[arg-type]
    except TypeError as exc:
        raise ValidationError(f"Invalid assumptions for {scenario_type.value}: {exc}") from exc


class ScenarioService:
    def __init__(self, session: DbSession) -> None:
        self._session = session
        self._scenarios = ScenarioRepository(session)
        self._snapshots = PositionSnapshotRepository(session)
        self._debts = DebtRepository(session)
        self._position = PositionService(session)

    def create(
        self,
        *,
        user_id: UUID,
        name: str,
        description: str | None,
        scenario_type: ScenarioType,
        assumptions: ScenarioAssumptions,
    ) -> Scenario:
        try:
            assumptions.validate()
        except ValueError as exc:
            raise SemanticError(str(exc)) from exc

        snapshot = self._position.capture_snapshot(user_id=user_id)

        scenario = Scenario(
            user_id=user_id,
            name=name,
            description=description,
            scenario_type=scenario_type,
            snapshot_id=snapshot.id,
            status=ScenarioStatus.DRAFT,
        )
        self._scenarios.add(scenario)
        self._scenarios.add_assumptions(
            [
                ScenarioAssumption(scenario_id=scenario.id, key=key, value=value)
                for key, value in assumptions.as_dict().items()
            ]
        )
        self._session.commit()
        return scenario

    def create_vehicle_purchase(
        self,
        *,
        user_id: UUID,
        name: str,
        description: str | None,
        assumptions: VehiclePurchaseAssumptions,
    ) -> Scenario:
        """Kept as a named entry point: the vehicle purchase is the worked example in
        specs/scenarios.md and the path the e2e test drives.
        """
        return self.create(
            user_id=user_id,
            name=name,
            description=description,
            scenario_type=ScenarioType.VEHICLE_PURCHASE,
            assumptions=assumptions,
        )

    def _existing_debt_schedule(
        self, *, user_id: UUID, additional_monthly_payment: Decimal = Decimal("0")
    ) -> tuple[AmortisationPeriod, ...]:
        """The user's existing debt set, amortised as one monthly series.

        Uses the avalanche ordering from app/domain/debt_payoff.py because a surplus has
        to be allocated somehow and avalanche is the deterministic, interest-minimising
        choice; with no surplus (the default) every ordering produces the same totals, so
        the choice only matters when `additional_monthly_payment` is non-zero.

        Returns an empty tuple when the user has no `Debt` rows, which makes the caller
        fall back to `monthly_debt_service` — see project_forward's assumptions.
        """
        debts = self._debts.list_for_user(user_id=user_id)
        if not debts:
            return ()

        inputs = [
            DebtInput(
                id=str(d.id),
                current_balance=d.current_balance,
                annual_rate=d.annual_rate,
                minimum_payment=(
                    d.instalment if d.instalment is not None else d.minimum_payment
                ),
            )
            for d in debts
            if d.current_balance > 0
        ]
        if not inputs:
            return ()

        total_monthly = sum((d.minimum_payment for d in inputs), Decimal("0")) + max(
            Decimal("0"), additional_monthly_payment
        )
        result = avalanche_schedule(inputs, total_monthly)
        return tuple(
            AmortisationPeriod(
                period=p.month,
                opening_balance=p.total_balance + p.principal,
                instalment=p.payment,
                interest=p.interest,
                principal=p.principal,
                closing_balance=p.total_balance,
            )
            for p in result.schedule
        )

    def run(self, scenario_id: UUID, *, user_id: UUID) -> ScenarioResult:
        scenario = self._scenarios.get_for_user(scenario_id, user_id=user_id)
        if scenario is None:
            raise NotFoundError("No scenario with that identifier exists for this user.")

        snapshot = self._snapshots.get_for_user(scenario.snapshot_id, user_id=user_id)
        if snapshot is None:
            raise NotFoundError("The scenario's position snapshot no longer exists.")

        assumption_rows = self._scenarios.assumptions_for(scenario.id)
        assumption_values = {row.key: row.value for row in assumption_rows}
        assumptions = build_assumptions(scenario.scenario_type, assumption_values)
        deltas = assumptions.deltas()

        position = FinancialPosition(
            as_of=snapshot.captured_at.date(),
            liquid_savings=snapshot.liquid_savings,
            total_debt=snapshot.total_debt,
            net_worth=snapshot.net_worth,
            monthly_income=snapshot.monthly_income,
            monthly_essential=snapshot.monthly_essential,
            monthly_discretionary=snapshot.monthly_discretionary,
        )

        baseline_debt_schedule = self._existing_debt_schedule(user_id=user_id)
        baseline_debt_service = self._flat_debt_service(user_id=user_id, schedule=baseline_debt_schedule)
        baseline_periods = project_forward(
            position=position,
            horizon_months=DEFAULT_HORIZON_MONTHS,
            monthly_debt_service=baseline_debt_service,
            existing_debt_schedule=baseline_debt_schedule,
        )

        new_debt_schedule: tuple[AmortisationPeriod, ...] = ()
        if deltas.new_debt_principal > 0 and deltas.new_debt_term_months > 0:
            new_debt_schedule = tuple(
                amortisation_schedule(
                    principal=deltas.new_debt_principal,
                    annual_rate=deltas.new_debt_annual_rate,
                    term_months=deltas.new_debt_term_months,
                )
            )

        scenario_debt_schedule = (
            self._existing_debt_schedule(
                user_id=user_id,
                additional_monthly_payment=deltas.additional_debt_repayment,
            )
            if deltas.additional_debt_repayment
            else baseline_debt_schedule
        )
        if scenario_debt_schedule:
            # The extra repayment is already inside the schedule's monthly budget, so
            # adding it again here would take it out of cash flow twice.
            scenario_debt_service = Decimal("0")
        else:
            scenario_debt_service = self._flat_debt_service(
                user_id=user_id, schedule=()
            ) + max(Decimal("0"), deltas.additional_debt_repayment)

        scenario_position = FinancialPosition(
            as_of=position.as_of,
            liquid_savings=position.liquid_savings - deltas.upfront_cash,
            total_debt=position.total_debt,
            net_worth=position.net_worth - deltas.upfront_cash,
            monthly_income=position.monthly_income,
            monthly_essential=position.monthly_essential,
            monthly_discretionary=position.monthly_discretionary,
        )
        scenario_periods = project_forward(
            position=scenario_position,
            horizon_months=DEFAULT_HORIZON_MONTHS,
            monthly_income_delta=deltas.monthly_income_delta,
            monthly_expense_delta=deltas.monthly_expense_delta,
            monthly_debt_service=scenario_debt_service,
            existing_debt_schedule=scenario_debt_schedule,
            new_debt_schedule=new_debt_schedule,
        )

        impact = self._impact(
            position=position,
            scenario_position=scenario_position,
            baseline_periods=baseline_periods,
            scenario_periods=scenario_periods,
            baseline_debt_service=(
                baseline_debt_schedule[0].instalment
                if baseline_debt_schedule
                else baseline_debt_service
            ),
            new_debt_schedule=new_debt_schedule,
            deltas=deltas,
        )

        assumptions_hash = hashlib.sha256(
            json.dumps(assumption_values, sort_keys=True).encode("utf-8")
        ).hexdigest()

        result = ScenarioResult(
            scenario_id=scenario.id,
            computed_at=datetime.now(UTC),
            engine_version=ENGINE_VERSION,
            assumptions_hash=assumptions_hash,
            impact=impact,
            periods=[_period_dict(p) for p in scenario_periods],
            baseline_periods=[_period_dict(p) for p in baseline_periods],
        )
        self._scenarios.add_result(result)
        scenario.status = ScenarioStatus.RUN
        self._session.commit()
        return result

    def _flat_debt_service(
        self, *, user_id: UUID, schedule: tuple[AmortisationPeriod, ...]
    ) -> Decimal:
        """The fallback monthly debt service for a user whose debts have no schedule.

        Zero when a schedule exists — passing both would double-count, since
        project_forward prefers the schedule.
        """
        if schedule:
            return Decimal("0")
        debts = self._debts.list_for_user(user_id=user_id)
        return sum(
            (
                (d.instalment if d.instalment is not None else d.minimum_payment)
                for d in debts
            ),
            Decimal("0"),
        )

    def _impact(
        self,
        *,
        position: FinancialPosition,
        scenario_position: FinancialPosition,
        baseline_periods: list[PeriodProjection],
        scenario_periods: list[PeriodProjection],
        baseline_debt_service: Decimal,
        new_debt_schedule: tuple[AmortisationPeriod, ...],
        deltas: ScenarioDeltas,
    ) -> dict:
        first_month_cash_flow_delta = scenario_periods[0].cash_flow - baseline_periods[0].cash_flow
        disposable_income_after = scenario_periods[0].cash_flow

        # The first period's contractual debt service, whether that came from the
        # amortised schedule or the flat fallback — the caller resolved which.
        existing_service = baseline_debt_service
        new_instalment = new_debt_schedule[0].instalment if new_debt_schedule else Decimal("0")

        if position.monthly_income > 0:
            dti_before = debt_to_income(
                monthly_debt_service=max(Decimal("0"), existing_service),
                monthly_income=position.monthly_income,
            )
            dti_after = debt_to_income(
                monthly_debt_service=max(Decimal("0"), existing_service)
                + new_instalment
                + max(Decimal("0"), deltas.additional_debt_repayment),
                monthly_income=position.monthly_income + deltas.monthly_income_delta,
            ) if position.monthly_income + deltas.monthly_income_delta > 0 else Decimal("0")
        else:
            dti_before = Decimal("0")
            dti_after = Decimal("0")

        # Debt free = the first projected month where nothing is outstanding, across both
        # the existing debt set and any new facility. With existing debts amortised
        # (engine 1.1.0) this is the true all-debts-zero date, not just the new loan's.
        debt_free_period = next((p for p in scenario_periods if p.debt <= 0), None)

        return {
            "monthly_cash_flow_delta": str(first_month_cash_flow_delta),
            "disposable_income_after": str(disposable_income_after),
            "debt_to_income_before": str(dti_before),
            "debt_to_income_after": str(dti_after),
            "emergency_fund_months_after": str(
                _emergency_fund_months_after(scenario_position, scenario_periods[0])
            ),
            "net_worth_at_60_months": str(scenario_periods[-1].net_worth),
            "net_worth_at_60_months_baseline": str(baseline_periods[-1].net_worth),
            "debt_free_date": debt_free_period.month if debt_free_period else None,
        }

    def rebaseline(self, scenario_id: UUID, *, user_id: UUID) -> ScenarioResult:
        """Capture a fresh snapshot and re-run — specs/scenarios.md acceptance criteria."""
        scenario = self._scenarios.get_for_user(scenario_id, user_id=user_id)
        if scenario is None:
            raise NotFoundError("No scenario with that identifier exists for this user.")

        snapshot = self._position.capture_snapshot(user_id=user_id)
        scenario.snapshot_id = snapshot.id
        self._session.commit()
        return self.run(scenario_id, user_id=user_id)

    def snapshot_age_days(self, scenario: Scenario, *, user_id: UUID) -> int | None:
        snapshot = self._snapshots.get_for_user(scenario.snapshot_id, user_id=user_id)
        if snapshot is None:
            return None
        return (datetime.now(UTC) - snapshot.captured_at).days

    def needs_rebaseline(self, scenario: Scenario, *, user_id: UUID) -> bool:
        age = self.snapshot_age_days(scenario, user_id=user_id)
        return age is not None and age > RE_BASELINE_AFTER_DAYS

    def compare(self, scenario_ids: list[UUID], *, user_id: UUID) -> list[dict]:
        comparisons = []
        for scenario_id in scenario_ids:
            scenario = self._scenarios.get_for_user(scenario_id, user_id=user_id)
            if scenario is None:
                raise NotFoundError("No scenario with that identifier exists for this user.")
            results = self._scenarios.results_for(scenario_id)
            comparisons.append(
                {
                    "scenario_id": str(scenario_id),
                    "name": scenario.name,
                    "scenario_type": scenario.scenario_type.value,
                    "latest_result": _result_dict(results[0]) if results else None,
                }
            )
        return comparisons

    def delete(self, scenario_id: UUID, *, user_id: UUID) -> None:
        scenario = self._scenarios.get_for_user(scenario_id, user_id=user_id)
        if scenario is None:
            raise NotFoundError("No scenario with that identifier exists for this user.")
        self._scenarios.delete(scenario)
        self._session.commit()


def _emergency_fund_months_after(position: FinancialPosition, first_period) -> Decimal:
    """emergency_fund_months (app/domain/emergency_fund.py) requires a non-negative
    balance — it validates a real account balance, which is never negative. A projected
    first-period savings balance is a different thing: it CAN legitimately go negative
    (the scenario costs more than the user's income and savings can cover), and that is
    exactly the case where coverage is zero, not an error to raise. Clamping here, at the
    service boundary, keeps the domain engine's contract honest for its real callers.
    """
    if first_period.savings < 0:
        return Decimal("0.000000")

    return emergency_fund_months(
        liquid_savings=first_period.savings,
        monthly_essential_spending=position.monthly_essential,
    )


def _period_dict(period) -> dict:
    return {
        "month": period.month,
        "cash_flow": str(period.cash_flow),
        "savings": str(period.savings),
        "debt": str(period.debt),
        "net_worth": str(period.net_worth),
    }


def _result_dict(result: ScenarioResult) -> dict:
    return {
        "result_id": str(result.id),
        "computed_at": result.computed_at.isoformat(),
        "engine_version": result.engine_version,
        "impact": result.impact,
    }


__all__ = [
    "ENGINE_VERSION",
    "DEFAULT_HORIZON_MONTHS",
    "RE_BASELINE_AFTER_DAYS",
    "ScenarioService",
    "build_assumptions",
    # Re-exported so existing callers and tests keep importing assumption types from the
    # service they use, even though the types themselves now live in the domain.
    "VehiclePurchaseAssumptions",
    "PropertyPurchaseAssumptions",
    "IncomeChangeAssumptions",
    "NewLoanAssumptions",
    "DebtRepaymentChangeAssumptions",
    "SavingsChangeAssumptions",
    "DiscretionaryExpenseAssumptions",
]
