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


def load_config() -> Config:
    if os.environ.get("FLASK_ENV") == "testing":
        return TestConfig()
    return Config()
