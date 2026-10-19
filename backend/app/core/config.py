from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None:
        raise RuntimeError(f"required environment variable {name} is not set")
    return value


@dataclass(frozen=True, slots=True)
class Config:
    """Process configuration, read once at startup. Never read `os.environ` elsewhere."""

    SECRET_KEY: str = field(default_factory=lambda: _env("SECRET_KEY"))
    SQLALCHEMY_DATABASE_URI: str = field(default_factory=lambda: _env("DATABASE_URL"))
    REDIS_URL: str = field(default_factory=lambda: _env("REDIS_URL", "redis://redis:6379/0"))

    SESSION_COOKIE_NAME: str = "fdt_session"
    SESSION_COOKIE_HTTPONLY: bool = True
    SESSION_COOKIE_SAMESITE: str = "Lax"
    SESSION_COOKIE_SECURE: bool = field(
        default_factory=lambda: os.environ.get("FLASK_ENV") != "development"
    )

    LOGIN_RATE_LIMIT: str = "5 per 15 minutes"

    # JWT (docs/api.md, "Authentication"). The session cookie above is still issued and
    # still accepted, because the browser client and the e2e suite were built against it;
    # a bearer token is the additional path, for clients that cannot hold a cookie.
    #
    # JWT_SECRET_KEY defaults to SECRET_KEY rather than being separately required, so an
    # existing deployment keeps working after this change. Setting it separately is the
    # better posture: rotating the signing key then does not invalidate every session
    # cookie at the same time.
    JWT_SECRET_KEY: str = field(
        default_factory=lambda: os.environ.get("JWT_SECRET_KEY") or _env("SECRET_KEY")
    )
    JWT_ALGORITHM: str = "HS256"
    JWT_ISSUER: str = "financial-digital-twin"
    # Fifteen minutes. An access token cannot be revoked before it expires, so its lifetime
    # IS the revocation window — every minute added here is a minute a stolen token keeps
    # working after a logout.
    JWT_ACCESS_TTL_SECONDS: int = field(
        default_factory=lambda: int(os.environ.get("JWT_ACCESS_TTL_SECONDS", "900"))
    )
    # Thirty days. The refresh token is revocable (see app/core/tokens.py), so a long life
    # here costs far less than a long-lived access token.
    JWT_REFRESH_TTL_SECONDS: int = field(
        default_factory=lambda: int(os.environ.get("JWT_REFRESH_TTL_SECONDS", str(30 * 86400)))
    )

    # Narration provider (ADR-002). Optional by design: with no key the app runs
    # NullInterpreter and the assistant returns figures with `narration_available: false`,
    # which is the path requirement 12 keeps working and the one developed against.
    OPENAI_API_KEY: str = field(default_factory=lambda: os.environ.get("OPENAI_API_KEY", ""))
    OPENAI_MODEL: str = field(
        default_factory=lambda: os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    )
    OPENAI_BASE_URL: str = field(default_factory=lambda: os.environ.get("OPENAI_BASE_URL", ""))
    # Short on purpose: narration is the optional half of the response, so waiting on it
    # is worse than shipping the figures without it.
    OPENAI_TIMEOUT_SECONDS: float = field(
        default_factory=lambda: float(os.environ.get("OPENAI_TIMEOUT_SECONDS", "8"))
    )

    SQLALCHEMY_ENGINE_OPTIONS: dict = field(
        default_factory=lambda: {"pool_pre_ping": True}
    )
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False

    TESTING: bool = False


@dataclass(frozen=True, slots=True)
class TestConfig(Config):
    SECRET_KEY: str = "test-secret"
    SQLALCHEMY_DATABASE_URI: str = field(
        default_factory=lambda: os.environ.get(
            "TEST_DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/fdt_test"
        )
    )
    REDIS_URL: str = "redis://localhost:6379/1"
    SESSION_COOKIE_SECURE: bool = False
    TESTING: bool = True
    JWT_SECRET_KEY: str = "test-secret"
    # No test ever calls a provider. Blank here regardless of the developer's environment,
    # so a key exported for local use cannot make the suite hit the network.
    OPENAI_API_KEY: str = ""


def load_config() -> Config:
    if os.environ.get("FLASK_ENV") == "testing":
        return TestConfig()
    return Config()
