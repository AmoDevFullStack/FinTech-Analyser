from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from app.core.db import DbSession

from app.models.scenario import Scenario, ScenarioAssumption, ScenarioResult


class ScenarioRepository:
    def __init__(self, session: DbSession) -> None:
        self._session = session

    def list_for_user(self, *, user_id: UUID) -> list[Scenario]:
        stmt = select(Scenario).where(Scenario.user_id == user_id).order_by(
            Scenario.created_at.desc()
        )
        return list(self._session.scalars(stmt))

    def get_for_user(self, scenario_id: UUID, *, user_id: UUID) -> Scenario | None:
        stmt = select(Scenario).where(Scenario.id == scenario_id, Scenario.user_id == user_id)
        return self._session.scalars(stmt).first()

    def add(self, scenario: Scenario) -> Scenario:
        self._session.add(scenario)
        self._session.flush()
        return scenario

    def delete(self, scenario: Scenario) -> None:
        self._session.delete(scenario)
        self._session.flush()

    def add_assumptions(self, assumptions: list[ScenarioAssumption]) -> None:
        self._session.add_all(assumptions)
        self._session.flush()

    def assumptions_for(self, scenario_id: UUID) -> list[ScenarioAssumption]:
        stmt = select(ScenarioAssumption).where(ScenarioAssumption.scenario_id == scenario_id)
        return list(self._session.scalars(stmt))

    def add_result(self, result: ScenarioResult) -> ScenarioResult:
        self._session.add(result)
        self._session.flush()
        return result

    def results_for(self, scenario_id: UUID) -> list[ScenarioResult]:
        stmt = (
            select(ScenarioResult)
            .where(ScenarioResult.scenario_id == scenario_id)
            .order_by(ScenarioResult.computed_at.desc())
        )
        return list(self._session.scalars(stmt))

    def result_for(self, scenario_id: UUID, result_id: UUID) -> ScenarioResult | None:
        stmt = select(ScenarioResult).where(
            ScenarioResult.scenario_id == scenario_id, ScenarioResult.id == result_id
        )
        return self._session.scalars(stmt).first()
