"""Scenario orchestration. See specs/scenarios.md and ADR-005.

This service loads the snapshot and assumptions and calls domain engines; it does not
calculate. Every figure in a `ScenarioResult` traces back to `app/domain/`.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from app.core.db import DbSession

from app.core.errors import NotFoundError, SemanticError
from app.domain.amortisation import amortisation_schedule
from app.domain.cash_flow import debt_to_income
from app.domain.emergency_fund import emergency_fund_months
from app.domain.projection import FinancialPosition, project_forward
from app.models.scenario import (
    Scenario,
    ScenarioAssumption,
    ScenarioResult,
    ScenarioStatus,
    ScenarioType,
)
from app.repositories.position_snapshot import PositionSnapshotRepository
from app.repositories.scenario import ScenarioRepository
from app.services.position import PositionService

ENGINE_VERSION = "1.0.0"
DEFAULT_HORIZON_MONTHS = 60
RE_BASELINE_AFTER_DAYS = 30


@dataclass(frozen=True, slots=True)
class VehiclePurchaseAssumptions:
    purchase_price: Decimal
    deposit: Decimal
    annual_rate: Decimal
    term_months: int
    insurance_monthly: Decimal = Decimal("0")
    fuel_monthly: Decimal = Decimal("0")
    maintenance_monthly: Decimal = Decimal("0")
    trade_in_value: Decimal = Decimal("0")

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

    @property
    def financed_principal(self) -> Decimal:
        return self.purchase_price - self.deposit - self.trade_in_value

    @property
    def recurring_monthly_cost(self) -> Decimal:
        return self.insurance_monthly + self.fuel_monthly + self.maintenance_monthly


class ScenarioService:
    def __init__(self, session: DbSession) -> None:
        self._session = session
        self._scenarios = ScenarioRepository(session)
        self._snapshots = PositionSnapshotRepository(session)
        self._position = PositionService(session)

    def create_vehicle_purchase(
        self,
        *,
        user_id: UUID,
        name: str,
        description: str | None,
        assumptions: VehiclePurchaseAssumptions,
    ) -> Scenario:
        if assumptions.financed_principal <= 0:
            raise SemanticError(
                "Deposit and trade-in together must be less than the purchase price."
            )

        snapshot = self._position.capture_snapshot(user_id=user_id)

        scenario = Scenario(
            user_id=user_id,
            name=name,
            description=description,
            scenario_type=ScenarioType.VEHICLE_PURCHASE,
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

    def run(self, scenario_id: UUID, *, user_id: UUID) -> ScenarioResult:
        scenario = self._scenarios.get_for_user(scenario_id, user_id=user_id)
        if scenario is None:
            raise NotFoundError("No scenario with that identifier exists for this user.")

        snapshot = self._snapshots.get_for_user(scenario.snapshot_id, user_id=user_id)
        if snapshot is None:
            raise NotFoundError("The scenario's position snapshot no longer exists.")

        assumption_rows = self._scenarios.assumptions_for(scenario.id)
        assumption_values = {row.key: row.value for row in assumption_rows}
        assumptions = VehiclePurchaseAssumptions(
            purchase_price=Decimal(assumption_values["purchase_price"]),
            deposit=Decimal(assumption_values["deposit"]),
            annual_rate=Decimal(assumption_values["annual_rate"]),
            term_months=int(assumption_values["term_months"]),
            insurance_monthly=Decimal(assumption_values["insurance_monthly"]),
            fuel_monthly=Decimal(assumption_values["fuel_monthly"]),
            maintenance_monthly=Decimal(assumption_values["maintenance_monthly"]),
            trade_in_value=Decimal(assumption_values["trade_in_value"]),
        )

        position = FinancialPosition(
            as_of=snapshot.captured_at.date(),
            liquid_savings=snapshot.liquid_savings,
            total_debt=snapshot.total_debt,
            net_worth=snapshot.net_worth,
            monthly_income=snapshot.monthly_income,
            monthly_essential=snapshot.monthly_essential,
            monthly_discretionary=snapshot.monthly_discretionary,
        )

        baseline_periods = project_forward(position=position, horizon_months=DEFAULT_HORIZON_MONTHS)

        schedule = amortisation_schedule(
            principal=assumptions.financed_principal,
            annual_rate=assumptions.annual_rate,
            term_months=assumptions.term_months,
        )
        scenario_position = FinancialPosition(
            as_of=position.as_of,
            liquid_savings=position.liquid_savings - assumptions.deposit,
            total_debt=position.total_debt,
            net_worth=position.net_worth - assumptions.deposit,
            monthly_income=position.monthly_income,
            monthly_essential=position.monthly_essential,
            monthly_discretionary=position.monthly_discretionary,
        )
        scenario_periods = project_forward(
            position=scenario_position,
            horizon_months=DEFAULT_HORIZON_MONTHS,
            monthly_expense_delta=assumptions.recurring_monthly_cost,
            new_debt_schedule=tuple(schedule),
        )

        first_month_cash_flow_delta = scenario_periods[0].cash_flow - baseline_periods[0].cash_flow
        disposable_income_after = scenario_periods[0].cash_flow
        dti_before = debt_to_income(
            monthly_debt_service=Decimal("0"), monthly_income=position.monthly_income
        ) if position.monthly_income > 0 else Decimal("0")
        first_instalment = schedule[0].instalment
        dti_after = debt_to_income(
            monthly_debt_service=first_instalment, monthly_income=position.monthly_income
        ) if position.monthly_income > 0 else Decimal("0")

        # "Debt free" here means the scenario's own new debt is paid off, not that every
        # pre-existing debt reaches zero — this slice doesn't amortise existing debts
        # period by period (see the assumptions in app/domain/projection.py). Once a full
        # multi-debt schedule engine exists (PLAN.md "Next"), this should track the true
        # all-debts-zero date instead.
        debt_free_period = next(
            (p for p in scenario_periods if p.debt <= position.total_debt), None
        )
        debt_free_date = debt_free_period.month if debt_free_period else None

        impact = {
            "monthly_cash_flow_delta": str(first_month_cash_flow_delta),
            "disposable_income_after": str(disposable_income_after),
            "debt_to_income_before": str(dti_before),
            "debt_to_income_after": str(dti_after),
            "emergency_fund_months_after": str(
                _emergency_fund_months_after(scenario_position, scenario_periods[0])
            ),
            "net_worth_at_60_months": str(scenario_periods[-1].net_worth),
            "debt_free_date": debt_free_date,
        }

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
