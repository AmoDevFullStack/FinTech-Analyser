"""Fixtures requiring a real Postgres instance — run via `docker compose exec backend
pytest`, per README.md. These are not exercised by the sandboxed session that wrote this
code; see the handover notes for what was actually run.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("FLASK_ENV", "testing")
os.environ.setdefault("SECRET_KEY", "test-secret")

from app import create_app
from app.core.extensions import db as _db


@pytest.fixture()
def app():
    application = create_app()
    with application.app_context():
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
