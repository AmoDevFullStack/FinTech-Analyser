from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, text

from app.core.db import DbSession

from app.models.scenario import Scenario, ScenarioAssumption, ScenarioResult

_LIST_FOR_USER = text(
    """
    SELECT *
      FROM scenarios
     WHERE user_id = :user_id
     ORDER BY created_at DESC
    """
)

_GET_FOR_USER = text(
    """
    SELECT *
      FROM scenarios
     WHERE id = :scenario_id
       AND user_id = :user_id
    """
)

_ASSUMPTIONS_FOR = text(
    """
    SELECT *
      FROM scenario_assumptions
     WHERE scenario_id = :scenario_id
    """
)

_RESULTS_FOR = text(
    """
    SELECT *
      FROM scenario_results
     WHERE scenario_id = :scenario_id
     ORDER BY computed_at DESC
    """
)

_RESULT_FOR = text(
    """
    SELECT *
      FROM scenario_results
     WHERE scenario_id = :scenario_id
       AND id = :result_id
    """
)


class ScenarioRepository:
    def __init__(self, session: DbSession) -> None:
        self._session = session

    def list_for_user(self, *, user_id: UUID) -> list[Scenario]:
        return list(
            self._session.scalars(
                select(Scenario).from_statement(_LIST_FOR_USER), {"user_id": user_id}
            )
        )

    def get_for_user(self, scenario_id: UUID, *, user_id: UUID) -> Scenario | None:
        return self._session.scalars(
            select(Scenario).from_statement(_GET_FOR_USER),
            {"scenario_id": scenario_id, "user_id": user_id},
        ).first()

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
        return list(
            self._session.scalars(
                select(ScenarioAssumption).from_statement(_ASSUMPTIONS_FOR),
                {"scenario_id": scenario_id},
            )
        )

    def add_result(self, result: ScenarioResult) -> ScenarioResult:
        self._session.add(result)
        self._session.flush()
        return result

    def results_for(self, scenario_id: UUID) -> list[ScenarioResult]:
        return list(
            self._session.scalars(
                select(ScenarioResult).from_statement(_RESULTS_FOR),
                {"scenario_id": scenario_id},
            )
        )

    def result_for(self, scenario_id: UUID, result_id: UUID) -> ScenarioResult | None:
        return self._session.scalars(
            select(ScenarioResult).from_statement(_RESULT_FOR),
            {"scenario_id": scenario_id, "result_id": result_id},
        ).first()
