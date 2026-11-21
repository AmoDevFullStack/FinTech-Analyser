"""Liveness, readiness and build identity — the endpoints a deploy pipeline talks to.

- /health   liveness: the process is up. Never touches the database, so a database outage
            does not make an orchestrator restart healthy containers in a loop.
- /ready    readiness: the database answers AND its schema is at this build's Alembic head.
- /version  which build is serving, so a post-deploy smoke test can prove the new image is
            the one answering rather than the previous one.
"""

from flask import Blueprint, Response, current_app, jsonify

from app.core.extensions import db
from app.core.release import BuildInfo, check_readiness

bp = Blueprint("operational", __name__)


@bp.get("/health")
def health() -> tuple[Response, int]:
    return jsonify({"status": "ok"}), 200


@bp.get("/ready")
def ready() -> tuple[Response, int]:
    readiness = check_readiness(db.session)
    return jsonify(readiness.as_dict()), 200 if readiness.ready else 503


@bp.get("/version")
def version() -> tuple[Response, int]:
    return jsonify(BuildInfo.from_config(current_app.config).as_dict()), 200
