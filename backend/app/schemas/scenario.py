from app.models.scenario import Scenario, ScenarioResult


def scenario_dict(scenario: Scenario, *, snapshot_captured_at: str) -> dict:
    return {
        "id": str(scenario.id),
        "name": scenario.name,
        "description": scenario.description,
        "scenario_type": scenario.scenario_type.value,
        "status": scenario.status.value,
        "snapshot_captured_at": snapshot_captured_at,
    }


def scenario_result_dict(scenario_id, result: ScenarioResult) -> dict:
    return {
        "scenario_id": str(scenario_id),
        "result_id": str(result.id),
        "engine_version": result.engine_version,
        "computed_at": result.computed_at.isoformat(),
        "impact": result.impact,
        "periods": result.periods,
        "baseline_periods": result.baseline_periods,
    }
