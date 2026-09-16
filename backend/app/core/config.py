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
    # No test ever calls a provider. Blank here regardless of the developer's environment,
    # so a key exported for local use cannot make the suite hit the network.
    OPENAI_API_KEY: str = ""


def load_config() -> Config:
    if os.environ.get("FLASK_ENV") == "testing":
        return TestConfig()
    return Config()
