from __future__ import annotations

from functools import wraps
from uuid import UUID

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from flask import g, session

from app.core.errors import UnauthenticatedError

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
