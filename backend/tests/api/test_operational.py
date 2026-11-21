"""The endpoints the deploy pipeline polls: /health, /ready, /version."""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import text

from app.core.extensions import db
from app.core.release import expected_revisions

_CREATE_VERSION_TABLE = text(
    "CREATE TABLE IF NOT EXISTS public.alembic_version ("
    "version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
)
_STAMP = text("INSERT INTO public.alembic_version (version_num) VALUES (:revision)")
_DROP_VERSION_TABLE = text("DROP TABLE IF EXISTS public.alembic_version")


@pytest.fixture()
def stamped_at(app: Flask) -> Iterator[Callable[[str], None]]:
    """Record a revision the way `alembic upgrade` would, then remove the table again.

    The suite builds tables with create_all, which never writes alembic_version, and drop_all
    only drops tables in the models' metadata — so this fixture owns the cleanup.
    """

    def _stamp(revision: str) -> None:
        db.session.execute(_CREATE_VERSION_TABLE)
        db.session.execute(_STAMP, {"revision": revision})
        db.session.commit()

    yield _stamp
    db.session.rollback()
    db.session.execute(_DROP_VERSION_TABLE)
    db.session.commit()


def test_health_is_ok_without_consulting_the_database(client: FlaskClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_ready_is_unavailable_when_the_database_was_never_migrated(client: FlaskClient) -> None:
    response = client.get("/api/v1/ready")
    body = response.get_json()

    assert response.status_code == 503
    assert body["database"] is True
    assert body["schema_current"] is False
    assert body["applied_revisions"] == []
    assert body["expected_revisions"] == sorted(expected_revisions())


def test_ready_is_unavailable_when_the_schema_is_behind(
    client: FlaskClient, stamped_at: Callable[[str], None]
) -> None:
    stamped_at("0001")

    response = client.get("/api/v1/ready")

    assert response.status_code == 503
    assert response.get_json()["applied_revisions"] == ["0001"]


def test_ready_is_ok_at_the_shipped_head(
    client: FlaskClient, stamped_at: Callable[[str], None]
) -> None:
    (head,) = expected_revisions()
    stamped_at(head)

    response = client.get("/api/v1/ready")

    assert response.status_code == 200
    assert response.get_json()["schema_current"] is True


def test_version_reports_the_configured_build(app: Flask, client: FlaskClient) -> None:
    app.config.update(APP_VERSION="1.4.0", BUILD_SHA="abc1234", BUILD_TIME="")

    response = client.get("/api/v1/version")

    assert response.status_code == 200
    assert response.get_json() == {"version": "1.4.0", "commit": "abc1234", "built_at": None}
