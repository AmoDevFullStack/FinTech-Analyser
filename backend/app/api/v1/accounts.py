from datetime import date
from decimal import Decimal

from flask import Blueprint, g, jsonify, request

from app.core.auth import require_auth
from app.core.errors import ValidationError
from app.core.extensions import db
from app.models.account import AccountType
from app.schemas.account import account_dict
from app.services.account import AccountService, CreateAccountInput, UpdateAccountInput

bp = Blueprint("accounts", __name__, url_prefix="/accounts")


@bp.get("")
@require_auth
def list_accounts():
    include_archived = request.args.get("include_archived", "false").lower() == "true"
    service = AccountService(db.session)
    views = service.list_for_user(user_id=g.user_id, include_archived=include_archived)
    return jsonify({"data": [account_dict(v) for v in views]}), 200


@bp.post("")
@require_auth
def create_account():
    body = request.get_json(force=True, silent=True) or {}
    try:
        account_type = AccountType(body.get("account_type"))
    except ValueError as exc:
        raise ValidationError(f"Unknown account_type: {body.get('account_type')!r}") from exc

    if not body.get("name"):
        raise ValidationError("'name' is required.")

    service = AccountService(db.session)
    account = service.create(
        user_id=g.user_id,
        data=CreateAccountInput(
            name=body["name"],
            account_type=account_type,
            institution=body.get("institution"),
            opening_balance=Decimal(str(body.get("opening_balance", "0"))),
            opened_on=date.fromisoformat(body["opened_on"]) if body.get("opened_on") else None,
            interest_rate=Decimal(str(body["interest_rate"])) if body.get("interest_rate") else None,
            credit_limit=Decimal(str(body["credit_limit"])) if body.get("credit_limit") else None,
        ),
    )
    view = service.get(account.id, user_id=g.user_id)
    return jsonify(account_dict(view)), 201


@bp.get("/<uuid:account_id>")
@require_auth
def get_account(account_id):
    view = AccountService(db.session).get(account_id, user_id=g.user_id)
    return jsonify(account_dict(view)), 200


@bp.patch("/<uuid:account_id>")
@require_auth
def update_account(account_id):
    body = request.get_json(force=True, silent=True) or {}
    service = AccountService(db.session)
    service.update(
        account_id,
        user_id=g.user_id,
        data=UpdateAccountInput(
            name=body.get("name"),
            institution=body.get("institution"),
            opened_on=date.fromisoformat(body["opened_on"]) if body.get("opened_on") else None,
            interest_rate=Decimal(str(body["interest_rate"])) if body.get("interest_rate") else None,
            credit_limit=Decimal(str(body["credit_limit"])) if body.get("credit_limit") else None,
            manual_balance=Decimal(str(body["balance"])) if body.get("balance") else None,
        ),
    )
    view = service.get(account_id, user_id=g.user_id)
    return jsonify(account_dict(view)), 200


@bp.post("/<uuid:account_id>/archive")
@require_auth
def archive_account(account_id):
    service = AccountService(db.session)
    service.archive(account_id, user_id=g.user_id)
    view = service.get(account_id, user_id=g.user_id)
    return jsonify(account_dict(view)), 200


@bp.delete("/<uuid:account_id>")
@require_auth
def delete_account(account_id):
    AccountService(db.session).soft_delete(account_id, user_id=g.user_id)
    return "", 204
