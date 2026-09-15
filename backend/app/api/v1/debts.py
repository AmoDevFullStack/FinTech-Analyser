from datetime import date
from decimal import Decimal

from flask import Blueprint, g, jsonify, request

from app.core.auth import require_auth
from app.core.errors import ValidationError
from app.core.extensions import db
from app.models.debt import DebtType
from app.schemas.debt import (
    debt_dict,
    schedule_period_dict,
    strategy_comparison_dict,
    what_if_dict,
)
from app.services.debt import CreateDebtInput, DebtService, UpdateDebtInput

bp = Blueprint("debts", __name__, url_prefix="/debts")


def _decimal(body: dict, key: str) -> Decimal | None:
    value = body.get(key)
    return Decimal(str(value)) if value is not None else None


def _int(body: dict, key: str) -> int | None:
    """Coerce at the boundary: the client sends whatever its form produced, and this is
    where a value becomes typed. The frontend is forbidden from narrowing strings to
    numbers itself (docs/frontend.md §4), so it sends them as-is.
    """
    value = body.get(key)
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"'{key}' must be a whole number.") from exc


@bp.get("")
@require_auth
def list_debts():
    debts = DebtService(db.session).list_for_user(user_id=g.user_id)
    return jsonify({"data": [debt_dict(d) for d in debts]}), 200


@bp.post("")
@require_auth
def create_debt():
    body = request.get_json(force=True, silent=True) or {}
    try:
        debt_type = DebtType(body.get("debt_type"))
    except ValueError as exc:
        raise ValidationError(f"Unknown debt_type: {body.get('debt_type')!r}") from exc

    for required in ("original_principal", "current_balance", "annual_rate", "minimum_payment", "started_on"):
        if body.get(required) is None:
            raise ValidationError(f"'{required}' is required.")

    service = DebtService(db.session)
    debt = service.create(
        user_id=g.user_id,
        data=CreateDebtInput(
            debt_type=debt_type,
            original_principal=Decimal(str(body["original_principal"])),
            current_balance=Decimal(str(body["current_balance"])),
            annual_rate=Decimal(str(body["annual_rate"])),
            minimum_payment=Decimal(str(body["minimum_payment"])),
            started_on=date.fromisoformat(body["started_on"]),
            account_id=body.get("account_id"),
            instalment=_decimal(body, "instalment"),
            term_months=_int(body, "term_months"),
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
    body = request.get_json(force=True, silent=True) or {}
    debt_type = DebtType(body["debt_type"]) if body.get("debt_type") is not None else None

    debt = DebtService(db.session).update(
        debt_id,
        user_id=g.user_id,
        data=UpdateDebtInput(
            debt_type=debt_type,
            current_balance=_decimal(body, "current_balance"),
            annual_rate=_decimal(body, "annual_rate"),
            minimum_payment=_decimal(body, "minimum_payment"),
            instalment=_decimal(body, "instalment"),
            term_months=_int(body, "term_months"),
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
    extra_monthly = Decimal(str(request.args.get("extra_monthly", "0")))
    periods = DebtService(db.session).schedule(
        debt_id, user_id=g.user_id, extra_monthly=extra_monthly
    )
    return jsonify({"data": [schedule_period_dict(p) for p in periods]}), 200


@bp.get("/<uuid:debt_id>/what-if")
@require_auth
def get_what_if(debt_id):
    """Months and interest saved at each of a set of extra-monthly increments, each
    compared against the same debt's baseline (extra_monthly=0) schedule.
    """
    raw = request.args.get("increments")
    increments = (
        tuple(Decimal(v) for v in raw.split(","))
        if raw
        else (Decimal("100"), Decimal("500"), Decimal("1000"))
    )
    results = DebtService(db.session).what_if(debt_id, user_id=g.user_id, increments=increments)
    return jsonify({"data": [what_if_dict(r) for r in results]}), 200


@bp.get("/strategies")
@require_auth
def get_strategies():
    """Compares avalanche, snowball, and (where `consolidation_rate` is supplied)
    consolidation across the user's full debt set. See docs/api.md.
    """
    total_monthly = (
        Decimal(str(request.args["total_monthly"])) if "total_monthly" in request.args else None
    )
    consolidation_rate = (
        Decimal(str(request.args["consolidation_rate"]))
        if "consolidation_rate" in request.args
        else None
    )
    consolidation_fee = Decimal(str(request.args.get("consolidation_fee", "0")))

    comparison = DebtService(db.session).compare_strategies(
        user_id=g.user_id,
        total_monthly=total_monthly,
        consolidation_rate=consolidation_rate,
        consolidation_fee=consolidation_fee,
    )
    return jsonify(strategy_comparison_dict(comparison)), 200
