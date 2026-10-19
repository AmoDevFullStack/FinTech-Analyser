"""Financial health, month by month. See app/services/financial_health.py.

The fixture is one household on one cheque account: R52,000 salary every month, R16,900 of
essentials, and R14,500 of rent added from July. The account holds R48,200 today.

What these tests hold to is the thing that was broken: a month is scored on its own
transactions and its own closing balance, so a month with no transactions cannot drag an
otherwise healthy user's score to the floor, and savings added today cannot silently
rewrite what June looked like.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.core.auth import hash_password
from app.core.errors import ValidationError
from app.models.account import Account, AccountType, BalanceSource
from app.models.category import Category, CategoryKind
from app.models.transaction import Direction, Transaction
from app.models.user import User
from app.repositories.health_assessment import HealthAssessmentRepository
from app.services.financial_health import FinancialHealthService

# September, with the household's statements ending in July — the situation that produced
# a score of zero for everything.
AS_OF = date(2026, 9, 18)


@pytest.fixture()
def household(session):
    user = User(
        email="health-months@example.com", password_hash=hash_password("x"), full_name="Test User"
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

    def add(occurred_on, amount, description, kind):
        session.add(
            Transaction(
                user_id=user.id,
                account_id=account.id,
                category_id=kinds[kind].id,
                occurred_on=occurred_on,
                amount=Decimal(amount),
                description=description,
                normalised_description=description.lower(),
                direction=Direction.CREDIT if Decimal(amount) >= 0 else Direction.DEBIT,
                fingerprint=f"{occurred_on}-{amount}-{description}",
            )
        )

    for month in (5, 6, 7):
        add(date(2026, month, 25), "52000", "SALARY", CategoryKind.INCOME)
        add(date(2026, month, 3), "-16900", "ESSENTIALS", CategoryKind.ESSENTIAL)
    add(date(2026, 7, 1), "-14500", "RENT", CategoryKind.ESSENTIAL)

    session.commit()
    return {"user": user, "account": account, "session": session, "add": add}


def _assess(household, **kwargs):
    return FinancialHealthService(household["session"]).assess_recent(
        user_id=household["user"].id, as_of=AS_OF, **kwargs
    )


def _by_month(assessments):
    return {a.month: a for a in assessments}


def _ratio(assessment, component: str) -> Decimal:
    return Decimal(
        {c["name"]: c for c in assessment.breakdown["components"]}[component]["ratio"]
    )


def test_each_month_is_scored_on_its_own_transactions(household):
    """Asserted on the component ratios, not the overall score.

    The overall score is a weighted sum through band tables, and two genuinely different
    months can land on the same integer — these two nearly do, because July's extra
    R14,500 of rent arrives alongside the extra cash that paid for it. The ratios are where
    "this month was scored on this month's figures" is actually visible.
    """
    months = _by_month(_assess(household))

    assert "2026-06" in months and "2026-07" in months
    # June's essentials are R16,900; July's are R31,400. Both the cover ratio (cash over
    # essentials) and the margin ratio (surplus over income) must reflect that.
    assert _ratio(months["2026-06"], "emergency_cover") != _ratio(
        months["2026-07"], "emergency_cover"
    )
    assert _ratio(months["2026-06"], "cash_flow_margin") > _ratio(
        months["2026-07"], "cash_flow_margin"
    )


def test_a_month_with_transactions_does_not_score_zero_because_this_month_is_empty(household):
    """The bug this replaced: with no September transactions, every component divided by a
    zero September income and the whole score collapsed."""
    months = _by_month(_assess(household))

    assert months["2026-06"].score > 0


def test_emergency_cover_uses_that_months_closing_balance(household):
    """Not today's balance against today's spending. June's cover is June's cash over
    June's essentials."""
    months = _by_month(_assess(household))
    june = {c["name"]: c for c in months["2026-06"].breakdown["components"]}

    assert Decimal(june["emergency_cover"]["ratio"]) > 0


def test_an_assessment_says_which_inputs_are_historical(household):
    months = _by_month(_assess(household))
    basis = months["2026-06"].breakdown["historical_basis"]

    assert basis["monthly_flows"] == "2026-06"
    assert basis["liquid_savings"] == "2026-06"
    # Neither can be reconstructed for a past month, and the assessment says so rather
    # than letting a reader assume the whole score is historical.
    assert basis["debt_minimum_payments"] == "current"
    assert basis["credit_utilisation"] == "current"


def test_reassessing_a_month_corrects_it_rather_than_adding_a_second_opinion(household):
    service = FinancialHealthService(household["session"])
    user_id = household["user"].id

    first = service.assess(user_id=user_id, as_of=AS_OF, month="2026-06")
    # Captured as values, not read off `first` afterwards: re-assessing updates that row in
    # place, so `first` and `second` are one instance and comparing their attributes would
    # be comparing an object with itself.
    first_id = first.id
    first_margin = _ratio(first, "cash_flow_margin")

    household["add"](date(2026, 6, 20), "-4000", "MORE ESSENTIALS", CategoryKind.ESSENTIAL)
    household["session"].commit()
    second = service.assess(user_id=user_id, as_of=AS_OF, month="2026-06")

    assert second.id == first_id
    assert _ratio(second, "cash_flow_margin") < first_margin

    stored = HealthAssessmentRepository(household["session"]).months_for_user(
        user_id=user_id, since="2026-06", until="2026-06"
    )
    assert len(stored) == 1


def test_the_latest_assessment_is_the_most_recent_month_not_the_most_recent_run(household):
    """Re-scoring June after July exists must not make June "the latest"."""
    service = FinancialHealthService(household["session"])
    user_id = household["user"].id

    service.assess_recent(user_id=user_id, as_of=AS_OF)
    service.assess(user_id=user_id, as_of=AS_OF, month="2026-06")

    latest = HealthAssessmentRepository(household["session"]).latest_for_user(user_id=user_id)
    assert latest.month == "2026-09"


def test_the_series_is_returned_oldest_first(household):
    assessments = _assess(household)
    months = [a.month for a in assessments]

    assert months == sorted(months)
    assert months[-1] == "2026-09"


def test_a_month_that_has_not_happened_is_refused(household):
    with pytest.raises(ValidationError, match="2026-12"):
        FinancialHealthService(household["session"]).assess(
            user_id=household["user"].id, as_of=AS_OF, month="2026-12"
        )


def test_adding_savings_moves_the_current_months_emergency_cover(session, household):
    """The complaint that started this: an emergency fund that changed nothing.

    It still cannot move a month with no essential spending — cover is savings over
    spending, and dividing by nothing has no answer — so this asserts the case that can
    move: a month that has both.
    """
    service = FinancialHealthService(session)
    user_id = household["user"].id

    before = service.assess(user_id=user_id, as_of=AS_OF, month="2026-07")
    # Values, not the instance: the second assessment mutates this same row.
    before_cover_ratio = _ratio(before, "emergency_cover")
    before_score = before.score

    session.add(
        Account(
            user_id=user_id,
            name="Emergency fund",
            account_type=AccountType.SAVINGS,
            current_balance=Decimal("60000.00"),
            balance_source=BalanceSource.MANUAL,
        )
    )
    session.commit()

    after = service.assess(user_id=user_id, as_of=AS_OF, month="2026-07")

    assert _ratio(after, "emergency_cover") > before_cover_ratio
    assert after.score > before_score
