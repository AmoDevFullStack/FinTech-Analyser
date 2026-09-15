from decimal import Decimal
from uuid import UUID

from flask import Blueprint, g, jsonify, request

from app.core.auth import require_auth
from app.core.errors import NotFoundError, ValidationError
from app.core.extensions import db
from app.repositories.position_snapshot import PositionSnapshotRepository
from app.repositories.scenario import ScenarioRepository
from app.schemas.scenario import scenario_dict, scenario_result_dict
from app.services.scenario import ScenarioService, VehiclePurchaseAssumptions

bp = Blueprint("scenarios", __name__, url_prefix="/scenarios")


@bp.post("")
@require_auth
def create_scenario():
    body = request.get_json(force=True, silent=True) or {}
    if body.get("scenario_type") != "vehicle_purchase":
        raise ValidationError("Only 'vehicle_purchase' scenarios are supported in this build.")
    if not body.get("name"):
        raise ValidationError("'name' is required.")

    assumptions_body = body.get("assumptions", {})
    try:
        assumptions = VehiclePurchaseAssumptions(
            purchase_price=Decimal(str(assumptions_body["purchase_price"])),
            deposit=Decimal(str(assumptions_body.get("deposit", "0"))),
            annual_rate=Decimal(str(assumptions_body["annual_rate"])),
            term_months=int(assumptions_body["term_months"]),
            insurance_monthly=Decimal(str(assumptions_body.get("insurance_monthly", "0"))),
            fuel_monthly=Decimal(str(assumptions_body.get("fuel_monthly", "0"))),
            maintenance_monthly=Decimal(str(assumptions_body.get("maintenance_monthly", "0"))),
            trade_in_value=Decimal(str(assumptions_body.get("trade_in_value", "0"))),
        )
    except KeyError as exc:
        raise ValidationError(f"Missing assumption: {exc.args[0]}") from exc

    service = ScenarioService(db.session)
    scenario = service.create_vehicle_purchase(
        user_id=g.user_id,
        name=body["name"],
        description=body.get("description"),
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
    return (
        jsonify(
            {
                "data": [
                    scenario_dict(
                        s,
                        snapshot_captured_at=snapshots.get_for_user(
                            s.snapshot_id, user_id=g.user_id
                        ).captured_at.isoformat(),
                    )
                    for s in scenarios
                ]
            }
        ),
        200,
    )


@bp.get("/<uuid:scenario_id>")
@require_auth
def get_scenario(scenario_id):
    scenario = ScenarioRepository(db.session).get_for_user(scenario_id, user_id=g.user_id)
    if scenario is None:
        raise NotFoundError("No scenario with that identifier exists for this user.")
    snapshot = PositionSnapshotRepository(db.session).get_for_user(
        scenario.snapshot_id, user_id=g.user_id
    )
    return jsonify(scenario_dict(scenario, snapshot_captured_at=snapshot.captured_at.isoformat())), 200


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


@bp.get("/compare")
@require_auth
def compare_scenarios():
    ids_param = request.args.get("ids", "")
    ids = [UUID(part) for part in ids_param.split(",") if part]
    comparisons = ScenarioService(db.session).compare(ids, user_id=g.user_id)
    return jsonify({"data": comparisons}), 200
