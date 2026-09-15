from flask import Blueprint

from app.api.v1.accounts import bp as accounts_bp
from app.api.v1.auth import bp as auth_bp
from app.api.v1.categories import bp as categories_bp
from app.api.v1.debts import bp as debts_bp
from app.api.v1.health import bp as health_bp
from app.api.v1.imports import bp as imports_bp
from app.api.v1.operational import bp as operational_bp
from app.api.v1.position import bp as position_bp
from app.api.v1.scenarios import bp as scenarios_bp
from app.api.v1.transactions import bp as transactions_bp

api_v1 = Blueprint("api_v1", __name__, url_prefix="/api/v1")

for blueprint in (
    auth_bp,
    accounts_bp,
    transactions_bp,
    imports_bp,
    categories_bp,
    debts_bp,
    position_bp,
    scenarios_bp,
    health_bp,
    operational_bp,
):
    api_v1.register_blueprint(blueprint)
