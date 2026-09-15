from datetime import datetime

from flask import Blueprint, g, jsonify, request

from app.core.auth import require_auth
from app.core.errors import NotFoundError
from app.core.extensions import db
from app.repositories.health_assessment import HealthAssessmentRepository
from app.workers.financial_health import assess_financial_health

bp = Blueprint("health", __name__, url_prefix="/health-assessment")


def _assessment_dict(assessment) -> dict:
    return {
        "score": assessment.score,
        "computed_at": assessment.computed_at.isoformat(),
        "weights_version": assessment.weights_version,
        "components": assessment.breakdown["components"],
        "largest_positive_contributor": assessment.breakdown["largest_positive_contributor"],
        "largest_negative_contributor": assessment.breakdown["largest_negative_contributor"],
    }


@bp.get("")
@require_auth
def get_health_assessment():
    """The response always includes the component breakdown — a score without it is not
    a valid response, per requirement 10 and specs/financial-health.md.
    """
    repo = HealthAssessmentRepository(db.session)
    assessment = repo.latest_for_user(user_id=g.user_id)
    if assessment is None:
        raise NotFoundError("No financial health assessment exists yet for this user.")
    return jsonify(_assessment_dict(assessment)), 200


@bp.get("/history")
@require_auth
def get_health_assessment_history():
    args = request.args
    repo = HealthAssessmentRepository(db.session)
    history = repo.history_for_user(
        user_id=g.user_id,
        since=datetime.fromisoformat(args["from"]) if args.get("from") else None,
        until=datetime.fromisoformat(args["to"]) if args.get("to") else None,
    )
    return jsonify({"data": [_assessment_dict(a) for a in history]}), 200


@bp.post("/refresh")
@require_auth
def refresh_health_assessment():
    assessment = assess_financial_health(db.session, user_id=g.user_id)
    return jsonify(_assessment_dict(assessment)), 201
