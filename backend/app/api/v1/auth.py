from flask import Blueprint, current_app, jsonify, request

from app.core.auth import require_auth
from app.core.errors import ValidationError
from app.core.extensions import db, limiter
from app.schemas.user import user_dict
from app.services.auth import AuthService, RegisterInput

bp = Blueprint("auth", __name__, url_prefix="/auth")


@bp.post("/register")
def register():
    body = request.get_json(force=True, silent=True) or {}
    for field in ("email", "password", "full_name"):
        if not body.get(field):
            raise ValidationError(f"'{field}' is required.")

    service = AuthService(db.session)
    user = service.register(
        RegisterInput(email=body["email"], password=body["password"], full_name=body["full_name"])
    )
    return jsonify(user_dict(user)), 201


@bp.post("/login")
@limiter.limit(lambda: current_app.config["LOGIN_RATE_LIMIT"])
def login():
    body = request.get_json(force=True, silent=True) or {}
    for field in ("email", "password"):
        if not body.get(field):
            raise ValidationError(f"'{field}' is required.")

    service = AuthService(db.session)
    user = service.login(email=body["email"], password=body["password"])
    return jsonify(user_dict(user)), 200


@bp.post("/logout")
@require_auth
def logout():
    AuthService(db.session).logout()
    return "", 204


@bp.get("/me")
@require_auth
def me():
    user = AuthService(db.session).current_user()
    return jsonify(user_dict(user)), 200
