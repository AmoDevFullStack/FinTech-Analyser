"""The Capitec statement layout, taken from a real file.

Every rule asserted here exists because an actual Capitec "Main Account Statement" broke
the parser. The fixtures below keep that file's layout and quirks exactly; the names and
amounts are changed.

What the real file taught, in the order it hurt:

  * a `Fee*` column, so a transaction line carries THREE figures — amount, fee, balance —
    and reading the second as the balance turns a R1.00 fee into the state of the account
  * the VAT marker glued straight onto the amount: `-7.00*`, which stopped the figure
    matching at all and left the fee beside it standing in as the amount
  * `R`-prefixed balances in the header: `Opening Balance: R1 804.22`
  * summary sections BEFORE the table — fee summary, money in/out, scheduled payments —
    whose lines also start with a date and end with an amount
  * `Pending Card Transactions` after the table, which have not reached the balance
  * loan statements printed newest-first, where a rising balance means more owed

Against the real 666-row statement these rules produce a parse that reconciles to the cent:
opening R1 804.22, closing R282.52, no unexplained difference, no disputed line.
"""

from decimal import Decimal

from app.services.pdf_statements import parse_money, parse_statement_text

CAPITEC = [
    "Main Account Statement",
    "MR A CLIENT Capitec Bank Limited",
    "Account 1578620781 VAT Registration Number 4680173723",
    "Statement Information",
    "From Date: 01/08/2025 Opening Balance: R1 804.22",
    "To Date: 04/08/2025 Closing Balance: R1 110.47",
    "Print Date: 19/11/2025 08:18 Available Balance: R52.52",
    "Money In Summary R188 510.24 Money Out Summary -R190 031.94",
    "Fee Summary -R733.75",
    "Cash Withdrawal Fee -R240.00",
    "Scheduled Payments",
    "Debit Orders Card Subscriptions",
    "02/03/2026 Tracker -R199.00 04/03/2026 Apple.com -R59.99",
    "Transaction History",
    "Date Description Category Money In Money Out Fee* Balance",
    "01/08/2025 PayShap Payment Received: Discovery Amo Other Income 2 000.00 3 804.22",
    "01/08/2025 Banking App Immediate Payment: Tshepang Digital Payments -1 500.00 -1.00 2 303.22",
    "01/08/2025 Banking App Voucher Purchase: Blu (LLJJXUSALCW7) Betting/Lottery -1 000.00 -2.00 1 301.22",
    "02/08/2025 Hpy*world Coffee Cape Town (Card 4109) Groceries -29.00 1 272.22",
    "* Includes VAT at 15%",
    "24hr Client Care Centre 0860 10 20 43 E ClientCare@capitecbank.co.za W capitecbank.co.za",
    "Unique Document No.: a4a89a26-f1b8-4527 / 204 / V2.0 - 09/07/2022 Page 2 of 15",
    "Date Description Category Money In Money Out Fee* Balance",
    "02/08/2025 Banking App External PayShap Payment: Martin M Digital Payments -150.00 -2.00 1 120.22",
    "(076 656 3419)",
    "03/08/2025 Banking App Prepaid Purchase: Vodacom Cellphone -7.00* -0.50 1 112.72",
    "04/08/2025 Online Purchase: Uber Cape Town (Card 4109) Public Transport -2.25 1 110.47",
    "Pending Card Transactions",
    "17/09/2026 BP Gp (Card 0387) -R150.00",
    "17/09/2026 Engen Centurion (Card 0387) -R300.00",
]

CAPITEC_LOAN = [
    "Loan Statement",
    "Account Name: 7 MONTH TERM LOAN",
    "Date: Branch Description Amount (Dr) Amount (Cr) BALANCE",
    "25/03/2026 997 CLOSING BALANCE 4 910.94",
    "25/03/2026 997 DEBICHK PAYMENT -762.38 4 910.94",
    "24/03/2026 997 MONTHLY DUES -762.38 5 673.32",
    "24/03/2026 997 INTEREST 116.22 5 673.32",
    "05/03/2026 4354 DEBICHECK RETURN 1 479.06 5 557.10",
    "04/03/2026 997 DEBICHK PAYMENT -1 479.06 4 078.04",
    "01/03/2026 0 OPENING BALANCE 5 557.10",
]


def test_a_real_capitec_statement_reconciles_exactly():
    """The whole point. Opening, every movement, closing — all from the document."""
    statement = parse_statement_text(CAPITEC)

    assert statement.format_name == "capitec_pdf"
    assert statement.opening_balance == Decimal("1804.22")
    assert statement.closing_balance == Decimal("1110.47")
    assert statement.reconciliation_gap == Decimal("0.00")
    assert statement.disputed_lines == ()
    assert statement.reconciles is True


def test_the_balance_is_the_last_figure_and_the_fee_belongs_to_the_amount():
    """A line with a fee column carries three figures: amount, fee, balance.

    Reading the second as the balance makes a R1.00 fee the state of the account. The fee
    is part of what left, because the bank takes both in one balance movement.
    """
    statement = parse_statement_text(CAPITEC)
    payment = statement.lines[1]

    assert payment.balance == Decimal("2303.22")
    assert payment.amount == Decimal("-1501.00")  # -1 500.00 payment plus -1.00 fee


def test_the_vat_asterisk_does_not_swallow_the_amount():
    """`-7.00*` is an amount with the VAT marker glued on. Before this was handled the
    figure did not match, the line lost its amount, and the R0.50 fee beside it was read as
    the amount instead — which is the kind of error that still balances."""
    statement = parse_statement_text(CAPITEC)
    vodacom = next(line for line in statement.lines if "Vodacom" in line.description)

    assert vodacom.amount == Decimal("-7.50")  # -7.00 airtime plus -0.50 fee
    assert vodacom.balance == Decimal("1112.72")


def test_the_summary_sections_are_not_read_as_transactions():
    """The statement opens with fee, money-in, money-out and scheduled-payment summaries.
    Their lines start with a date and end with an amount, and they summarise the
    transactions below — reading them imports every debit order twice."""
    statement = parse_statement_text(CAPITEC)

    assert all("Tracker" not in line.description for line in statement.lines)
    assert all("Cash Withdrawal Fee" not in line.description for line in statement.lines)
    # The seven lines under `Transaction History`, and nothing from above or below it.
    assert len(statement.lines) == 7


def test_pending_card_transactions_are_not_imported():
    """An authorisation that has not come off the balance has not happened yet."""
    statement = parse_statement_text(CAPITEC)

    assert all("BP Gp" not in line.description for line in statement.lines)
    assert all(line.occurred_on.year == 2025 for line in statement.lines)


def test_a_wrapped_description_does_not_become_a_transaction():
    """`(076 656 3419)` is the tail of the line above it."""
    statement = parse_statement_text(CAPITEC)

    assert all(line.description != "(076 656 3419)" for line in statement.lines)


def test_r_prefixed_money_is_read():
    assert parse_money("R1 804.22") == Decimal("1804.22")
    assert parse_money("-R733.75") == Decimal("-733.75")


# ---------------------------------------------------------------------------------------
# The loan statement: newest-first, and a liability
# ---------------------------------------------------------------------------------------
def test_a_newest_first_statement_is_turned_around_before_the_balance_walk():
    """A balance movement only means anything in the order the money moved. Read as
    printed, every amount becomes the previous row's."""
    statement = parse_statement_text(CAPITEC_LOAN)
    dates = [line.occurred_on for line in statement.lines]

    assert dates == sorted(dates)
    assert statement.reconciles is True


def test_opening_and_closing_marker_rows_are_not_transactions():
    """`OPENING BALANCE 5 557.10` carries a date and a figure like any row. Imported, it
    posts the entire balance as income."""
    statement = parse_statement_text(CAPITEC_LOAN)

    assert all("BALANCE" not in line.description.upper() for line in statement.lines)


def test_a_line_that_moved_no_money_is_reported_rather_than_imported():
    """`MONTHLY DUES` states the instalment falling due; the balance does not move. The
    balance is the authority on whether anything happened, and the line is counted so a
    short row count can still be explained."""
    statement = parse_statement_text(CAPITEC_LOAN)

    assert all("MONTHLY DUES" not in line.description for line in statement.lines)
    assert any("MONTHLY DUES" in note for note in statement.informational_lines)


def test_a_loan_statement_is_flagged_because_its_balance_means_the_opposite():
    """A rising balance here is more owed, not more held. Read like a cheque account, a
    R116 interest charge becomes R116 of income."""
    assert parse_statement_text(CAPITEC_LOAN).balance_is_liability is True
    assert parse_statement_text(CAPITEC).balance_is_liability is False
