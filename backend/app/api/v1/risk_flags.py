from flask import Blueprint, g, jsonify, request

from app.core.auth import require_auth
from app.core.errors import ValidationError
from app.core.extensions import db
from app.models.risk_flag import RiskFlag, RiskStatus
from app.services.risk import RiskService

bp = Blueprint("risk_flags", __name__, url_prefix="/risk-flags")


def _flag_dict(flag: RiskFlag) -> dict:
    return {
        "id": str(flag.id),
        "risk_type": flag.risk_type,
        "severity": flag.severity,
        "status": flag.status.value,
        "detected_on": flag.detected_on.isoformat(),
        "projected_date": flag.projected_date.isoformat() if flag.projected_date else None,
        "quantified_amount": str(flag.quantified_amount),
        "explanation": flag.explanation,
        "computation_reference": flag.computation_reference,
        "details": flag.details,
    }


@bp.get("")
@require_auth
def list_risk_flags():
    raw_status = request.args.get("status", "active")
    if raw_status == "all":
        status = None
    else:
        try:
            status = RiskStatus(raw_status)
        except ValueError as exc:
            raise ValidationError(f"Unknown status: {raw_status!r}") from exc

    flags = RiskService(db.session).list_flags(user_id=g.user_id, status=status)
    return jsonify({"data": [_flag_dict(f) for f in flags]}), 200


@bp.post("/evaluate")
@require_auth
def evaluate_risk_flags():
    """The on-demand counterpart to the worker's post-forecast evaluation."""
    flags = RiskService(db.session).evaluate(user_id=g.user_id)
    return jsonify({"data": [_flag_dict(f) for f in flags]}), 201


@bp.post("/<uuid:flag_id>/acknowledge")
@require_auth
def acknowledge_risk_flag(flag_id):
    flag = RiskService(db.session).acknowledge(flag_id, user_id=g.user_id)
    return jsonify(_flag_dict(flag)), 200


@bp.post("/<uuid:flag_id>/dismiss")
@require_auth
def dismiss_risk_flag(flag_id):
    """Dismissal suppresses this risk type for 30 days unless its severity increases."""
    flag = RiskService(db.session).dismiss(flag_id, user_id=g.user_id)
    return jsonify(_flag_dict(flag)), 200
