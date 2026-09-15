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

    return app
