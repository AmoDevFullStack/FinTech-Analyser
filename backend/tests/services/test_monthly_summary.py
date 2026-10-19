"""MonthlySummaryService — the month-to-month view. See app/services/monthly_summary.py.

The fixture below is three months of one household on one cheque account: R52,000 salary
every month, R16,900 of essentials, R9,800 of discretionary, and R14,500 of rent starting
in July. Every expected figure is that arithmetic written out.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.core.auth import hash_password
from app.models.account import Account, AccountType, BalanceSource
from app.models.category import Category, CategoryKind
from app.models.transaction import Direction, Transaction
from app.models.user import User
from app.services.monthly_summary import MAX_MONTHS, MonthlySummaryService

AS_OF = date(2026, 7, 31)


@pytest.fixture()
def household(session):
    """One user, one cheque account, three months of history."""
    user = User(
        email="months@example.com", password_hash=hash_password("x"), full_name="Test User"
    )
    session.add(user)
    session.flush()

    account = Account(
        user_id=user.id,
        name="Cheque",
        account_type=AccountType.TRANSACTIONAL,
        current_balance=Decimal("48200.00"),
        balance_source=BalanceSource.DERIVED,
    )
    session.add(account)

    kinds = {}
    for kind in CategoryKind:
        category = Category(user_id=user.id, name=kind.value.title(), kind=kind)
        session.add(category)
        kinds[kind] = category
    session.flush()

    def add(occurred_on, amount, description, kind, **extra):
        transaction = Transaction(
            user_id=user.id,
            account_id=account.id,
            category_id=kinds[kind].id if kind is not None else None,
            occurred_on=occurred_on,
            amount=Decimal(amount),
            description=description,
            normalised_description=description.lower(),
            direction=Direction.CREDIT if Decimal(amount) >= 0 else Direction.DEBIT,
            fingerprint=f"{occurred_on}-{amount}-{description}",
            **extra,
        )
        session.add(transaction)
        return transaction

    for month in (5, 6, 7):
        add(date(2026, month, 25), "52000", "SALARY", CategoryKind.INCOME)
        add(date(2026, month, 3), "-16900", "GROCERIES AND UTILITIES", CategoryKind.ESSENTIAL)
        add(date(2026, month, 12), "-9800", "DINING AND ENTERTAINMENT", CategoryKind.DISCRETIONARY)
    add(date(2026, 7, 1), "-14500", "RENT", CategoryKind.ESSENTIAL)

    session.commit()
    return {"user": user, "account": account, "categories": kinds, "add": add, "session": session}


def _summary(household, **kwargs):
    return MonthlySummaryService(household["session"]).summary(
        user_id=household["user"].id, as_of=AS_OF, **kwargs
    )


def _by_month(reports):
    return {report.comparison.month: report for report in reports}


# ---------------------------------------------------------------------------------------
# Flows
# ---------------------------------------------------------------------------------------
def test_each_month_reports_its_own_totals(household):
    months = _by_month(_summary(household, since=date(2026, 5, 1), until=date(2026, 7, 31)))

    assert sorted(months) == ["2026-05", "2026-06", "2026-07"]
    june = months["2026-06"].comparison.totals
    assert june.income == Decimal("52000.00")
    assert june.essential == Decimal("16900.00")
    assert june.spending == Decimal("26700.00")
    assert june.net == Decimal("25300.00")

    july = months["2026-07"].comparison.totals
    assert july.essential == Decimal("31400.00")  # 16,900 + 14,500 rent
    assert july.net == Decimal("10800.00")


def test_a_month_is_compared_against_the_one_before_it(household):
    months = _by_month(_summary(household, since=date(2026, 5, 1), until=date(2026, 7, 31)))
    changes = {c.metric: c for c in months["2026-07"].comparison.changes}

    assert months["2026-07"].comparison.previous_month == "2026-06"
    assert changes["essential"].change == Decimal("14500.00")
    assert changes["net"].change == Decimal("-14500.00")


def test_the_first_month_asked_for_is_compared_against_the_month_before_the_window(household):
    """June is the first month requested, so June's own comparison is against May —
    which is in the table, and leaving it out would report June as having no predecessor.
    """
    months = _by_month(_summary(household, since=date(2026, 6, 1), until=date(2026, 7, 31)))

    assert sorted(months) == ["2026-06", "2026-07"]
    assert months["2026-06"].comparison.previous_month == "2026-05"
    assert months["2026-06"].comparison.changes != ()


def test_a_month_with_no_transactions_is_still_a_month(household):
    months = _by_month(_summary(household, since=date(2026, 3, 1), until=date(2026, 7, 31)))

    assert "2026-04" in months
    assert months["2026-04"].comparison.totals.income == Decimal("0.00")
    assert months["2026-04"].transaction_count == 0


def test_internal_transfers_are_not_income_and_not_spending(household):
    """Both legs of a transfer are real rows. Counting them would inflate income and
    spending at once — specs/transactions.md step 4."""
    before = _by_month(_summary(household, since=date(2026, 6, 1), until=date(2026, 6, 30)))
    baseline = before["2026-06"].comparison.totals

    household["add"](
        date(2026, 6, 15), "-5000", "TRANSFER TO SAVINGS", CategoryKind.TRANSFER
    )
    household["session"].commit()

    after = _by_month(_summary(household, since=date(2026, 6, 1), until=date(2026, 6, 30)))
    assert after["2026-06"].comparison.totals == baseline


def test_an_uncategorised_transaction_is_not_put_in_a_bucket(household):
    """A row with no category has no kind, and guessing one would be presented as a
    figure. It still counts as cash that moved."""
    before = _by_month(_summary(household, since=date(2026, 6, 1), until=date(2026, 6, 30)))
    baseline = before["2026-06"]

    household["add"](date(2026, 6, 18), "-750", "UNKNOWN DEBIT", None)
    household["session"].commit()

    after = _by_month(_summary(household, since=date(2026, 6, 1), until=date(2026, 6, 30)))
    assert after["2026-06"].comparison.totals == baseline.comparison.totals
    assert after["2026-06"].transaction_count == baseline.transaction_count + 1


def test_a_soft_deleted_transaction_is_not_counted(household):
    from datetime import datetime, timezone

    months = _by_month(_summary(household, since=date(2026, 6, 1), until=date(2026, 6, 30)))
    removed = household["add"](date(2026, 6, 20), "-1000", "TO BE DELETED", CategoryKind.DISCRETIONARY)
    removed.deleted_at = datetime.now(timezone.utc)
    household["session"].commit()

    after = _by_month(_summary(household, since=date(2026, 6, 1), until=date(2026, 6, 30)))
    assert after["2026-06"].comparison.totals == months["2026-06"].comparison.totals


# ---------------------------------------------------------------------------------------
# Cash
# ---------------------------------------------------------------------------------------
def test_the_cash_line_walks_back_from_the_account_balance(household):
    """Closing R48,200 at the end of July.

    July:  opening = 48,200 - (52,000 - 41,200) = 37,400
    June:  opening = 37,400 - (52,000 - 26,700) = 12,100
    """
    months = _by_month(_summary(household, since=date(2026, 5, 1), until=date(2026, 7, 31)))

    assert months["2026-07"].balance.closing == Decimal("48200.00")
    assert months["2026-07"].balance.opening == Decimal("37400.00")
    assert months["2026-06"].balance.opening == Decimal("12100.00")


def test_each_month_opens_where_the_previous_one_closed(household):
    reports = _summary(household, since=date(2026, 5, 1), until=date(2026, 7, 31))
    balances = [report.balance for report in reports]
    for earlier, later in zip(balances, balances[1:]):
        assert later.opening == earlier.closing


def test_a_window_that_ends_early_is_not_dated_by_what_came_after(household):
    """Asking for May and June must give the same figures whether or not July exists,
    because the walk accounts for everything between the window and today."""
    with_july = _by_month(_summary(household, since=date(2026, 5, 1), until=date(2026, 7, 31)))
    without_july = _by_month(_summary(household, since=date(2026, 5, 1), until=date(2026, 6, 30)))

    assert without_july["2026-06"].balance.closing == with_july["2026-06"].balance.closing


def test_a_credit_card_alone_has_no_cash_line(household, session):
    """A card balance is money owed, not money available."""
    card = Account(
        user_id=household["user"].id,
        name="Credit card",
        account_type=AccountType.CREDIT_CARD,
        current_balance=Decimal("-4200.00"),
        balance_source=BalanceSource.DERIVED,
    )
    session.add(card)
    session.commit()

    reports = _summary(household, since=date(2026, 6, 1), until=date(2026, 6, 30), account_id=card.id)
    assert reports[0].balance is None


# ---------------------------------------------------------------------------------------
# Scope and window
# ---------------------------------------------------------------------------------------
def test_one_users_months_never_include_another_users_transactions(session, household):
    other = User(email="other@example.com", password_hash=hash_password("x"), full_name="Other")
    session.add(other)
    session.flush()
    other_account = Account(
        user_id=other.id,
        name="Theirs",
        account_type=AccountType.TRANSACTIONAL,
        current_balance=Decimal("999999.00"),
        balance_source=BalanceSource.DERIVED,
    )
    session.add(other_account)
    category = Category(user_id=other.id, name="Income", kind=CategoryKind.INCOME)
    session.add(category)
    session.flush()
    session.add(
        Transaction(
            user_id=other.id,
            account_id=other_account.id,
            category_id=category.id,
            occurred_on=date(2026, 6, 10),
            amount=Decimal("999999.00"),
            description="THEIR SALARY",
            normalised_description="their salary",
            direction=Direction.CREDIT,
            fingerprint="theirs",
        )
    )
    session.commit()

    months = _by_month(_summary(household, since=date(2026, 6, 1), until=date(2026, 6, 30)))
    assert months["2026-06"].comparison.totals.income == Decimal("52000.00")


def test_an_unknown_account_is_rejected(household):
    from uuid import uuid4

    from app.core.errors import ValidationError

    with pytest.raises(ValidationError):
        _summary(household, account_id=uuid4())


def test_a_window_longer_than_the_maximum_is_rejected(household):
    from app.core.errors import ValidationError

    with pytest.raises(ValidationError, match=str(MAX_MONTHS)):
        _summary(household, since=date(2015, 1, 1), until=date(2026, 7, 31))


def test_the_default_window_is_the_last_twelve_months(household):
    reports = _summary(household)
    months = [report.comparison.month for report in reports]

    assert len(months) == 12
    assert months[-1] == "2026-07"
    assert months[0] == "2025-08"


# ---------------------------------------------------------------------------------------
# Traceability
# ---------------------------------------------------------------------------------------
def test_a_month_names_the_uploads_its_figures_came_from(household, session):
    from app.models.import_batch import ImportBatch, ImportStatus

    batch = ImportBatch(
        user_id=household["user"].id,
        account_id=household["account"].id,
        status=ImportStatus.COMMITTED,
        rows_parsed=1,
        rows_imported=1,
    )
    session.add(batch)
    session.flush()

    imported = household["add"](
        date(2026, 6, 14), "-320", "IMPORTED ROW", CategoryKind.DISCRETIONARY
    )
    imported.import_batch_id = batch.id
    session.commit()

    months = _by_month(_summary(household, since=date(2026, 6, 1), until=date(2026, 6, 30)))
    assert months["2026-06"].import_batch_ids == (str(batch.id),)


def test_a_month_typed_in_by_hand_names_no_upload(household):
    months = _by_month(_summary(household, since=date(2026, 6, 1), until=date(2026, 6, 30)))
    assert months["2026-06"].import_batch_ids == ()


# ---------------------------------------------------------------------------------------
# The baseline month every other figure is measured over
# ---------------------------------------------------------------------------------------
#: Two months after this household's last transaction — the situation that produced a
#: position of all zeros, and with it a health score nothing could move.
LATER = date(2026, 9, 18)


def test_the_position_measures_the_last_month_with_transactions(household):
    """Not the current calendar month. September holds nothing for this household, and a
    position built from it reported zero income against real savings."""
    from app.services.position import PositionService

    service = PositionService(household["session"])
    start, end = service.baseline_month(user_id=household["user"].id, as_of=LATER)

    assert (start.year, start.month) == (2026, 7)
    assert end == date(2026, 7, 31)

    position = service.compute_current(user_id=household["user"].id, as_of=LATER)
    assert position.monthly_income == Decimal("52000.00")
    assert position.monthly_essential == Decimal("31400.00")


def test_a_user_with_no_transactions_falls_back_to_the_current_month(session):
    """Zero is then the honest answer: there is nothing to measure, and the dashboard says
    so rather than quietly borrowing a month that does not exist."""
    from app.core.auth import hash_password
    from app.services.position import PositionService

    user = User(email="empty@example.com", password_hash=hash_password("x"), full_name="Empty")
    session.add(user)
    session.commit()

    start, end = PositionService(session).baseline_month(user_id=user.id, as_of=LATER)
    assert (start.year, start.month) == (LATER.year, LATER.month)
    assert end == LATER


def test_the_current_month_is_measured_only_as_far_as_it_has_run(household):
    """A month in progress is reported to today, never projected to its end."""
    from app.services.position import PositionService

    mid_july = date(2026, 7, 15)
    _, end = PositionService(household["session"]).baseline_month(
        user_id=household["user"].id, as_of=mid_july
    )
    assert end == mid_july


def test_activity_span_reports_what_history_exists(household):
    from app.repositories.transaction import TransactionRepository

    span = TransactionRepository(household["session"]).activity_span(
        user_id=household["user"].id
    )

    # Three months of salary, essentials and discretionary, plus July's rent.
    assert span.first_on == date(2026, 5, 3)
    assert span.last_on == date(2026, 7, 25)
    assert span.months_with_activity == 3
    assert span.transaction_count == 10
    assert span.has_history is True
