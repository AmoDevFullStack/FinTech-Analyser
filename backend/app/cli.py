"""`python -m app.cli seed --demo`, per README.md's quick start."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import click
from flask import Flask

from app.core.auth import hash_password
from app.core.events import MAX_ATTEMPTS, dispatch_pending
from app.core.extensions import db
from app.models.account import Account, AccountType, BalanceSource
from app.repositories.domain_event import DomainEventRepository
from app.models.transaction import Direction, Transaction
from app.models.user import User
from app.services.category_seed import ensure_system_categories
from app.services.import_service import make_fingerprint, normalise_description
from app.services.spending_insight import SpendingInsightService


def register(app: Flask) -> None:
    app.cli.add_command(seed)
    app.cli.add_command(events)


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

    # The full system chart of accounts, not three hand-made rows: a demo whose categories
    # do not match a real user's produces a dashboard that cannot be compared with one.
    categories = {c.name: c for c in ensure_system_categories(db.session)}
    db.session.flush()

    income = categories["Salary"]
    essential = categories["Groceries"]
    discretionary = categories["Dining out"]
    rent = categories["Rent"]
    insurance = categories["Insurance"]

    transactions = []
    for month_offset in range(18):
        occurred_on = date.today().replace(day=1) - timedelta(days=30 * month_offset)
        for label, category, amount in (
            ("SALARY DEPOSIT ACME PTY LTD", income, Decimal("52000.00")),
            # Rent as a debit order, which is how it appears on a real statement and what
            # the detection engine is built to recognise. Without a rent line the demo
            # understates essential spending by the largest number in most budgets, and
            # the emergency-fund figure derived from it is correspondingly wrong.
            ("DEBIT ORDER RENT PROPERTY GROUP", rent, Decimal("-14500.00")),
            ("DEBIT ORDER OUTSURANCE PREMIUM", insurance, Decimal("-1850.00")),
            ("POS PURCHASE WOOLWORTHS CLAREMONT", essential, Decimal("-16900.00")),
            ("CARD PURCHASE UBER EATS", discretionary, Decimal("-9800.00")),
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
    db.session.flush()

    insight = SpendingInsightService(db.session)
    for transaction in transactions:
        insight.classify_transaction(transaction)
    db.session.commit()

    from app.services.financial_health import FinancialHealthService
    from app.services.position import PositionService

    PositionService(db.session).capture_snapshot(user_id=user.id)
    assessment = FinancialHealthService(db.session).assess(user_id=user.id)

    click.echo(f"Demo user created: {email} / {password}")
    click.echo(f"Financial health score: {assessment.score}/100")


@click.group()
def events() -> None:
    """Domain event commands. See app/core/events.py."""


@events.command("drain")
@click.option("--limit", default=100, show_default=True, help="Most events to process.")
def events_drain(limit: int) -> None:
    """Run the handlers for events still waiting, across every user.

    Dispatch normally happens in the request that recorded the event. This is for the
    cases where that did not finish it: a handler that failed and is being retried after a
    fix, or a backlog left by a process that was restarted mid-pass.
    """
    report = dispatch_pending(db.session, user_id=None, limit=limit)
    click.echo(f"processed {report.processed}, failed {report.failed}")


@events.command("failed")
def events_failed() -> None:
    """List events that gave up after MAX_ATTEMPTS, with the error that stopped them.

    This is the command that makes a failing handler visible: dispatch never fails a user's
    request over a recomputation, so without somewhere to look, a handler that is broken
    for everyone would show up only as figures quietly not updating.
    """
    stuck = DomainEventRepository(db.session).failed(max_attempts=MAX_ATTEMPTS)
    if not stuck:
        click.echo("No events have exhausted their attempts.")
        return

    for event in stuck:
        click.echo(
            f"{event.occurred_at.isoformat()}  {event.name}  user={event.user_id}  "
            f"attempts={event.attempts}  {event.last_error}"
        )
    click.echo(f"{len(stuck)} event(s) stopped after {MAX_ATTEMPTS} attempts.")
