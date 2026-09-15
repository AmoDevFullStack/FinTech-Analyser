"""AccountService.update — see specs/accounts.md's constraint that a derived balance is
never overwritten by a manual entry.
"""

from decimal import Decimal

from app.core.auth import hash_password
from app.core.errors import ValidationError
from app.models.account import Account, AccountType, BalanceSource
from app.models.user import User
from app.repositories.health_assessment import HealthAssessmentRepository
from app.repositories.position_snapshot import PositionSnapshotRepository
from app.services.account import AccountService, CreateAccountInput, UpdateAccountInput

import pytest


def _make_user(session, email: str = "update-test@example.com") -> User:
    user = User(email=email, password_hash=hash_password("x"), full_name="Test User")
    session.add(user)
    session.flush()
    return user


def _make_account(session, user, *, balance_source: BalanceSource) -> Account:
    account = Account(
        user_id=user.id,
        name="Original name",
        account_type=AccountType.SAVINGS,
        current_balance=Decimal("100.00"),
        balance_source=balance_source,
    )
    session.add(account)
    session.commit()
    return account


def test_update_changes_editable_fields(session):
    user = _make_user(session)
    account = _make_account(session, user, balance_source=BalanceSource.MANUAL)
    service = AccountService(session)

    updated = service.update(
        account.id,
        user_id=user.id,
        data=UpdateAccountInput(name="Renamed", institution="New Bank", interest_rate=Decimal("0.05")),
    )

    assert updated.name == "Renamed"
    assert updated.institution == "New Bank"
    assert updated.interest_rate == Decimal("0.05")


def test_update_manual_balance_sets_balance_and_timestamp(session):
    user = _make_user(session)
    account = _make_account(session, user, balance_source=BalanceSource.MANUAL)
    service = AccountService(session)

    updated = service.update(
        account.id, user_id=user.id, data=UpdateAccountInput(manual_balance=Decimal("250.00"))
    )

    assert updated.current_balance == Decimal("250.00")
    assert updated.manual_balance_set_at is not None


def test_update_balance_on_derived_account_is_rejected(session):
    user = _make_user(session)
    account = _make_account(session, user, balance_source=BalanceSource.DERIVED)
    service = AccountService(session)

    with pytest.raises(ValidationError):
        service.update(account.id, user_id=user.id, data=UpdateAccountInput(manual_balance=Decimal("250.00")))


def test_create_account_captures_a_fresh_position_snapshot(session):
    """The dashboard reads a stored snapshot only (ADR-003) — an account mutation is one
    of the few places that snapshot is refreshed, so the dashboard reflects it without the
    user having to separately hit "Refresh".
    """
    user = _make_user(session, "create-snapshot@example.com")
    service = AccountService(session)

    service.create(
        user_id=user.id,
        data=CreateAccountInput(
            name="New savings",
            account_type=AccountType.SAVINGS,
            institution=None,
            opening_balance=Decimal("500.00"),
            opened_on=None,
        ),
    )

    snapshot = PositionSnapshotRepository(session).latest_for_user(user_id=user.id)
    assert snapshot is not None
    assert snapshot.liquid_savings == Decimal("500.00")


def test_renaming_an_account_does_not_recapture_the_snapshot(session):
    user = _make_user(session, "rename-snapshot@example.com")
    account = _make_account(session, user, balance_source=BalanceSource.MANUAL)
    service = AccountService(session)
    service.create(
        user_id=user.id,
        data=CreateAccountInput(
            name="Anchor",
            account_type=AccountType.SAVINGS,
            institution=None,
            opening_balance=Decimal("0.00"),
            opened_on=None,
        ),
    )
    first_snapshot = PositionSnapshotRepository(session).latest_for_user(user_id=user.id)

    service.update(account.id, user_id=user.id, data=UpdateAccountInput(name="Renamed"))

    second_snapshot = PositionSnapshotRepository(session).latest_for_user(user_id=user.id)
    assert second_snapshot.id == first_snapshot.id


def test_archiving_an_account_recaptures_the_snapshot(session):
    user = _make_user(session, "archive-snapshot@example.com")
    account = _make_account(session, user, balance_source=BalanceSource.MANUAL)
    service = AccountService(session)

    service.archive(account.id, user_id=user.id)

    snapshot = PositionSnapshotRepository(session).latest_for_user(user_id=user.id)
    assert snapshot is not None
    assert snapshot.liquid_savings == Decimal("0.00")


def test_create_account_also_recomputes_the_health_assessment(session):
    """specs/financial-health.md: health is computed "on material change", not only on a
    schedule — an account mutation is that change, so the dashboard's health section
    doesn't stay frozen at whatever it last showed while net worth moves.
    """
    user = _make_user(session, "health-sync@example.com")
    service = AccountService(session)

    service.create(
        user_id=user.id,
        data=CreateAccountInput(
            name="New savings",
            account_type=AccountType.SAVINGS,
            institution=None,
            opening_balance=Decimal("500.00"),
            opened_on=None,
        ),
    )

    assessment = HealthAssessmentRepository(session).latest_for_user(user_id=user.id)
    assert assessment is not None


def test_editing_credit_limit_recomputes_the_health_assessment(session):
    """Credit utilisation (10% of the score) is balance ÷ limit — a limit-only edit moves
    that ratio even though it isn't a `manual_balance` change.
    """
    user = _make_user(session, "credit-limit-sync@example.com")
    account = Account(
        user_id=user.id,
        name="Card",
        account_type=AccountType.CREDIT_CARD,
        current_balance=Decimal("-1000.00"),
        balance_source=BalanceSource.MANUAL,
        credit_limit=Decimal("5000.00"),
    )
    session.add(account)
    session.commit()
    service = AccountService(session)
    before = HealthAssessmentRepository(session).latest_for_user(user_id=user.id)

    service.update(account.id, user_id=user.id, data=UpdateAccountInput(credit_limit=Decimal("10000.00")))

    after = HealthAssessmentRepository(session).latest_for_user(user_id=user.id)
    assert after is not None
    assert before is None or after.id != before.id
