from app.services.account import AccountView


def account_dict(view: AccountView) -> dict:
    account = view.account
    return {
        "id": str(account.id),
        "name": account.name,
        "account_type": account.account_type.value,
        "institution": account.institution,
        "current_balance": str(view.balance),
        "balance_source": account.balance_source.value,
        "is_manual_balance_stale": view.is_manual_balance_stale,
        "credit_limit": str(account.credit_limit) if account.credit_limit is not None else None,
        "utilisation": str(view.utilisation) if view.utilisation is not None else None,
        "interest_rate": str(account.interest_rate) if account.interest_rate is not None else None,
        "opened_on": account.opened_on.isoformat() if account.opened_on else None,
        "archived_at": account.archived_at.isoformat() if account.archived_at else None,
    }
