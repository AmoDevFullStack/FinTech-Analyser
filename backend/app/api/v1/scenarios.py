from uuid import UUID

from flask import Blueprint, g, jsonify, request

from app.core.auth import require_auth
from app.core.errors import NotFoundError, ValidationError
from app.core.extensions import db
from app.models.scenario import ScenarioType
from app.repositories.position_snapshot import PositionSnapshotRepository
from app.repositories.scenario import ScenarioRepository
from app.schemas.scenario import scenario_dict, scenario_result_dict
from app.services.scenario import ScenarioService, build_assumptions

bp = Blueprint("scenarios", __name__, url_prefix="/scenarios")


@bp.post("")
@require_auth
def create_scenario():
    body = request.get_json(force=True, silent=True) or {}
    try:
        scenario_type = ScenarioType(body.get("scenario_type"))
    except ValueError as exc:
        supported = ", ".join(t.value for t in ScenarioType)
        raise ValidationError(
            f"Unknown scenario_type: {body.get('scenario_type')!r}. Supported: {supported}."
        ) from exc
    if not body.get("name"):
        raise ValidationError("'name' is required.")

    assumptions = build_assumptions(scenario_type, body.get("assumptions", {}))

    service = ScenarioService(db.session)
    scenario = service.create(
        user_id=g.user_id,
        name=body["name"],
        description=body.get("description"),
        scenario_type=scenario_type,
        assumptions=assumptions,
    )
    snapshot = PositionSnapshotRepository(db.session).get_for_user(
        scenario.snapshot_id, user_id=g.user_id
    )
    return jsonify(scenario_dict(scenario, snapshot_captured_at=snapshot.captured_at.isoformat())), 201


@bp.get("")
@require_auth
def list_scenarios():
    scenarios = ScenarioRepository(db.session).list_for_user(user_id=g.user_id)
    snapshots = PositionSnapshotRepository(db.session)
    service = ScenarioService(db.session)
    return (
        jsonify(
            {
                "data": [
                    {
                        **scenario_dict(
                            s,
                            snapshot_captured_at=snapshots.get_for_user(
                                s.snapshot_id, user_id=g.user_id
                            ).captured_at.isoformat(),
                        ),
                        "snapshot_age_days": service.snapshot_age_days(s, user_id=g.user_id),
                        "needs_rebaseline": service.needs_rebaseline(s, user_id=g.user_id),
                    }
                    for s in scenarios
                ]
            }
        ),
        200,
    )


@bp.get("/compare")
@require_auth
def compare_scenarios():
    ids_param = request.args.get("ids", "")
    ids = [UUID(part) for part in ids_param.split(",") if part]
    comparisons = ScenarioService(db.session).compare(ids, user_id=g.user_id)
    return jsonify({"data": comparisons}), 200


@bp.get("/<uuid:scenario_id>")
@require_auth
def get_scenario(scenario_id):
    scenario = ScenarioRepository(db.session).get_for_user(scenario_id, user_id=g.user_id)
    if scenario is None:
        raise NotFoundError("No scenario with that identifier exists for this user.")
    snapshot = PositionSnapshotRepository(db.session).get_for_user(
        scenario.snapshot_id, user_id=g.user_id
    )
    service = ScenarioService(db.session)
    return (
        jsonify(
            {
                **scenario_dict(
                    scenario, snapshot_captured_at=snapshot.captured_at.isoformat()
                ),
                "snapshot_age_days": service.snapshot_age_days(scenario, user_id=g.user_id),
                "needs_rebaseline": service.needs_rebaseline(scenario, user_id=g.user_id),
                "assumptions": {
                    row.key: row.value
                    for row in ScenarioRepository(db.session).assumptions_for(scenario_id)
                },
            }
        ),
        200,
    )


@bp.delete("/<uuid:scenario_id>")
@require_auth
def delete_scenario(scenario_id):
    ScenarioService(db.session).delete(scenario_id, user_id=g.user_id)
    return "", 204


@bp.post("/<uuid:scenario_id>/run")
@require_auth
def run_scenario(scenario_id):
    result = ScenarioService(db.session).run(scenario_id, user_id=g.user_id)
    return jsonify(scenario_result_dict(scenario_id, result)), 200


@bp.post("/<uuid:scenario_id>/rebaseline")
@require_auth
def rebaseline_scenario(scenario_id):
    """Capture a fresh snapshot and re-run against it."""
    result = ScenarioService(db.session).rebaseline(scenario_id, user_id=g.user_id)
    return jsonify(scenario_result_dict(scenario_id, result)), 200


@bp.get("/<uuid:scenario_id>/results")
@require_auth
def list_scenario_results(scenario_id):
    scenario = ScenarioRepository(db.session).get_for_user(scenario_id, user_id=g.user_id)
    if scenario is None:
        raise NotFoundError("No scenario with that identifier exists for this user.")
    results = ScenarioRepository(db.session).results_for(scenario_id)
    return jsonify({"data": [scenario_result_dict(scenario_id, r) for r in results]}), 200


@bp.get("/<uuid:scenario_id>/results/<uuid:result_id>")
@require_auth
def get_scenario_result(scenario_id, result_id):
    scenario = ScenarioRepository(db.session).get_for_user(scenario_id, user_id=g.user_id)
    if scenario is None:
        raise NotFoundError("No scenario with that identifier exists for this user.")
    result = ScenarioRepository(db.session).result_for(scenario_id, result_id)
    if result is None:
        raise NotFoundError("No result with that identifier exists for this scenario.")
    return jsonify(scenario_result_dict(scenario_id, result)), 200
