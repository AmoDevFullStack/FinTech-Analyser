from __future__ import annotations

from functools import wraps
from uuid import UUID

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from flask import g, request, session

from app.core.errors import UnauthenticatedError
from app.core.tokens import ACCESS, bearer_token_from_header, decode_token

_hasher = PasswordHasher()


def hash_password(plain: str) -> str:
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, plain)
    except VerifyMismatchError:
        return False


def log_in_user(user_id: UUID) -> None:
    session.clear()
    session["user_id"] = str(user_id)
    session.permanent = True


def log_out_user() -> None:
    session.clear()


def current_user_id() -> UUID | None:
    """Who is making this request, by bearer token first and session cookie second.

    Both are supported on purpose. The bearer token is the interface for any client that
    cannot hold a cookie; the cookie remains because the browser client and the Playwright
    suite were built on it and because a same-site cookie is not the weaker option for a
    browser. The order matters: a request that troubles to send an `Authorization` header
    means that identity, and silently answering as whoever the stale cookie names would be
    a cross-user data leak in a system where every repository query is scoped by user id.
    """
    token = bearer_token_from_header(request.headers.get("Authorization"))
    if token is not None:
        return decode_token(token, expected_type=ACCESS).user_id

    raw = session.get("user_id")
    return UUID(raw) if raw else None


def require_auth(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user_id = current_user_id()
        if user_id is None:
            raise UnauthenticatedError()
        g.user_id = user_id
        return view(*args, **kwargs)

    return wrapped
