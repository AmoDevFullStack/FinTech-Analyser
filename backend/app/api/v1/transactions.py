"""Transaction list, search, manual entry, and the detection dry run. See docs/api.md."""

from flask import Blueprint, g, jsonify

from app.core.auth import require_auth
from app.core.extensions import db
from app.domain.payment_taxonomy import classify_payment
from app.repositories.transaction import TransactionRepository
from app.schemas.base import parse_body, parse_query
from app.schemas.insight import insight_dict
from app.schemas.requests import (
    ClassifyRequest,
    ManualTransactionRequest,
    MonthlySummaryQuery,
    TransactionQuery,
)
from app.schemas.transaction import (
    classification_dict,
    month_report_dict,
    transaction_dict,
    transaction_match_dict,
)
from app.services.monthly_summary import MonthlySummaryService
from app.services.spending_insight import SpendingInsightService
from app.services.transaction import ManualTransactionInput, TransactionService

bp = Blueprint("transactions", __name__, url_prefix="/transactions")


@bp.get("")
@require_auth
def list_transactions():
    """Filtered, searchable transaction list.

    `q` matches by edit distance unless `fuzzy=false` — see
    `TransactionRepository.search`. Each row carries `match_score` and `match_basis` so a
    client can show a user why a result they did not type exactly is in the list.
    """
    query = parse_query(TransactionQuery)
    matches = TransactionRepository(db.session).search(
        user_id=g.user_id,
        account_id=query.account_id,
        since=query.since,
        until=query.until,
        category_id=query.category_id,
        min_amount=query.min_amount,
        max_amount=query.max_amount,
        direction=query.direction,
        payment_method=query.payment_method,
        spending_purpose=query.spending_purpose,
        is_recurring=query.is_recurring,
        uncategorised_only=query.uncategorised_only,
        q=query.q,
        fuzzy=query.fuzzy,
        min_score=query.min_score,
        limit=query.limit,
    )

    return (
        jsonify(
            {
                "data": [transaction_match_dict(match) for match in matches],
                "next_cursor": None,
                "search": {
                    "q": query.q,
                    "fuzzy": query.fuzzy and bool(query.q),
                    "min_score": str(query.min_score),
                },
            }
        ),
        200,
    )


@bp.get("/months")
@require_auth
def monthly_summary():
    """Month by month: what each one was, what changed, and what the cash did.

    The list endpoint answers "what happened", over whatever window was asked for. This
    one answers "how does this month compare with the last" — whole calendar months, each
    against its predecessor, with the account balance walked back so a month shows what was
    actually there rather than only what moved.

    Declared above `/<uuid:transaction_id>` deliberately: Flask matches in registration
    order and a later literal route loses to an earlier converter.
    """
    query = parse_query(MonthlySummaryQuery)
    reports = MonthlySummaryService(db.session).summary(
        user_id=g.user_id,
        since=query.since,
        until=query.until,
        account_id=query.account_id,
    )
    return (
        jsonify(
            {
                "data": [month_report_dict(report) for report in reports],
                "months": len(reports),
            }
        ),
        200,
    )


@bp.post("")
@require_auth
def create_transaction():
    """Record one transaction by hand, and report what it changed.

    specs/transactions.md lists manual entry as an input alongside CSV; this is that path.
    The response carries the same impact report an import commit returns, because one
    R14,500 rent payment moves the same figures a statement full of them does.
    """
    body = parse_body(ManualTransactionRequest)
    created = TransactionService(db.session).create(
        user_id=g.user_id,
        data=ManualTransactionInput(
            account_id=body.account_id,
            occurred_on=body.occurred_on,
            amount=body.amount,
            description=body.description,
            category_id=body.category_id,
        ),
    )
    return (
        jsonify(
            {
                **transaction_dict(created.transaction),
                "insight": insight_dict(created.insight),
            }
        ),
        201,
    )


@bp.post("/classify")
@require_auth
def classify():
    """Read a description without storing anything.

    Lets a client show "we read this as a rent debit order, essential" while the user is
    still typing, and lets a reviewer check a rule without importing a file.
    """
    body = parse_body(ClassifyRequest)
    classification = classify_payment(description=body.description, amount=body.amount)
    return jsonify(classification_dict(classification, amount=body.amount)), 200


@bp.post("/reclassify")
@require_auth
def reclassify():
    """Re-run detection over this user's whole history.

    Explicit and user-initiated by design. Migration 0013 deliberately does not backfill:
    re-running a changed rule table over existing history moves figures a user has already
    seen, and doing that silently inside a deploy leaves no record of why a number changed.
    Categories are untouched — this rewrites what the statement said, never what the user
    decided it meant.
    """
    updated = SpendingInsightService(db.session).reclassify_history(user_id=g.user_id)
    return jsonify({"transactions_reclassified": updated}), 200


@bp.get("/<uuid:transaction_id>")
@require_auth
def get_transaction(transaction_id):
    transaction = TransactionService(db.session).get(transaction_id, user_id=g.user_id)
    return jsonify(transaction_dict(transaction)), 200
