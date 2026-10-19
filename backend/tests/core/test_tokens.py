"""JWT issue, verify, revoke. No database — tokens touch config and Redis, not Postgres.

The app here is a bare Flask instance rather than the one `create_app` builds, so this file
runs without a database even when the rest of the suite cannot. Under TESTING the
revocation store is the in-process dict, which is the point of that branch existing.
"""

from __future__ import annotations

import time
from uuid import uuid4

import jwt
import pytest
from flask import Flask

from app.core.config import load_config
from app.core.errors import UnauthenticatedError
from app.core.tokens import (
    ACCESS,
    REFRESH,
    bearer_token_from_header,
    decode_token,
    issue_token_pair,
    revoke,
)


@pytest.fixture()
def app():
    application = Flask(__name__)
    # `load_config` rather than `TestConfig` directly: conftest sets FLASK_ENV=testing at
    # import, so this is the same object, and importing the class by name makes pytest try
    # to collect it as a test class.
    application.config.from_object(load_config())
    with application.app_context():
        yield application


@pytest.fixture()
def user_id():
    return uuid4()


def test_a_pair_round_trips_to_the_same_user(app, user_id) -> None:
    pair = issue_token_pair(user_id)

    assert decode_token(pair.access_token, expected_type=ACCESS).user_id == user_id
    assert decode_token(pair.refresh_token, expected_type=REFRESH).user_id == user_id


def test_the_pair_reports_the_access_token_lifetime(app, user_id) -> None:
    """A client schedules its refresh from this rather than decoding the JWT itself."""
    pair = issue_token_pair(user_id)

    assert pair.token_type == "Bearer"
    assert pair.expires_in == app.config["JWT_ACCESS_TTL_SECONDS"]


def test_an_access_token_is_not_accepted_where_a_refresh_token_is_required(app, user_id) -> None:
    """Otherwise the fifteen-minute access token silently becomes a thirty-day one, because
    it would be accepted at the endpoint that mints new thirty-day tokens."""
    pair = issue_token_pair(user_id)

    with pytest.raises(UnauthenticatedError, match="refresh token is required"):
        decode_token(pair.access_token, expected_type=REFRESH)


def test_a_refresh_token_is_not_accepted_as_an_access_token(app, user_id) -> None:
    pair = issue_token_pair(user_id)

    with pytest.raises(UnauthenticatedError, match="access token is required"):
        decode_token(pair.refresh_token, expected_type=ACCESS)


def test_a_token_signed_with_another_key_is_rejected(app, user_id) -> None:
    forged = jwt.encode(
        {
            "sub": str(user_id),
            "typ": ACCESS,
            "jti": str(uuid4()),
            "iat": int(time.time()),
            "exp": int(time.time()) + 900,
            "iss": app.config["JWT_ISSUER"],
        },
        "not-the-signing-key",
        algorithm="HS256",
    )

    with pytest.raises(UnauthenticatedError, match="not valid"):
        decode_token(forged, expected_type=ACCESS)


def test_a_token_from_another_issuer_is_rejected(app, user_id) -> None:
    other = jwt.encode(
        {
            "sub": str(user_id),
            "typ": ACCESS,
            "jti": str(uuid4()),
            "iat": int(time.time()),
            "exp": int(time.time()) + 900,
            "iss": "somebody-elses-service",
        },
        app.config["JWT_SECRET_KEY"],
        algorithm="HS256",
    )

    with pytest.raises(UnauthenticatedError, match="not valid"):
        decode_token(other, expected_type=ACCESS)


def test_an_expired_token_says_so_rather_than_saying_invalid(app, user_id) -> None:
    """The distinction is what a client acts on: expired means refresh, invalid means log
    in again. It tells an attacker nothing they could not learn by waiting."""
    app.config["JWT_ACCESS_TTL_SECONDS"] = -1
    pair = issue_token_pair(user_id)

    with pytest.raises(UnauthenticatedError, match="expired"):
        decode_token(pair.access_token, expected_type=ACCESS)


def test_a_token_missing_a_required_claim_is_rejected(app, user_id) -> None:
    incomplete = jwt.encode(
        {"sub": str(user_id), "typ": ACCESS, "exp": int(time.time()) + 900},
        app.config["JWT_SECRET_KEY"],
        algorithm="HS256",
    )

    with pytest.raises(UnauthenticatedError, match="not valid"):
        decode_token(incomplete, expected_type=ACCESS)


def test_revoking_a_refresh_token_stops_it_working(app, user_id) -> None:
    pair = issue_token_pair(user_id)
    claims = decode_token(pair.refresh_token, expected_type=REFRESH)

    revoke(claims)

    with pytest.raises(UnauthenticatedError, match="revoked"):
        decode_token(pair.refresh_token, expected_type=REFRESH)


def test_revoking_a_refresh_token_leaves_the_access_token_alone(app, user_id) -> None:
    """Documented, deliberate, and the reason the access TTL is short: checking the
    revocation list on every request would put a Redis round trip in front of the whole API
    to close a window that is already only fifteen minutes wide."""
    pair = issue_token_pair(user_id)
    revoke(decode_token(pair.refresh_token, expected_type=REFRESH))

    assert decode_token(pair.access_token, expected_type=ACCESS).user_id == user_id


def test_revoking_an_already_expired_token_is_a_no_op(app, user_id) -> None:
    app.config["JWT_REFRESH_TTL_SECONDS"] = 1
    pair = issue_token_pair(user_id)
    claims = decode_token(pair.refresh_token, expected_type=REFRESH)
    # Reach past the token's life without sleeping the suite.
    expired = type(claims)(
        user_id=claims.user_id,
        token_type=claims.token_type,
        jti=claims.jti,
        expires_at=int(time.time()) - 5,
    )

    revoke(expired)  # must not write a tombstone that never expires

    assert decode_token(pair.refresh_token, expected_type=REFRESH).jti == claims.jti


def test_two_pairs_for_the_same_user_have_different_ids(app, user_id) -> None:
    """Otherwise revoking one session would revoke every session that user has open."""
    first = decode_token(issue_token_pair(user_id).refresh_token, expected_type=REFRESH)
    second = decode_token(issue_token_pair(user_id).refresh_token, expected_type=REFRESH)

    assert first.jti != second.jti


# --------------------------------------------------------------------------------------
# Header parsing
# --------------------------------------------------------------------------------------
def test_a_bearer_header_yields_the_token() -> None:
    assert bearer_token_from_header("Bearer abc.def.ghi") == "abc.def.ghi"


def test_the_scheme_is_matched_case_insensitively() -> None:
    assert bearer_token_from_header("bearer abc.def.ghi") == "abc.def.ghi"


@pytest.mark.parametrize("header", [None, "", "Basic dXNlcjpwYXNz", "Token abc"])
def test_a_missing_or_foreign_scheme_falls_through_to_the_cookie(header) -> None:
    assert bearer_token_from_header(header) is None


def test_a_bearer_header_with_no_token_is_an_error_rather_than_silence() -> None:
    """A client sending a credential it believes in deserves to be told it is malformed,
    not quietly downgraded to the cookie path."""
    with pytest.raises(UnauthenticatedError, match="no token"):
        bearer_token_from_header("Bearer    ")
