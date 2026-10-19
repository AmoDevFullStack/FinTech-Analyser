"""JWT issue, verify, and revoke. See docs/api.md, "Authentication".

Two token types, with deliberately different properties:

  * **access** — short-lived, sent on every request as `Authorization: Bearer <token>`,
    and *not* checked against the revocation list. Checking it would put a Redis round
    trip in front of every single API call to close a window that is already only fifteen
    minutes wide. Its short lifetime is the revocation mechanism.
  * **refresh** — long-lived, sent only to `POST /auth/refresh`, and checked against the
    revocation list on every use. Logout revokes it, and a refresh rotates it: the token
    presented is revoked as the new pair is issued, so a refresh token is usable exactly
    once. A stolen refresh token that the attacker uses therefore breaks the real user's
    session at their next refresh, which is a detectable event rather than a silent
    parallel session.

Both carry a `jti`, so a refresh token can be named in the revocation list without storing
the token itself anywhere.

The revocation list is Redis, keyed by `jti` with a TTL equal to the token's own remaining
life — an entry that outlives the token it revokes protects nothing and costs memory
forever. Under TESTING it is a process-local dict, because the suite must not require a
Redis instance to assert that logout works.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from uuid import UUID, uuid4

import jwt
from flask import current_app

from app.core.errors import UnauthenticatedError

ACCESS = "access"
REFRESH = "refresh"

_REVOKED_KEY_PREFIX = "jwt:revoked:"

# TESTING only. A module-level dict is process-local and therefore useless across the
# gunicorn workers a real deployment runs, which is exactly why it is fenced behind the
# TESTING check in `_revocation_store` rather than offered as a general fallback.
_in_memory_revocations: dict[str, float] = {}


@dataclass(frozen=True, slots=True)
class TokenPair:
    """What a successful login or refresh hands the client.

    `expires_in` is the access token's remaining life in seconds, so a client can schedule
    its refresh without parsing the JWT itself.
    """

    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int


@dataclass(frozen=True, slots=True)
class TokenClaims:
    user_id: UUID
    token_type: str
    jti: str
    expires_at: int


class _MemoryStore:
    """The TESTING revocation store. Expiry is enforced on read, not by a background sweep."""

    def revoke(self, jti: str, *, ttl_seconds: int) -> None:
        _in_memory_revocations[jti] = time.time() + ttl_seconds

    def is_revoked(self, jti: str) -> bool:
        expires_at = _in_memory_revocations.get(jti)
        if expires_at is None:
            return False
        if expires_at <= time.time():
            del _in_memory_revocations[jti]
            return False
        return True


class _RedisStore:
    def __init__(self, url: str) -> None:
        import redis

        self._client = redis.Redis.from_url(url)

    def revoke(self, jti: str, *, ttl_seconds: int) -> None:
        # No try/except: if Redis is unreachable, logout must fail loudly. Reporting a
        # successful logout that did not revoke anything is the worst available outcome —
        # the user believes they are signed out and the refresh token still works.
        self._client.setex(f"{_REVOKED_KEY_PREFIX}{jti}", max(ttl_seconds, 1), "1")

    def is_revoked(self, jti: str) -> bool:
        return self._client.exists(f"{_REVOKED_KEY_PREFIX}{jti}") == 1


def _revocation_store() -> _MemoryStore | _RedisStore:
    if current_app.config["TESTING"]:
        return _MemoryStore()
    return _RedisStore(current_app.config["REDIS_URL"])


def _encode(*, user_id: UUID, token_type: str, ttl_seconds: int) -> tuple[str, str]:
    issued_at = int(time.time())
    jti = str(uuid4())
    payload = {
        "sub": str(user_id),
        "typ": token_type,
        "jti": jti,
        "iat": issued_at,
        "nbf": issued_at,
        "exp": issued_at + ttl_seconds,
        "iss": current_app.config["JWT_ISSUER"],
    }
    token = jwt.encode(
        payload,
        current_app.config["JWT_SECRET_KEY"],
        algorithm=current_app.config["JWT_ALGORITHM"],
    )
    return token, jti


def issue_token_pair(user_id: UUID) -> TokenPair:
    """Mint a fresh access/refresh pair for a user who has just proved who they are."""
    access_ttl = current_app.config["JWT_ACCESS_TTL_SECONDS"]
    refresh_ttl = current_app.config["JWT_REFRESH_TTL_SECONDS"]

    access_token, _ = _encode(user_id=user_id, token_type=ACCESS, ttl_seconds=access_ttl)
    refresh_token, _ = _encode(user_id=user_id, token_type=REFRESH, ttl_seconds=refresh_ttl)

    return TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="Bearer",
        expires_in=access_ttl,
    )


def decode_token(raw: str, *, expected_type: str) -> TokenClaims:
    """Verify a token's signature, issuer, expiry, and type, and return its claims.

    Every failure raises `UnauthenticatedError` with the same status and a message that
    says which check failed. The distinction matters to a client — "expired" means refresh,
    "invalid" means log in again — and tells an attacker nothing they cannot determine by
    waiting fifteen minutes.

    A refresh token is additionally checked against the revocation list. An access token
    is not; see this module's docstring for why.
    """
    try:
        payload = jwt.decode(
            raw,
            current_app.config["JWT_SECRET_KEY"],
            algorithms=[current_app.config["JWT_ALGORITHM"]],
            issuer=current_app.config["JWT_ISSUER"],
            options={"require": ["exp", "iat", "sub", "jti", "iss"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise UnauthenticatedError("The token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise UnauthenticatedError("The token is not valid.") from exc

    if payload.get("typ") != expected_type:
        raise UnauthenticatedError(
            f"A {expected_type} token is required for this endpoint."
        )

    try:
        user_id = UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise UnauthenticatedError("The token is not valid.") from exc

    jti = payload["jti"]
    if expected_type == REFRESH and _revocation_store().is_revoked(jti):
        raise UnauthenticatedError("The token has been revoked.")

    return TokenClaims(
        user_id=user_id,
        token_type=payload["typ"],
        jti=jti,
        expires_at=int(payload["exp"]),
    )


def revoke(claims: TokenClaims) -> None:
    """Add a token's `jti` to the revocation list until the token would have expired anyway."""
    ttl = claims.expires_at - int(time.time())
    if ttl <= 0:
        return  # already expired; the list would only hold a tombstone
    _revocation_store().revoke(claims.jti, ttl_seconds=ttl)


def bearer_token_from_header(header: str | None) -> str | None:
    """Pull the credential out of an `Authorization: Bearer <token>` header.

    Returns None for a missing header and for one using a different scheme, so the caller
    can fall through to cookie authentication. A malformed *Bearer* header is not silently
    ignored, though — it is a client sending a credential it believes in, and treating that
    as "unauthenticated, try the cookie" hides the bug.
    """
    if not header:
        return None
    parts = header.split(None, 1)
    if not parts or parts[0].lower() != "bearer":
        return None
    # The scheme is checked before the token, so "Bearer" with nothing after it reaches the
    # error below rather than falling into the `len(parts) != 2` case and being treated as
    # no credential at all.
    token = parts[1].strip() if len(parts) == 2 else ""
    if not token:
        raise UnauthenticatedError("The Authorization header carries no token.")
    return token
