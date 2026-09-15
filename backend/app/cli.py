"""`python -m app.cli seed --demo`, per README.md's quick start."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import click
from flask import Flask

from app.core.auth import hash_password
from app.core.extensions import db
from app.models.account import Account, AccountType, BalanceSource
from app.models.category import Category, CategoryKind
from app.models.transaction import Direction, Transaction
from app.models.user import User
from app.services.import_service import make_fingerprint, normalise_description


def register(app: Flask) -> None:
    app.cli.add_command(seed)


@click.group()
def seed() -> None:
    """Seed commands."""


@seed.command("demo")
def seed_demo() -> None:
    """Create a demo user with 18 months of plausible transaction history, matching the
    README's quick-start promise and the published dashboard mock's figures.
    """
    email = "demo@financialdigitaltwin.local"
    password = "demo-password-change-me"

    existing = db.session.query(User).filter_by(email=email).first()
    if existing is not None:
        click.echo(f"Demo user already exists: {email}")
        return

    user = User(email=email, password_hash=hash_password(password), full_name="Demo User")
    db.session.add(user)
    db.session.flush()

    cheque = Account(
        user_id=user.id,
        name="Everyday account",
        account_type=AccountType.TRANSACTIONAL,
        institution="Demo Bank",
        current_balance=Decimal("48200.00"),
        balance_source=BalanceSource.MANUAL,
        opened_on=date.today() - timedelta(days=900),
    )
    vehicle_finance = Account(
        user_id=user.id,
        name="Vehicle finance",
        account_type=AccountType.VEHICLE_FINANCE,
        institution="Demo Bank",
        current_balance=Decimal("287300.00"),
        balance_source=BalanceSource.MANUAL,
        interest_rate=Decimal("0.117500"),
        opened_on=date.today() - timedelta(days=400),
    )
    db.session.add_all([cheque, vehicle_finance])
    db.session.flush()

    income = Category(name="Salary", kind=CategoryKind.INCOME)
    essential = Category(name="Groceries", kind=CategoryKind.ESSENTIAL)
    discretionary = Category(name="Dining out", kind=CategoryKind.DISCRETIONARY)
    db.session.add_all([income, essential, discretionary])
    db.session.flush()

    transactions = []
    for month_offset in range(18):
        occurred_on = date.today().replace(day=1) - timedelta(days=30 * month_offset)
        for label, category, amount in (
            ("Salary", income, Decimal("52000.00")),
            ("Groceries", essential, Decimal("-31400.00")),
            ("Dining out", discretionary, Decimal("-9800.00")),
        ):
            normalised = normalise_description(label)
            transactions.append(
                Transaction(
                    user_id=user.id,
                    account_id=cheque.id,
                    category_id=category.id,
                    occurred_on=occurred_on,
                    amount=amount,
                    description=label,
                    normalised_description=normalised,
                    direction=Direction.CREDIT if amount >= 0 else Direction.DEBIT,
                    category_confidence=Decimal("1.000000"),
                    category_set_by_user=True,
                    fingerprint=make_fingerprint(
                        user_id=user.id,
                        account_id=cheque.id,
                        occurred_on=occurred_on,
                        amount=amount,
                        normalised=normalised,
                    ),
                )
            )
    db.session.add_all(transactions)
    db.session.commit()

    from app.services.financial_health import FinancialHealthService
    from app.services.position import PositionService

    PositionService(db.session).capture_snapshot(user_id=user.id)
    assessment = FinancialHealthService(db.session).assess(user_id=user.id)

    click.echo(f"Demo user created: {email} / {password}")
    click.echo(f"Financial health score: {assessment.score}/100")
