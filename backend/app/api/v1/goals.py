from datetime import date
from decimal import Decimal

from flask import Blueprint, g, jsonify, request

from app.core.auth import require_auth
from app.core.errors import ValidationError
from app.core.extensions import db
from app.schemas.goal import funding_plan_dict, goal_dict, progress_dict
from app.services.goal import CreateGoalInput, GoalService, UpdateGoalInput

bp = Blueprint("goals", __name__, url_prefix="/goals")


def _decimal(body: dict, key: str) -> Decimal | None:
    value = body.get(key)
    return Decimal(str(value)) if value is not None else None


@bp.get("")
@require_auth
def list_goals():
    goals = GoalService(db.session).list_for_user(user_id=g.user_id)
    return jsonify({"data": [goal_dict(goal) for goal in goals]}), 200


@bp.post("")
@require_auth
def create_goal():
    body = request.get_json(force=True, silent=True) or {}
    for required in ("name", "target_amount", "target_date"):
        if body.get(required) is None:
            raise ValidationError(f"'{required}' is required.")

    goal = GoalService(db.session).create(
        user_id=g.user_id,
        data=CreateGoalInput(
            name=body["name"],
            target_amount=Decimal(str(body["target_amount"])),
            target_date=date.fromisoformat(body["target_date"]),
            priority=int(body.get("priority", 1)),
            account_id=body.get("account_id"),
            opening_amount=Decimal(str(body.get("opening_amount", "0"))),
            planned_monthly_contribution=_decimal(body, "planned_monthly_contribution"),
        ),
    )
    return jsonify(goal_dict(goal)), 201


@bp.get("/funding-plan")
@require_auth
def get_funding_plan():
    """Competition across goals — which are funded, in what order, and what slips."""
    plan = GoalService(db.session).funding_plan(user_id=g.user_id)
    return jsonify(funding_plan_dict(plan)), 200


@bp.get("/<uuid:goal_id>")
@require_auth
def get_goal(goal_id):
    goal = GoalService(db.session).get(goal_id, user_id=g.user_id)
    return jsonify(goal_dict(goal)), 200


@bp.patch("/<uuid:goal_id>")
@require_auth
def update_goal(goal_id):
    body = request.get_json(force=True, silent=True) or {}
    goal = GoalService(db.session).update(
        goal_id,
        user_id=g.user_id,
        data=UpdateGoalInput(
            name=body.get("name"),
            target_amount=_decimal(body, "target_amount"),
            target_date=(
                date.fromisoformat(body["target_date"]) if body.get("target_date") else None
            ),
            priority=int(body["priority"]) if body.get("priority") is not None else None,
            account_id=body.get("account_id"),
            planned_monthly_contribution=_decimal(body, "planned_monthly_contribution"),
        ),
    )
    return jsonify(goal_dict(goal)), 200


@bp.delete("/<uuid:goal_id>")
@require_auth
def delete_goal(goal_id):
    GoalService(db.session).soft_delete(goal_id, user_id=g.user_id)
    return "", 204


@bp.get("/<uuid:goal_id>/progress")
@require_auth
def get_progress(goal_id):
    view = GoalService(db.session).progress(goal_id, user_id=g.user_id)
    return jsonify(progress_dict(view)), 200


@bp.post("/<uuid:goal_id>/contributions")
@require_auth
def add_contribution(goal_id):
    body = request.get_json(force=True, silent=True) or {}
    if body.get("amount") is None:
        raise ValidationError("'amount' is required.")

    contribution = GoalService(db.session).record_contribution(
        goal_id,
        user_id=g.user_id,
        amount=Decimal(str(body["amount"])),
        occurred_on=(
            date.fromisoformat(body["occurred_on"])
            if body.get("occurred_on")
            else date.today()
        ),
        note=body.get("note"),
    )
    return (
        jsonify(
            {
                "id": str(contribution.id),
                "goal_id": str(contribution.goal_id),
                "amount": str(contribution.amount),
                "occurred_on": contribution.occurred_on.isoformat(),
                "note": contribution.note,
            }
        ),
        201,
    )
