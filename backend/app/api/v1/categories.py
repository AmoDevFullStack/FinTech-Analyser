from flask import Blueprint, g, jsonify

from app.core.auth import require_auth
from app.core.errors import NotFoundError
from app.core.extensions import db
from app.repositories.category import CategoryRepository
from app.repositories.transaction import TransactionRepository
from app.schemas.base import parse_body
from app.schemas.requests import CategoryCorrectionRequest
from app.services.categorisation import CategorisationService

bp = Blueprint("categories", __name__, url_prefix="/categories")


@bp.get("")
@require_auth
def list_categories():
    categories = CategoryRepository(db.session).list_for_user(user_id=g.user_id)
    return (
        jsonify(
            {
                "data": [
                    {
                        "id": str(c.id),
                        "name": c.name,
                        "kind": c.kind.value,
                        "parent_id": str(c.parent_id) if c.parent_id else None,
                        "is_system": c.user_id is None,
                    }
                    for c in categories
                ]
            }
        ),
        200,
    )


@bp.post("/corrections")
@require_auth
def correct_category():
    """Record a user's category correction and learn from it immediately.

    specs/transactions.md: "Corrections also become training signal for that user's future
    categorisation" — so this returns how many other uncorrected transactions the
    correction moved, rather than silently improving them.
    """
    body = parse_body(CategoryCorrectionRequest)

    transaction = TransactionRepository(db.session).get_for_user(
        body.transaction_id, user_id=g.user_id
    )
    if transaction is None:
        raise NotFoundError("No transaction with that identifier exists for this user.")

    propagated = CategorisationService(db.session).correct(
        transaction,
        category_id=body.category_id,
        propagate=body.propagate,
    )
    return (
        jsonify(
            {
                "transaction_id": str(transaction.id),
                "category_id": str(transaction.category_id),
                "category_set_by_user": transaction.category_set_by_user,
                "also_recategorised": propagated,
            }
        ),
        200,
    )
