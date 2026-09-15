from datetime import date
from decimal import Decimal
from uuid import UUID

from flask import Blueprint, g, jsonify, request

from app.core.auth import require_auth
from app.core.errors import NotFoundError
from app.core.extensions import db
from app.models.transaction import Transaction
from app.repositories.transaction import TransactionRepository
from app.schemas.transaction import transaction_dict

bp = Blueprint("transactions", __name__, url_prefix="/transactions")


@bp.get("")
@require_auth
def list_transactions():
    args = request.args
    repo = TransactionRepository(db.session)

    if args.get("account_id"):
        transactions = repo.by_account(
            UUID(args["account_id"]),
            user_id=g.user_id,
            since=date.fromisoformat(args["from"]) if args.get("from") else None,
            until=date.fromisoformat(args["to"]) if args.get("to") else None,
            category_id=UUID(args["category_id"]) if args.get("category_id") else None,
            min_amount=Decimal(args["min_amount"]) if args.get("min_amount") else None,
            max_amount=Decimal(args["max_amount"]) if args.get("max_amount") else None,
            q=args.get("q"),
            limit=int(args.get("limit", 50)),
        )
    else:
        transactions = repo.for_user(
            user_id=g.user_id,
            since=date.fromisoformat(args["from"]) if args.get("from") else None,
            until=date.fromisoformat(args["to"]) if args.get("to") else None,
            limit=int(args.get("limit", 50)),
        )

    return jsonify({"data": [transaction_dict(t) for t in transactions], "next_cursor": None}), 200


@bp.get("/<uuid:transaction_id>")
@require_auth
def get_transaction(transaction_id):
    txn = db.session.get(Transaction, transaction_id)
    if txn is None or txn.user_id != g.user_id or txn.deleted_at is not None:
        raise NotFoundError("No transaction with that identifier exists for this user.")
    return jsonify(transaction_dict(txn)), 200
