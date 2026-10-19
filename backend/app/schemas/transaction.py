from decimal import Decimal

from app.models.transaction import Transaction
from app.repositories.transaction import TransactionMatch


def transaction_dict(txn: Transaction) -> dict:
    return {
        "id": str(txn.id),
        "account_id": str(txn.account_id),
        "category_id": str(txn.category_id) if txn.category_id else None,
        "occurred_on": txn.occurred_on.isoformat(),
        "amount": str(txn.amount),
        "description": txn.description,
        "normalised_description": txn.normalised_description,
        "direction": txn.direction.value,
        "is_recurring": txn.is_recurring,
        "category_confidence": (
            str(txn.category_confidence) if txn.category_confidence is not None else None
        ),
        "category_set_by_user": txn.category_set_by_user,
        # Spending detection. Null on any row imported before migration 0013 and never
        # reclassified — the client renders the absence rather than inventing "unknown",
        # because "we have not looked at this row" and "we looked and could not tell" are
        # different things and only the second one is worth showing a user.
        "payment_method": txn.payment_method.value if txn.payment_method else None,
        "spending_purpose": txn.spending_purpose.value if txn.spending_purpose else None,
        "merchant": txn.merchant,
        "purpose_confidence": (
            str(txn.purpose_confidence) if txn.purpose_confidence is not None else None
        ),
    }


def transaction_match_dict(match: TransactionMatch) -> dict:
    """A search result: the transaction, plus how it matched.

    `match_score` and `match_basis` are on the envelope rather than on the transaction,
    because they are facts about this query and not about the row. The same transaction
    returned by a different search has a different score.
    """
    payload = transaction_dict(match.transaction)
    payload["match_score"] = str(match.score)
    payload["match_basis"] = match.basis
    return payload


def classification_dict(classification, *, amount: Decimal) -> dict:
    """The dry-run response for `POST /transactions/classify`.

    Both confidences travel, separately, because the two halves are decided by separate
    evidence: "DEBIT ORDER 4471992" is a certain method and an unknown purpose, and a
    single blended number would hide that.
    """
    return {
        "amount": str(amount),
        "payment_method": classification.method.value,
        "spending_purpose": classification.purpose.value,
        "kind": classification.kind.value if classification.kind is not None else None,
        "merchant": classification.merchant,
        "method_confidence": str(classification.method_confidence),
        "purpose_confidence": str(classification.purpose_confidence),
        "matched_rule": classification.matched_rule,
    }


def month_report_dict(report) -> dict:
    """One month of history, for `GET /transactions/months`.

    Money is a string, per ADR-001. `changes` is an object keyed by metric rather than a
    list, because a client renders one named figure at a time — "what happened to
    discretionary" — and looking that up by scanning a list is the client writing a join
    the response could have avoided.
    """
    comparison = report.comparison
    totals = comparison.totals
    balance = report.balance

    return {
        "month": comparison.month,
        "previous_month": comparison.previous_month,
        "totals": {
            "income": str(totals.income),
            "essential": str(totals.essential),
            "discretionary": str(totals.discretionary),
            "saving": str(totals.saving),
            "debt_service": str(totals.debt_service),
            "spending": str(totals.spending),
            "net": str(totals.net),
        },
        "changes": {
            change.metric: {
                "previous": str(change.previous),
                "current": str(change.current),
                "change": str(change.change),
                # Null where the previous month was zero. The client shows the amount and
                # no percentage, rather than a 0% that would read as "unchanged".
                "percentage_change": (
                    str(change.percentage_change)
                    if change.percentage_change is not None
                    else None
                ),
            }
            for change in comparison.changes
        },
        # Null when nothing in scope holds a cash balance. The flows above are still real.
        "cash": (
            {
                "opening": str(balance.opening),
                "inflow": str(balance.inflow),
                "outflow": str(balance.outflow),
                "closing": str(balance.closing),
            }
            if balance is not None
            else None
        ),
        "transaction_count": report.transaction_count,
        # Which uploads this month's figures were built from, so a figure that moved can be
        # traced back to the statement that moved it.
        "import_batch_ids": list(report.import_batch_ids),
    }
