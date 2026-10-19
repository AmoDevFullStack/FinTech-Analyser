"""Spending detection rules. Pure, so no database.

The descriptions below are the shapes South African bank CSV exports actually produce —
FNB, Standard Bank, Absa, Nedbank, Capitec — with amounts and account references changed.
They are the reference source for these assertions in the sense the financial-domain-engine
skill means: the expected answer comes from what the statement line says, not from what the
code currently does.
"""

from decimal import Decimal

import pytest

from app.domain.payment_taxonomy import (
    PURPOSE_CATEGORY_NAME,
    PURPOSE_KIND,
    PaymentMethod,
    SpendingPurpose,
    SpendKind,
    classify_payment,
    extract_merchant,
)


def _classify(description: str, amount: str):
    return classify_payment(description=description, amount=Decimal(amount))


# --------------------------------------------------------------------------------------
# Method — how the money moved
# --------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("description", "amount", "expected"),
    [
        ("DEBIT ORDER RENT PROPERTY GROUP", "-14500.00", PaymentMethod.DEBIT_ORDER),
        ("D/ORDER OUTSURANCE", "-1850.00", PaymentMethod.DEBIT_ORDER),
        ("STOP ORDER SCHOOL FEES", "-3200.00", PaymentMethod.STOP_ORDER),
        ("POS PURCHASE WOOLWORTHS CLAREMONT", "-842.31", PaymentMethod.CARD_PURCHASE),
        ("CARD PURCHASE UBER EATS", "-215.00", PaymentMethod.CARD_PURCHASE),
        ("ONLINE PURCHASE TAKEALOT", "-1299.00", PaymentMethod.CARD_ONLINE),
        ("ATM WITHDRAWAL SANDTON CITY", "-1000.00", PaymentMethod.ATM_WITHDRAWAL),
        ("CASH DEPOSIT CDM ROSEBANK", "2000.00", PaymentMethod.CASH_DEPOSIT),
        ("SALARY DEPOSIT ACME PTY LTD", "52000.00", PaymentMethod.SALARY_DEPOSIT),
        ("PAYSHAP PAYMENT TO NADIA", "-500.00", PaymentMethod.INSTANT_PAYMENT),
        ("TRANSFER TO SAVINGS POCKET", "-3000.00", PaymentMethod.INTERNAL_TRANSFER),
        ("MONTHLY ACCOUNT FEE", "-115.00", PaymentMethod.BANK_FEE),
        ("CREDIT INTEREST", "12.44", PaymentMethod.INTEREST),
        ("REVERSAL POS PURCHASE", "842.31", PaymentMethod.REVERSAL),
    ],
)
def test_method_is_read_from_the_statement_phrase(description, amount, expected) -> None:
    assert _classify(description, amount).method is expected


def test_an_eft_inflow_and_outflow_are_told_apart_by_sign() -> None:
    assert _classify("EFT PAYMENT TO LANDLORD", "-14500.00").method is PaymentMethod.EFT_OUT
    assert _classify("EFT PAYMENT FROM TENANT", "9500.00").method is PaymentMethod.EFT_IN


def test_a_salary_word_on_an_outflow_is_not_a_salary_deposit() -> None:
    """"SALARY TRANSFER TO SAVINGS" is the user moving their salary, not receiving it.

    Reading it as a deposit would add it to income a second time, which is precisely how a
    savings rate ends up above 100%.
    """
    classification = _classify("SALARY TRANSFER TO SAVINGS", "-20000.00")
    assert classification.method is not PaymentMethod.SALARY_DEPOSIT
    assert classification.kind is not SpendKind.INCOME


def test_an_unrecognised_description_still_reports_a_direction() -> None:
    outflow = _classify("QWERTYUIOP 8891", "-100.00")
    assert outflow.method is PaymentMethod.EFT_OUT
    assert outflow.method_confidence < Decimal("0.5")
    assert _classify("QWERTYUIOP 8891", "100.00").method is PaymentMethod.EFT_IN


# --------------------------------------------------------------------------------------
# Purpose — what it was for
# --------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("description", "amount", "expected"),
    [
        ("DEBIT ORDER RENT PROPERTY GROUP", "-14500.00", SpendingPurpose.RENT),
        ("EFT PAYMENT TO LANDLORD", "-12000.00", SpendingPurpose.RENT),
        ("DEBIT ORDER SA HOME LOANS", "-11200.00", SpendingPurpose.BOND_REPAYMENT),
        ("BODY CORPORATE LEVY", "-1450.00", SpendingPurpose.LEVIES),
        ("CITY OF CAPE TOWN MUNICIPAL", "-2310.00", SpendingPurpose.RATES_AND_TAXES),
        ("ESKOM PREPAID ELECTRICITY", "-800.00", SpendingPurpose.UTILITIES),
        ("POS PURCHASE CHECKERS HYPER", "-1842.31", SpendingPurpose.GROCERIES),
        ("ENGEN RONDEBOSCH", "-950.00", SpendingPurpose.FUEL),
        ("DEBIT ORDER WESBANK", "-6430.00", SpendingPurpose.VEHICLE_INSTALMENT),
        ("DEBIT ORDER OUTSURANCE PREMIUM", "-1850.00", SpendingPurpose.INSURANCE),
        ("DEBIT ORDER DISCOVERY HEALTH", "-4300.00", SpendingPurpose.MEDICAL),
        ("DEBIT ORDER VODACOM", "-699.00", SpendingPurpose.TELECOMS),
        ("NETFLIX.COM", "-199.00", SpendingPurpose.SUBSCRIPTIONS),
        ("UBER EATS", "-215.00", SpendingPurpose.DINING),
        ("STOP ORDER SCHOOL FEES", "-3200.00", SpendingPurpose.EDUCATION),
        ("EASY EQUITIES DEPOSIT", "-2500.00", SpendingPurpose.INVESTMENT),
        ("TRANSFER TO TAX FREE SAVINGS", "-3000.00", SpendingPurpose.SAVINGS),
        ("CAPITEC PERSONAL LOAN REPAYMENT", "-2100.00", SpendingPurpose.DEBT_REPAYMENT),
        ("MONTHLY ACCOUNT FEE", "-115.00", SpendingPurpose.BANK_CHARGES),
        ("SALARY DEPOSIT ACME PTY LTD", "52000.00", SpendingPurpose.SALARY),
    ],
)
def test_purpose_is_read_from_the_statement_phrase(description, amount, expected) -> None:
    assert _classify(description, amount).purpose is expected


def test_rent_and_a_bond_are_separate_purposes_with_different_kinds() -> None:
    """Both are the roof over someone's head. Only one is a debt the payoff engines can
    schedule, and only one builds equity, so they cannot share a kind."""
    rent = _classify("DEBIT ORDER RENT PROPERTY GROUP", "-14500.00")
    bond = _classify("DEBIT ORDER SA HOME LOANS BOND", "-11200.00")

    assert rent.kind is SpendKind.ESSENTIAL
    assert bond.kind is SpendKind.DEBT


def test_a_misspelled_merchant_is_recognised_by_edit_distance() -> None:
    """The fuzzy pass. A statement that prints WOOLWORTS is still groceries."""
    classification = _classify("POS PURCH WOOLWORTS CLAREMNT", "-842.31")
    assert classification.purpose is SpendingPurpose.GROCERIES
    assert classification.matched_rule.endswith("fuzzy:woolworths")
    assert classification.purpose_confidence < Decimal("0.8")


def test_an_expense_phrase_on_an_inflow_is_not_booked_as_negative_spending() -> None:
    """A refund of groceries is income, not minus-groceries. No cash-flow figure in this
    system models negative spending, so booking it that way would corrupt the month."""
    classification = _classify("REFUND WOOLWORTHS CLAREMONT", "842.31")
    assert classification.kind is SpendKind.INCOME


def test_an_unrecognised_outflow_is_unknown_rather_than_guessed() -> None:
    classification = _classify("QWERTYUIOP 8891", "-100.00")
    assert classification.purpose is SpendingPurpose.UNKNOWN
    assert classification.kind is None
    assert classification.purpose_confidence == Decimal("0.000000")


def test_the_two_confidences_move_independently() -> None:
    """A certain method with an unknown purpose has to report exactly that."""
    classification = _classify("DEBIT ORDER 4471992", "-1200.00")
    assert classification.method is PaymentMethod.DEBIT_ORDER
    assert classification.method_confidence == Decimal("0.900000")
    assert classification.purpose is SpendingPurpose.UNKNOWN
    assert classification.purpose_confidence == Decimal("0.000000")


# --------------------------------------------------------------------------------------
# Merchant
# --------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("POS PURCHASE 4471 WOOLWORTHS CLAREMONT", "woolworths claremont"),
        ("DEBIT ORDER OUTSURANCE PREMIUM", "outsurance premium"),
        ("FNB APP PAYMENT FROM NADIA", "app nadia"),
        ("ATM WITHDRAWAL", None),
    ],
)
def test_merchant_strips_the_payment_mechanics(description, expected) -> None:
    assert extract_merchant(description) == expected


# --------------------------------------------------------------------------------------
# Invariants
# --------------------------------------------------------------------------------------
def test_every_purpose_except_unknown_has_a_kind_and_a_category_name() -> None:
    """A purpose the engine can return but nothing can file is a purpose that gets detected
    and then discarded. app/services/category_seed.py builds the chart of accounts from
    these two tables, so a gap here is a gap there."""
    for purpose in SpendingPurpose:
        if purpose is SpendingPurpose.UNKNOWN:
            continue
        assert purpose in PURPOSE_KIND, purpose
        assert purpose in PURPOSE_CATEGORY_NAME, purpose


def test_spend_kind_mirrors_the_category_kind_enum() -> None:
    """`app/domain/` may not import models, so the two enums are kept in step by this test
    rather than by the type system."""
    from app.models.category import CategoryKind

    assert {k.value for k in SpendKind} == {k.value for k in CategoryKind}


def test_classification_is_deterministic() -> None:
    first = _classify("DEBIT ORDER RENT PROPERTY GROUP", "-14500.00")
    second = _classify("DEBIT ORDER RENT PROPERTY GROUP", "-14500.00")
    assert first == second
