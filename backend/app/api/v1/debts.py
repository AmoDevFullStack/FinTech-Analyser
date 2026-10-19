from decimal import Decimal

from flask import Blueprint, g, jsonify

from app.core.auth import require_auth
from app.core.extensions import db
from app.schemas.base import parse_body, parse_query
from app.schemas.debt import (
    debt_dict,
    schedule_period_dict,
    strategy_comparison_dict,
    what_if_dict,
)
from app.schemas.requests import (
    CreateDebtRequest,
    ScheduleQuery,
    StrategiesQuery,
    UpdateDebtRequest,
    WhatIfQuery,
)
from app.services.debt import CreateDebtInput, DebtService, UpdateDebtInput

bp = Blueprint("debts", __name__, url_prefix="/debts")

DEFAULT_WHAT_IF_INCREMENTS = (Decimal("100"), Decimal("500"), Decimal("1000"))


@bp.get("")
@require_auth
def list_debts():
    debts = DebtService(db.session).list_for_user(user_id=g.user_id)
    return jsonify({"data": [debt_dict(d) for d in debts]}), 200


@bp.post("")
@require_auth
def create_debt():
    body = parse_body(CreateDebtRequest)
    debt = DebtService(db.session).create(
        user_id=g.user_id,
        data=CreateDebtInput(
            debt_type=body.debt_type,
            original_principal=body.original_principal,
            current_balance=body.current_balance,
            annual_rate=body.annual_rate,
            minimum_payment=body.minimum_payment,
            started_on=body.started_on,
            account_id=body.account_id,
            instalment=body.instalment,
            term_months=body.term_months,
        ),
    )
    return jsonify(debt_dict(debt)), 201


@bp.get("/<uuid:debt_id>")
@require_auth
def get_debt(debt_id):
    debt = DebtService(db.session).get(debt_id, user_id=g.user_id)
    return jsonify(debt_dict(debt)), 200


@bp.patch("/<uuid:debt_id>")
@require_auth
def update_debt(debt_id):
    body = parse_body(UpdateDebtRequest)
    debt = DebtService(db.session).update(
        debt_id,
        user_id=g.user_id,
        data=UpdateDebtInput(
            debt_type=body.debt_type,
            current_balance=body.current_balance,
            annual_rate=body.annual_rate,
            minimum_payment=body.minimum_payment,
            instalment=body.instalment,
            term_months=body.term_months,
        ),
    )
    return jsonify(debt_dict(debt)), 200


@bp.delete("/<uuid:debt_id>")
@require_auth
def delete_debt(debt_id):
    DebtService(db.session).soft_delete(debt_id, user_id=g.user_id)
    return "", 204


@bp.get("/<uuid:debt_id>/schedule")
@require_auth
def get_schedule(debt_id):
    """Computed synchronously — see docs/api.md: fast and deterministic."""
    query = parse_query(ScheduleQuery)
    periods = DebtService(db.session).schedule(
        debt_id, user_id=g.user_id, extra_monthly=query.extra_monthly
    )
    return jsonify({"data": [schedule_period_dict(p) for p in periods]}), 200


@bp.get("/<uuid:debt_id>/what-if")
@require_auth
def get_what_if(debt_id):
    """Months and interest saved at each of a set of extra-monthly increments, each
    compared against the same debt's baseline (extra_monthly=0) schedule.
    """
    query = parse_query(WhatIfQuery)
    increments = (
        tuple(query.increments) if query.increments else DEFAULT_WHAT_IF_INCREMENTS
    )
    results = DebtService(db.session).what_if(
        debt_id, user_id=g.user_id, increments=increments
    )
    return jsonify({"data": [what_if_dict(r) for r in results]}), 200


@bp.get("/strategies")
@require_auth
def get_strategies():
    """Compares avalanche, snowball, and (where `consolidation_rate` is supplied)
    consolidation across the user's full debt set. See docs/api.md.
    """
    query = parse_query(StrategiesQuery)
    comparison = DebtService(db.session).compare_strategies(
        user_id=g.user_id,
        total_monthly=query.total_monthly,
        consolidation_rate=query.consolidation_rate,
        consolidation_fee=query.consolidation_fee,
    )
    return jsonify(strategy_comparison_dict(comparison)), 200
