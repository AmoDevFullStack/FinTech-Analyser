from flask import Blueprint, g, jsonify

from app.core.auth import require_auth
from app.core.extensions import db
from app.services.position import PositionService

bp = Blueprint("position", __name__, url_prefix="/position")


@bp.get("")
@require_auth
def get_position():
    """Reads stored results only — never triggers computation. See ADR-003 and
    specs/dashboard.md.
    """
    payload = PositionService(db.session).dashboard_payload(user_id=g.user_id)
    return jsonify(payload), 200


@bp.post("/snapshot")
@require_auth
def create_snapshot():
    snapshot = PositionService(db.session).capture_snapshot(user_id=g.user_id)
    return jsonify({"snapshot_id": str(snapshot.id), "captured_at": snapshot.captured_at.isoformat()}), 201
