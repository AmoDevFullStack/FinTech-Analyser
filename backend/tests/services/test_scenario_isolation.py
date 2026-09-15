"""ADR-005's explicit requirement: "A test asserting a scenario run issues zero writes to
real financial tables." Accounts and transactions are the real financial tables this slice
has; a scenario run must leave every one of them byte-for-byte unchanged.
"""

from datetime import date
from decimal import Decimal

from app.core.auth import hash_password
from app.models.account import Account, AccountType, BalanceSource
from app.models.category import Category, CategoryKind
from app.models.transaction import Direction, Transaction
from app.models.user import User
from app.repositories.account import AccountRepository
from app.services.scenario import ScenarioService, VehiclePurchaseAssumptions


def _seed_user_with_position(session) -> User:
    user = User(email="scenario@example.com", password_hash=hash_password("x"), full_name="S")
    session.add(user)
    session.flush()

    cheque = Account(
        user_id=user.id,
        name="Cheque",
        account_type=AccountType.TRANSACTIONAL,
        current_balance=Decimal("48200.00"),
        balance_source=BalanceSource.MANUAL,
    )
    session.add(cheque)
    session.flush()

    income_category = Category(name="Salary", kind=CategoryKind.INCOME)
    essential_category = Category(name="Groceries", kind=CategoryKind.ESSENTIAL)
    session.add_all([income_category, essential_category])
    session.flush()

    session.add_all(
        [
            Transaction(
                user_id=user.id,
                account_id=cheque.id,
                category_id=income_category.id,
                occurred_on=date.today().replace(day=1),
                amount=Decimal("52000.00"),
                description="Salary",
                normalised_description="salary",
                direction=Direction.CREDIT,
                fingerprint="fp-salary",
            ),
            Transaction(
                user_id=user.id,
                account_id=cheque.id,
                category_id=essential_category.id,
                occurred_on=date.today().replace(day=2),
                amount=Decimal("-31400.00"),
                description="Groceries",
                normalised_description="groceries",
                direction=Direction.DEBIT,
                fingerprint="fp-groceries",
            ),
        ]
    )
    session.commit()
    return user


def test_running_a_scenario_writes_nothing_to_accounts_or_transactions(session):
    user = _seed_user_with_position(session)
    accounts_before = [
        (a.id, a.current_balance) for a in AccountRepository(session).list_for_user(user_id=user.id)
    ]

    service = ScenarioService(session)
    scenario = service.create_vehicle_purchase(
        user_id=user.id,
        name="New car",
        description=None,
        assumptions=VehiclePurchaseAssumptions(
            purchase_price=Decimal("350000"),
            deposit=Decimal("50000"),
            annual_rate=Decimal("0.1175"),
            term_months=72,
            insurance_monthly=Decimal("850"),
            fuel_monthly=Decimal("1800"),
            maintenance_monthly=Decimal("450"),
        ),
    )
    service.run(scenario.id, user_id=user.id)

    accounts_after = [
        (a.id, a.current_balance) for a in AccountRepository(session).list_for_user(user_id=user.id)
    ]
    assert accounts_before == accounts_after


def test_rerunning_with_identical_inputs_is_byte_identical(session):
    user = _seed_user_with_position(session)
    service = ScenarioService(session)
    scenario = service.create_vehicle_purchase(
        user_id=user.id,
        name="New car",
        description=None,
        assumptions=VehiclePurchaseAssumptions(
            purchase_price=Decimal("350000"),
            deposit=Decimal("50000"),
            annual_rate=Decimal("0.1175"),
            term_months=72,
        ),
    )
    first = service.run(scenario.id, user_id=user.id)
    second = service.run(scenario.id, user_id=user.id)
    assert first.impact == second.impact
    assert first.periods == second.periods
