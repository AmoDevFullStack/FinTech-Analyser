"""Reading a statement PDF's text. No database, no PDF — the parsing rules are pure.

The fixtures below are the text a statement's text layer produces, which is what
`extract_text_lines` hands over. Keeping the rules testable without a binary file is the
point of that split: every shape a bank might print can be written down here.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.services.pdf_statements import (
    StatementParseError,
    detect_bank,
    parse_date,
    parse_money,
    parse_statement_text,
    statement_years,
)

NBSP = chr(0x00A0)

SBSA = [
    "The Standard Bank of South Africa Limited",
    "Statement period: 25 June 2026 to 24 July 2026",
    "Account number 123456789",
    "Opening balance 27 600,00",
    "25 Jun 2026 SALARY ACB CREDIT 52 000,00 79 600,00",
    "01 Jul 2026 RENT DEBIT ORDER 14 500,00 65 100,00",
    "03 Jul 2026 POS PURCHASE WOOLWORTHS CLAREMONT CARD 4471 1 234,56 63 865,44",
    "12 Jul 2026 IB TRANSFER TO SAVINGS 5 000,00 58 865,44",
    "24 Jul 2026 MONTHLY SERVICE FEE 115,00 58 750,44",
    "Closing balance 58 750,44",
]


# ---------------------------------------------------------------------------------------
# Money
# ---------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1 234,56", "1234.56"),
        (f"1{NBSP}234,56", "1234.56"),
        ("1,234.56", "1234.56"),
        ("1234.56", "1234.56"),
        ("-1 234,56", "-1234.56"),
        ("1 234,56-", "-1234.56"),
        ("1 234,56 Cr", "1234.56"),
        ("1 234,56 Dr", "-1234.56"),
        ("52 000,00", "52000.00"),
        ("0,00", "0.00"),
    ],
)
def test_money_is_parsed_as_statements_print_it(raw, expected):
    assert parse_money(raw) == Decimal(expected)


def test_a_lone_comma_group_is_thousands_not_cents():
    """`1,234` is one thousand two hundred and thirty four. Reading it as 1.234 would turn
    R1,234.00 into R1.23, which is the kind of error that reconciles to nothing."""
    assert parse_money("1,234") == Decimal("1234")
    assert parse_money("1,23") == Decimal("1.23")


def test_text_that_is_not_money_is_refused():
    with pytest.raises(ValueError):
        parse_money("CARD")


# ---------------------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("2026-07-24", date(2026, 7, 24)),
        ("24/07/2026", date(2026, 7, 24)),
        ("24-07-2026", date(2026, 7, 24)),
        ("24 Jul 2026", date(2026, 7, 24)),
        ("24 July 2026", date(2026, 7, 24)),
    ],
)
def test_dates_are_parsed_in_every_shape_statements_print(raw, expected):
    assert parse_date(raw) == expected


def test_dates_are_day_first():
    """`03/04/2026` is 3 April on a South African statement. Guessing month-first would move
    a third of every month's transactions into the wrong month, silently."""
    assert parse_date("03/04/2026") == date(2026, 4, 3)


def test_a_date_without_a_year_needs_one_supplied():
    assert parse_date("24 Jul", default_year=2026) == date(2026, 7, 24)
    with pytest.raises(ValueError, match="no year"):
        parse_date("24 Jul")


# ---------------------------------------------------------------------------------------
# The statement as a whole
# ---------------------------------------------------------------------------------------
def test_transaction_lines_are_read_and_the_rest_is_ignored():
    statement = parse_statement_text(SBSA)

    assert len(statement.lines) == 5
    assert [line.occurred_on for line in statement.lines] == [
        date(2026, 6, 25),
        date(2026, 7, 1),
        date(2026, 7, 3),
        date(2026, 7, 12),
        date(2026, 7, 24),
    ]
    # The address block, the account number and the balance lines are not transactions, and
    # nothing had to list them to exclude them: they do not start with a date and end with
    # money.
    assert all("Opening" not in line.description for line in statement.lines)


def test_the_sign_comes_from_the_balance_not_the_printed_figure():
    """Every amount in the fixture is printed unsigned, as statements do. The balance says
    which way the money went, and it cannot be ambiguous about it."""
    statement = parse_statement_text(SBSA)
    amounts = [line.amount for line in statement.lines]

    assert amounts[0] == Decimal("52000.00")  # salary in
    assert amounts[1] == Decimal("-14500.00")  # rent out
    assert amounts[2] == Decimal("-1234.56")
    assert amounts[4] == Decimal("-115.00")


def test_a_description_ending_in_digits_is_not_read_as_an_amount():
    """`CARD 4471` has no cents, so it is description. A figure invented from a card number
    would post a transaction that never happened."""
    statement = parse_statement_text(SBSA)
    woolworths = statement.lines[2]

    assert woolworths.description.endswith("CARD 4471")
    assert woolworths.amount == Decimal("-1234.56")


def test_a_statement_that_balances_reconciles():
    statement = parse_statement_text(SBSA)

    assert statement.opening_balance == Decimal("27600.00")
    assert statement.closing_balance == Decimal("58750.44")
    assert statement.reconciliation_gap == Decimal("0.00")
    assert statement.reconciles is True


def test_a_missed_line_is_caught_by_the_line_that_absorbed_it():
    """The whole reason the balances are read — and a lesson about how.

    Dropping a line does NOT open a gap between the opening and closing balances. Amounts
    are derived from balance movements, so the line after the missing one simply absorbs
    it and the total still lands exactly on the closing balance. What gives it away is that
    the absorbing line's printed amount no longer matches its movement.
    """
    without_rent = [line for line in SBSA if "RENT" not in line]
    statement = parse_statement_text(without_rent)

    # The total still balances, which is exactly why this check cannot be the only one.
    assert statement.reconciliation_gap == Decimal("0.00")

    # Woolworths printed 1 234,56 but the balance fell by 15 734,56 — the rent it swallowed.
    woolworths = statement.lines[1]
    assert woolworths.amount == Decimal("-15734.56")
    assert woolworths.amount_disputed is True
    assert statement.reconciles is False


def test_a_statement_missing_its_last_line_opens_a_gap():
    """The check that the opening/closing comparison does catch on its own."""
    without_last = [line for line in SBSA if "SERVICE FEE" not in line]
    statement = parse_statement_text(without_last)

    assert statement.reconciliation_gap == Decimal("115.00")
    assert statement.reconciles is False


def test_a_printed_amount_contradicting_the_balance_is_flagged():
    """The balance is used, and the line is marked as worth a human's eye."""
    tampered = list(SBSA)
    tampered[5] = "01 Jul 2026 RENT DEBIT ORDER 14 000,00 65 100,00"
    statement = parse_statement_text(tampered)

    rent = statement.lines[1]
    assert rent.amount == Decimal("-14500.00")  # the balance movement, not the printed figure
    assert rent.amount_disputed is True
    assert len(statement.disputed_lines) == 1
    # The totals still balance, and the parse is still refused: a figure nobody wrote is
    # not something to import quietly.
    assert statement.reconciliation_gap == Decimal("0.00")
    assert statement.reconciles is False


def test_a_statement_with_no_balances_parses_without_the_check():
    """Absence of the check is not a failure — it is the absence of the check, and the gap
    is reported as unknown rather than as zero."""
    lines = [
        "Capitec Bank",
        "25 Jun 2026 SALARY 52 000,00",
        "01 Jul 2026 RENT -14 500,00",
    ]
    statement = parse_statement_text(lines)

    assert len(statement.lines) == 2
    assert statement.reconciliation_gap is None
    assert statement.reconciles is True
    # With no balance to derive from, the printed sign is all there is.
    assert statement.lines[0].amount == Decimal("52000.00")
    assert statement.lines[1].amount == Decimal("-14500.00")


def test_text_with_no_transactions_is_refused():
    with pytest.raises(StatementParseError, match="No transactions"):
        parse_statement_text(["Standard Bank", "Your statement is attached.", "Page 1 of 2"])


def test_the_bank_is_named_from_the_text():
    assert detect_bank(SBSA) == "sbsa_pdf"
    assert detect_bank(["Capitec Bank Limited"]) == "capitec_pdf"
    assert detect_bank(["A statement"]) == "pdf"


def test_the_statement_period_supplies_the_year_for_lines_without_one():
    assert statement_years(SBSA) == (2026, 2026)

    dated_without_years = [
        "Standard Bank",
        "Statement period: 20 December 2025 to 20 January 2026",
        "Opening balance 1 000,00",
        "24 Dec SALARY 5 000,00 6 000,00",
        "03 Jan GROCERIES 500,00 5 500,00",
    ]
    statement = parse_statement_text(dated_without_years)

    # December belongs to the year the statement opened in; January to the next one.
    assert statement.lines[0].occurred_on == date(2025, 12, 24)
    assert statement.lines[1].occurred_on == date(2026, 1, 3)
