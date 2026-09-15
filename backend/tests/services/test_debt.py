"""DebtService — schedule/what-if delegation, strategy comparison, and the health engine's
debt-burden component switching to real minimum payments once a Debt exists.
See specs/debts.md and specs/financial-health.md.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.core.auth import hash_password
from app.core.errors import ValidationError
from app.domain.cash_flow import debt_to_income
from app.models.account import Account, AccountType, BalanceSource
from app.models.category import Category, CategoryKind
from app.models.transaction import Direction, Transaction
from app.models.user import User
from app.models.debt import DebtType
from app.repositories.health_assessment import HealthAssessmentRepository
from app.services.debt import CreateDebtInput, DebtService


def _make_user(session, email: str) -> User:
    user = User(email=email, password_hash=hash_password("x"), full_name="Test User")
    session.add(user)
    session.flush()
    return user


def _give_monthly_income(session, user, amount: Decimal) -> None:
    account = Account(
        user_id=user.id,
        name="Cheque",
        account_type=AccountType.TRANSACTIONAL,
        current_balance=amount,
        balance_source=BalanceSource.MANUAL,
    )
    session.add(account)
    income_category = Category(name="Salary", kind=CategoryKind.INCOME)
    session.add(income_category)
    session.flush()
    session.add(
        Transaction(
            user_id=user.id,
            account_id=account.id,
            category_id=income_category.id,
            occurred_on=date.today().replace(day=1),
            amount=amount,
            description="Salary",
            normalised_description="salary",
            direction=Direction.CREDIT,
            fingerprint=f"fp-salary-{user.id}",
        )
    )
    session.commit()


def test_create_persists_a_debt(session):
    user = _make_user(session, "debt-create@example.com")
    service = DebtService(session)

    debt = service.create(
        user_id=user.id,
        data=CreateDebtInput(
            debt_type=DebtType.VEHICLE,
            original_principal=Decimal("350000.00"),
            current_balance=Decimal("350000.00"),
            annual_rate=Decimal("0.1175"),
            minimum_payment=Decimal("6797.15"),
            started_on=date(2026, 1, 1),
            term_months=72,
        ),
    )

    fetched = service.get(debt.id, user_id=user.id)
    assert fetched.current_balance == Decimal("350000.00")
    assert fetched.term_months == 72


def test_schedule_uses_fixed_term_engine_when_term_months_is_set(session):
    user = _make_user(session, "debt-schedule-term@example.com")
    service = DebtService(session)
    debt = service.create(
        user_id=user.id,
        data=CreateDebtInput(
            debt_type=DebtType.VEHICLE,
            original_principal=Decimal("350000.00"),
            current_balance=Decimal("350000.00"),
            annual_rate=Decimal("0.1175"),
            minimum_payment=Decimal("6797.15"),
            started_on=date(2026, 1, 1),
            term_months=72,
        ),
    )

    periods = service.schedule(debt.id, user_id=user.id)
    assert len(periods) == 72
    assert periods[-1].closing_balance == Decimal("0.00")


def test_schedule_uses_fixed_payment_engine_when_no_term_months(session):
    user = _make_user(session, "debt-schedule-open@example.com")
    service = DebtService(session)
    debt = service.create(
        user_id=user.id,
        data=CreateDebtInput(
            debt_type=DebtType.CREDIT_CARD,
            original_principal=Decimal("20000.00"),
            current_balance=Decimal("15000.00"),
            annual_rate=Decimal("0.24"),
            minimum_payment=Decimal("900.00"),
            started_on=date(2024, 1, 1),
        ),
    )

    periods = service.schedule(debt.id, user_id=user.id)
    assert periods[-1].closing_balance == Decimal("0.00")
    assert all(p.instalment <= Decimal("900.00") for p in periods)


def test_what_if_reports_savings_for_each_increment(session):
    user = _make_user(session, "debt-what-if@example.com")
    service = DebtService(session)
    debt = service.create(
        user_id=user.id,
        data=CreateDebtInput(
            debt_type=DebtType.CREDIT_CARD,
            original_principal=Decimal("20000.00"),
            current_balance=Decimal("15000.00"),
            annual_rate=Decimal("0.24"),
            minimum_payment=Decimal("900.00"),
            started_on=date(2024, 1, 1),
        ),
    )

    results = service.what_if(debt.id, user_id=user.id)
    assert len(results) == 3
    assert all(r.months_saved > 0 for r in results)


def test_compare_strategies_defaults_total_monthly_to_sum_of_minimums(session):
    user = _make_user(session, "debt-strategies@example.com")
    service = DebtService(session)
    service.create(
        user_id=user.id,
        data=CreateDebtInput(
            debt_type=DebtType.CREDIT_CARD,
            original_principal=Decimal("20000.00"),
            current_balance=Decimal("20000.00"),
            annual_rate=Decimal("0.24"),
            minimum_payment=Decimal("600.00"),
            started_on=date(2024, 1, 1),
        ),
    )
    service.create(
        user_id=user.id,
        data=CreateDebtInput(
            debt_type=DebtType.PERSONAL_LOAN,
            original_principal=Decimal("60000.00"),
            current_balance=Decimal("60000.00"),
            annual_rate=Decimal("0.18"),
            minimum_payment=Decimal("1800.00"),
            started_on=date(2024, 1, 1),
        ),
    )

    comparison = service.compare_strategies(user_id=user.id)
    assert comparison.avalanche.months_to_free > 0
    assert comparison.snowball.months_to_free > 0
    assert comparison.consolidation is None


def test_compare_strategies_rejects_a_user_with_no_debts(session):
    user = _make_user(session, "debt-strategies-empty@example.com")
    service = DebtService(session)

    with pytest.raises(ValidationError):
        service.compare_strategies(user_id=user.id)


def test_compare_strategies_rejects_total_monthly_below_minimums(session):
    user = _make_user(session, "debt-strategies-low@example.com")
    service = DebtService(session)
    service.create(
        user_id=user.id,
        data=CreateDebtInput(
            debt_type=DebtType.CREDIT_CARD,
            original_principal=Decimal("20000.00"),
            current_balance=Decimal("20000.00"),
            annual_rate=Decimal("0.24"),
            minimum_payment=Decimal("600.00"),
            started_on=date(2024, 1, 1),
        ),
    )

    with pytest.raises(ValidationError):
        service.compare_strategies(user_id=user.id, total_monthly=Decimal("100.00"))


def test_creating_a_debt_switches_the_health_score_to_real_minimum_payments(session):
    """Before any Debt exists, debt-to-income falls back to transaction-derived spend in
    the DEBT category (here, zero — no such transactions were recorded). Creating a Debt
    must make the score reflect its actual minimum payment instead.
    """
    user = _make_user(session, "debt-health-sync@example.com")
    _give_monthly_income(session, user, Decimal("20000.00"))

    DebtService(session).create(
        user_id=user.id,
        data=CreateDebtInput(
            debt_type=DebtType.CREDIT_CARD,
            original_principal=Decimal("20000.00"),
            current_balance=Decimal("15000.00"),
            annual_rate=Decimal("0.24"),
            minimum_payment=Decimal("2000.00"),
            started_on=date(2024, 1, 1),
        ),
    )

    assessment = HealthAssessmentRepository(session).latest_for_user(user_id=user.id)
    assert assessment is not None
    debt_component = next(c for c in assessment.breakdown["components"] if c["name"] == "debt_burden")
    expected_ratio = debt_to_income(
        monthly_debt_service=Decimal("2000.00"), monthly_income=Decimal("20000.00")
    )
    assert Decimal(debt_component["ratio"]) == expected_ratio
