"""Registration, login, token refresh, logout. See docs/api.md, "Authentication".

Two credentials are issued on every successful login or registration: the session cookie
that already existed, and a JWT access/refresh pair. A client uses whichever suits it and
ignores the other. The reason both exist is in `app/core/auth.py`; the reason the tokens
have the lifetimes they do is in `app/core/tokens.py`.
"""

from flask import Blueprint, current_app, jsonify, request

from app.core.auth import require_auth
from app.core.extensions import db, limiter
from app.core.tokens import (
    ACCESS,
    REFRESH,
    TokenPair,
    bearer_token_from_header,
    decode_token,
    issue_token_pair,
    revoke,
)
from app.schemas.base import parse_body
from app.schemas.requests import LoginRequest, RefreshRequest, RegisterRequest
from app.schemas.user import user_dict
from app.services.auth import AuthService, RegisterInput
from app.services.category_seed import ensure_system_categories

bp = Blueprint("auth", __name__, url_prefix="/auth")


def _token_dict(pair: TokenPair) -> dict:
    return {
        "access_token": pair.access_token,
        "refresh_token": pair.refresh_token,
        "token_type": pair.token_type,
        "expires_in": pair.expires_in,
    }


@bp.post("/register")
def register():
    body = parse_body(RegisterRequest)

    service = AuthService(db.session)
    user = service.register(
        RegisterInput(email=body.email, password=body.password, full_name=body.full_name)
    )
    # A user with no categories has no cash-flow figures at all — every import falls
    # through categorisation and the dashboard reads zero. Seeding at registration is the
    # one moment it is certain to have happened before the first import.
    ensure_system_categories(db.session)
    db.session.commit()

    return jsonify({**user_dict(user), "tokens": _token_dict(issue_token_pair(user.id))}), 201


@bp.post("/login")
@limiter.limit(lambda: current_app.config["LOGIN_RATE_LIMIT"])
def login():
    body = parse_body(LoginRequest)
    user = AuthService(db.session).login(email=body.email, password=body.password)
    return jsonify({**user_dict(user), "tokens": _token_dict(issue_token_pair(user.id))}), 200


@bp.post("/refresh")
def refresh():
    """Exchange a refresh token for a new pair, revoking the one presented.

    Rotation, not reissue. The presented token is revoked as the new pair is minted, so a
    refresh token works exactly once — a stolen one that the attacker uses breaks the real
    user's next refresh, which turns a silent parallel session into a visible failure.

    Deliberately not behind `@require_auth`: the whole point of this endpoint is to be
    reachable once the access token has expired.
    """
    body = parse_body(RefreshRequest)
    claims = decode_token(body.refresh_token, expected_type=REFRESH)
    revoke(claims)
    return jsonify(_token_dict(issue_token_pair(claims.user_id))), 200


@bp.post("/logout")
@require_auth
def logout():
    """Clear the session cookie and revoke the refresh token, if one was supplied.

    The refresh token travels in the body rather than being inferred, because this request
    is authenticated with the *access* token and the two are separate credentials — the
    server cannot name the refresh token belonging to this session unless it is told which
    one it is.

    A logout with no refresh token still succeeds and still clears the cookie. Failing it
    would leave a client that has lost its refresh token unable to log out at all, which is
    worse than one refresh token running to its own expiry.
    """
    AuthService(db.session).logout()

    payload = request.get_json(force=True, silent=True)
    raw = payload.get("refresh_token") if isinstance(payload, dict) else None
    if raw:
        revoke(decode_token(raw, expected_type=REFRESH))

    return "", 204


@bp.get("/me")
@require_auth
def me():
    user = AuthService(db.session).current_user()
    return jsonify(user_dict(user)), 200


@bp.get("/verify")
@require_auth
def verify():
    """"Is this access token still good?", for a client deciding whether to refresh.

    Returns `/auth/me`'s payload plus the token's own expiry, so a client holding only the
    token string does not have to decode a JWT to find out when it dies. Null for a
    cookie-authenticated caller, which has no token to report an expiry for.
    """
    token = bearer_token_from_header(request.headers.get("Authorization"))
    expires_at = (
        decode_token(token, expected_type=ACCESS).expires_at if token is not None else None
    )
    user = AuthService(db.session).current_user()
    return jsonify({**user_dict(user), "expires_at": expires_at}), 200
