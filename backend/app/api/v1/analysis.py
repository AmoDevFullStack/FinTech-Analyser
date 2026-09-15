from flask import Blueprint, g, jsonify

from app.core.auth import require_auth
from app.core.extensions import db
from app.services.recurrence import RecurrenceService

bp = Blueprint("analysis", __name__, url_prefix="/analysis")


@bp.get("/recurring")
@require_auth
def list_recurring():
    """The recurring series view from specs/transactions.md's Output section."""
    views = RecurrenceService(db.session).detect(user_id=g.user_id)
    return (
        jsonify(
            {
                "data": [
                    {
                        "key": v.series.key,
                        "frequency": v.series.frequency.value,
                        "median_amount": str(v.series.median_amount),
                        "monthly_equivalent": str(v.series.monthly_equivalent),
                        "annual_cost": str(v.series.annual_cost),
                        "occurrence_count": v.series.occurrence_count,
                        "first_seen": v.series.first_seen.isoformat(),
                        "last_seen": v.series.last_seen.isoformat(),
                        "next_expected_on": v.series.next_expected_on.isoformat(),
                        "category_id": str(v.category_id) if v.category_id else None,
                        "category_kind": v.category_kind.value if v.category_kind else None,
                    }
                    for v in views
                ]
            }
        ),
        200,
    )
