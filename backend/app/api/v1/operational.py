from flask import Blueprint, jsonify

from app.core.extensions import db

bp = Blueprint("operational", __name__)


@bp.get("/health")
def health():
    return jsonify({"status": "ok"}), 200


@bp.get("/ready")
def ready():
    try:
        db.session.execute(db.text("SELECT 1"))
        database_ok = True
    except Exception:
        database_ok = False
    status = 200 if database_ok else 503
    return jsonify({"status": "ok" if database_ok else "unavailable", "database": database_ok}), status
