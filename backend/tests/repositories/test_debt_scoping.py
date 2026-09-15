"""Proves no repository query returns another user's rows. See docs/architecture.md §3.4
and specs/debts.md.
"""

from datetime import date
from decimal import Decimal

from app.core.auth import hash_password
from app.models.debt import Debt, DebtType
from app.models.user import User
from app.repositories.debt import DebtRepository


def _make_user(session, email: str) -> User:
    user = User(email=email, password_hash=hash_password("x"), full_name="Test User")
    session.add(user)
    session.flush()
    return user


def _debt(user_id, **overrides) -> Debt:
    defaults = dict(
        user_id=user_id,
        debt_type=DebtType.CREDIT_CARD,
        original_principal=Decimal("20000.00"),
        current_balance=Decimal("15000.00"),
        annual_rate=Decimal("0.240000"),
        minimum_payment=Decimal("600.00"),
        started_on=date(2024, 1, 1),
    )
    defaults.update(overrides)
    return Debt(**defaults)


def test_list_for_user_excludes_other_users_debts(session):
    repo = DebtRepository(session)
    alice = _make_user(session, "alice-debt@example.com")
    bob = _make_user(session, "bob-debt@example.com")

    repo.add(_debt(alice.id))
    repo.add(_debt(bob.id))
    session.commit()

    alice_debts = repo.list_for_user(user_id=alice.id)
    assert len(alice_debts) == 1
    assert alice_debts[0].user_id == alice.id


def test_get_for_user_returns_none_for_other_users_debt(session):
    repo = DebtRepository(session)
    alice = _make_user(session, "alice-debt2@example.com")
    bob = _make_user(session, "bob-debt2@example.com")

    bob_debt = repo.add(_debt(bob.id))
    session.commit()

    assert repo.get_for_user(bob_debt.id, user_id=alice.id) is None
    assert repo.get_for_user(bob_debt.id, user_id=bob.id) is not None


def test_list_for_user_excludes_soft_deleted_debts(session):
    from datetime import UTC, datetime

    repo = DebtRepository(session)
    user = _make_user(session, "carol-debt@example.com")

    debt = repo.add(_debt(user.id))
    session.commit()
    debt.deleted_at = datetime.now(UTC)
    session.commit()

    assert repo.list_for_user(user_id=user.id) == []
    assert repo.get_for_user(debt.id, user_id=user.id) is None
