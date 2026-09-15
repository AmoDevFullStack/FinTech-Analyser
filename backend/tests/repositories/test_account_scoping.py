"""Proves no repository query returns another user's rows. See docs/architecture.md §3.4
and specs/accounts.md's acceptance criteria.
"""

from decimal import Decimal

from app.core.auth import hash_password
from app.models.account import Account, AccountType, BalanceSource
from app.models.user import User
from app.repositories.account import AccountRepository


def _make_user(session, email: str) -> User:
    user = User(email=email, password_hash=hash_password("x"), full_name="Test User")
    session.add(user)
    session.flush()
    return user


def test_list_for_user_excludes_other_users_accounts(session):
    repo = AccountRepository(session)
    alice = _make_user(session, "alice@example.com")
    bob = _make_user(session, "bob@example.com")

    repo.add(
        Account(
            user_id=alice.id,
            name="Alice cheque",
            account_type=AccountType.TRANSACTIONAL,
            current_balance=Decimal("100.00"),
            balance_source=BalanceSource.MANUAL,
        )
    )
    repo.add(
        Account(
            user_id=bob.id,
            name="Bob cheque",
            account_type=AccountType.TRANSACTIONAL,
            current_balance=Decimal("200.00"),
            balance_source=BalanceSource.MANUAL,
        )
    )
    session.commit()

    alice_accounts = repo.list_for_user(user_id=alice.id)
    assert len(alice_accounts) == 1
    assert alice_accounts[0].name == "Alice cheque"


def test_get_for_user_returns_none_for_other_users_account(session):
    repo = AccountRepository(session)
    alice = _make_user(session, "alice2@example.com")
    bob = _make_user(session, "bob2@example.com")

    bob_account = repo.add(
        Account(
            user_id=bob.id,
            name="Bob savings",
            account_type=AccountType.SAVINGS,
            current_balance=Decimal("500.00"),
            balance_source=BalanceSource.MANUAL,
        )
    )
    session.commit()

    assert repo.get_for_user(bob_account.id, user_id=alice.id) is None
    assert repo.get_for_user(bob_account.id, user_id=bob.id) is not None
