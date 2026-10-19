"""Fixtures requiring a real Postgres instance — run via `docker compose exec backend
pytest`, per README.md.

These fixtures create and drop every table, so pointing them at the wrong database
destroys real data. That is not hypothetical: `setdefault("FLASK_ENV", "testing")` here
silently did nothing, because docker-compose passes `FLASK_ENV=development` from `.env`,
so the whole suite ran against the development database and `drop_all()` deleted its
contents. Hence both the assignment below and `_assert_safe_database`, which fails
collection rather than trusting the configuration to be right.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text

# Assignment, not setdefault: the container already has FLASK_ENV=development set, and
# setdefault would keep it — which is exactly the bug described above.
os.environ["FLASK_ENV"] = "testing"
os.environ.setdefault("SECRET_KEY", "test-secret")

from app import create_app  # noqa: E402
from app.core.config import load_config  # noqa: E402
from app.core.extensions import db as _db  # noqa: E402
from app.models.schemas import ensure_schemas  # noqa: E402

# A database this suite is willing to drop tables in. Anything else is someone's data.
SAFE_DATABASE_SUFFIXES = ("_test", "_tests")


def _database_name(uri: str) -> str:
    return uri.rsplit("/", 1)[-1].split("?")[0]


def _assert_safe_database() -> None:
    """Refuse to run against a database that is not obviously a test database.

    Checked at import time so collection fails before any fixture can drop a table. The
    check is on the resolved URI rather than on FLASK_ENV, because the failure being
    guarded against was precisely FLASK_ENV not being what the file assumed.
    """
    uri = load_config().SQLALCHEMY_DATABASE_URI
    name = _database_name(uri)
    if not name.endswith(SAFE_DATABASE_SUFFIXES):
        raise RuntimeError(
            f"Refusing to run the test suite against database {name!r}: these fixtures "
            f"call drop_all() and would delete its contents. Point TEST_DATABASE_URL at "
            f"a database whose name ends in {' or '.join(SAFE_DATABASE_SUFFIXES)}, and "
            f"create it first:\n"
            f"    docker compose exec postgres createdb -U fdt fdt_test"
        )


_assert_safe_database()


@pytest.fixture()
def app():
    application = create_app()
    with application.app_context():
        # Schemas first: every table declares one (app/models/schemas.py) and create_all
        # builds tables, never the schemas holding them — without this the first table
        # fails with InvalidSchemaName on a fresh database.
        #
        # `citext` too: `users.email` is CITEXT, and create_all does not install the
        # extension its column type needs. Migration 0001 does that for a real database;
        # these fixtures build their tables from the models instead, so they have to say it
        # themselves.
        with _db.engine.connect() as connection:
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS citext"))
            ensure_schemas(connection)
            connection.commit()

        # Drop before creating as well as after: a run interrupted mid-test leaves tables
        # behind, and starting from them makes the next run fail on whatever unique
        # constraint the leftover rows happen to violate rather than on anything real.
        _db.drop_all()
        _db.create_all()
        yield application
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def session(app):
    return _db.session


@pytest.fixture()
def client(app):
    return app.test_client()
