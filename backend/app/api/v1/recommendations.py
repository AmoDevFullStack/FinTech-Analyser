from flask import Blueprint, g, jsonify, request

from app.core.auth import require_auth
from app.core.errors import ValidationError
from app.core.extensions import db
from app.models.recommendation import Recommendation, RecommendationStatus
from app.services.recommendation import RecommendationService

bp = Blueprint("recommendations", __name__, url_prefix="/recommendations")


def _recommendation_dict(recommendation: Recommendation) -> dict:
    return {
        "id": str(recommendation.id),
        "rule_id": recommendation.rule_id,
        "status": recommendation.status.value,
        "benefit_amount": str(recommendation.benefit_amount),
        "benefit_kind": recommendation.benefit_kind,
        "explanation": recommendation.explanation,
        "computation_reference": recommendation.computation_reference,
        "details": recommendation.details,
        "generated_on": recommendation.generated_on.isoformat(),
    }


@bp.get("")
@require_auth
def list_recommendations():
    raw_status = request.args.get("status", "active")
    if raw_status == "all":
        status = None
    else:
        try:
            status = RecommendationStatus(raw_status)
        except ValueError as exc:
            raise ValidationError(f"Unknown status: {raw_status!r}") from exc

    rows = RecommendationService(db.session).list_recommendations(
        user_id=g.user_id, status=status
    )
    return jsonify({"data": [_recommendation_dict(r) for r in rows]}), 200


@bp.post("/evaluate")
@require_auth
def evaluate_recommendations():
    rows = RecommendationService(db.session).evaluate(user_id=g.user_id)
    return jsonify({"data": [_recommendation_dict(r) for r in rows]}), 201


@bp.post("/<uuid:recommendation_id>/dismiss")
@require_auth
def dismiss_recommendation(recommendation_id):
    """Dismissal suppresses this rule for 60 days unless its benefit materially increases."""
    row = RecommendationService(db.session).dismiss(recommendation_id, user_id=g.user_id)
    return jsonify(_recommendation_dict(row)), 200


@bp.post("/<uuid:recommendation_id>/acted-on")
@require_auth
def mark_acted_on(recommendation_id):
    row = RecommendationService(db.session).mark_acted_on(recommendation_id, user_id=g.user_id)
    return jsonify(_recommendation_dict(row)), 200
