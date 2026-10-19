from __future__ import annotations

from flask import Flask

from app.api.v1 import api_v1
from app.core.config import load_config
from app.core.errors import register_error_handlers
from app.core.extensions import db, limiter, migrate


def create_app() -> Flask:
    app = Flask(__name__)
    config = load_config()
    app.config.from_object(config)

    db.init_app(app)
    migrate.init_app(app, db)
    limiter.init_app(app)

    register_error_handlers(app)
    app.register_blueprint(api_v1)

    from app import cli

    cli.register(app)

    # Imported for its side effect: the module's decorators are what put handlers in the
    # registry, and an event with no handler registered is silently a no-op. Imported here
    # rather than in app/core/events.py, which must not know which services exist.
    from app.services import event_handlers  # noqa: F401

    return app
