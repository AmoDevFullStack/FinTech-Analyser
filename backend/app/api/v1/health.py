from flask import Blueprint, g, jsonify

from app.core.auth import require_auth
from app.core.errors import NotFoundError
from app.core.extensions import db
from app.repositories.health_assessment import HealthAssessmentRepository
from app.schemas.base import parse_query
from app.schemas.requests import HealthAssessmentQuery, HealthMonthsQuery
from app.workers.financial_health import assess_financial_health

bp = Blueprint("health", __name__, url_prefix="/health-assessment")


def _assessment_dict(assessment) -> dict:
    return {
        "month": assessment.month,
        "score": assessment.score,
        "computed_at": assessment.computed_at.isoformat(),
        "weights_version": assessment.weights_version,
        "components": assessment.breakdown["components"],
        "largest_positive_contributor": assessment.breakdown["largest_positive_contributor"],
        "largest_negative_contributor": assessment.breakdown["largest_negative_contributor"],
        # Which inputs are the month's own and which are as they stand today, and how many
        # statement lines stand behind the month. Absent on assessments stored before the
        # score became month-by-month.
        "historical_basis": assessment.breakdown.get("historical_basis"),
        "evidence": assessment.breakdown.get("evidence"),
    }


@bp.get("")
@require_auth
def get_health_assessment():
    """One month's assessment — the most recent one by default.

    The response always includes the component breakdown: a score without it is not a valid
    response, per requirement 10 and specs/financial-health.md.
    """
    query = parse_query(HealthAssessmentQuery)
    repo = HealthAssessmentRepository(db.session)

    assessment = (
        repo.for_month(user_id=g.user_id, month=query.month)
        if query.month is not None
        else repo.latest_for_user(user_id=g.user_id)
    )
    if assessment is None:
        raise NotFoundError(
            f"No financial health assessment exists for {query.month}."
            if query.month is not None
            else "No financial health assessment exists yet for this user."
        )
    return jsonify(_assessment_dict(assessment)), 200


@bp.get("/months")
@require_auth
def get_health_assessment_months():
    """The score month by month, oldest first — the series a trajectory is read from.

    This replaced `/history`, which was ordered by when each assessment ran rather than by
    what it was about: two runs in one afternoon read as two data points and a quiet
    fortnight read as none.
    """
    query = parse_query(HealthMonthsQuery)
    assessments = HealthAssessmentRepository(db.session).months_for_user(
        user_id=g.user_id, since=query.since, until=query.until
    )
    return (
        jsonify(
            {
                "data": [_assessment_dict(a) for a in assessments],
                "months": len(assessments),
            }
        ),
        200,
    )


@bp.post("/refresh")
@require_auth
def refresh_health_assessment():
    """Re-score the recent months and return the most recent one.

    Not only the current month: a statement imported later usually carries months whose
    scores were computed before those transactions existed.
    """
    assessment = assess_financial_health(db.session, user_id=g.user_id)
    return jsonify(_assessment_dict(assessment)), 201
