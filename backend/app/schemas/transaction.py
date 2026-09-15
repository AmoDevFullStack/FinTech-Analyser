from app.models.transaction import Transaction


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
    }
