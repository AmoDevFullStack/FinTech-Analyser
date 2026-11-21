"""What is running, and whether the database it talks to matches it.

Two questions a deploy pipeline has to be able to ask a running container:

1. Which build is this? Answered by `BuildInfo`, populated from the APP_VERSION / BUILD_SHA /
   BUILD_TIME values the image is built with (see .github/workflows/cd.yml). Without it, a
   smoke test after a deploy can pass against the *previous* container and nobody notices.

2. Is the schema the one this code was written against? Answered by `check_readiness`. The
   code carries its own Alembic head; the database records which revision it is at. If they
   differ, the container is up but not ready — the migration step was skipped or failed —
   and `/ready` says so with a 503 instead of serving requests that will fail on a missing
   column.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.db import DbSession

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"

# Alembic's bookkeeping table lives in `public` (see migrations/env.py, VERSION_TABLE_SCHEMA).
VERSION_TABLE = "public.alembic_version"

_PING = text("SELECT 1")
_VERSION_TABLE_EXISTS = text("SELECT to_regclass(:table_name) IS NOT NULL")
_APPLIED_REVISIONS = text("SELECT version_num FROM public.alembic_version")


@dataclass(frozen=True, slots=True)
class BuildInfo:
    version: str
    commit: str
    built_at: str | None

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> BuildInfo:
        return cls(
            version=str(config.get("APP_VERSION", "dev")),
            commit=str(config.get("BUILD_SHA", "unknown")),
            built_at=config.get("BUILD_TIME") or None,
        )

    def as_dict(self) -> dict[str, str | None]:
        return {"version": self.version, "commit": self.commit, "built_at": self.built_at}


@dataclass(frozen=True, slots=True)
class Readiness:
    database: bool
    schema_current: bool
    expected_revisions: frozenset[str]
    applied_revisions: frozenset[str]

    @property
    def ready(self) -> bool:
        return self.database and self.schema_current

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": "ok" if self.ready else "unavailable",
            "database": self.database,
            "schema_current": self.schema_current,
            "expected_revisions": sorted(self.expected_revisions),
            "applied_revisions": sorted(self.applied_revisions),
        }


@lru_cache(maxsize=1)
def expected_revisions() -> frozenset[str]:
    """The Alembic head(s) shipped with this code. Read once: they cannot change at runtime."""
    return frozenset(ScriptDirectory(str(MIGRATIONS_DIR)).get_heads())


def applied_revisions(session: DbSession) -> frozenset[str]:
    """The revision(s) the database says it is at; empty if it was never migrated."""
    exists: bool | None = session.execute(
        _VERSION_TABLE_EXISTS, {"table_name": VERSION_TABLE}
    ).scalar_one()
    if not exists:
        return frozenset()
    return frozenset(session.execute(_APPLIED_REVISIONS).scalars().all())


def check_readiness(session: DbSession) -> Readiness:
    """Probe the database and compare its revision with the code's.

    Catches database errors deliberately: a readiness probe that raises returns a 500, which
    an orchestrator cannot tell apart from a bug in the probe. The session is rolled back on
    failure so a pooled connection is not handed on in an aborted transaction.
    """
    expected = expected_revisions()
    try:
        session.execute(_PING)
        applied = applied_revisions(session)
    except SQLAlchemyError:
        session.rollback()
        return Readiness(
            database=False,
            schema_current=False,
            expected_revisions=expected,
            applied_revisions=frozenset(),
        )
    return Readiness(
        database=True,
        schema_current=applied == expected,
        expected_revisions=expected,
        applied_revisions=applied,
    )
