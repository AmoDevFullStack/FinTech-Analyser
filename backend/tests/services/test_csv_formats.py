"""Format detection and amount extraction. No database needed.

The header shapes for the five banks added beyond FNB and SBSA are documented shapes, not
shapes verified against a real export — see the module docstring in app/services/
csv_formats.py. These tests therefore prove the detectors behave as written and do not
collide with each other; they do not prove any bank actually exports this header.
"""

from decimal import Decimal

import pytest

from app.services.csv_formats import (
    ABSA_HEADER,
    CAPITEC_HEADER,
    DISCOVERY_HEADER,
    FNB_HEADER,
    NEDBANK_HEADER,
    SBSA_HEADER,
    TYMEBANK_HEADER,
    ColumnMapping,
    detect_format,
    extract_amount,
)

ALL_HEADERS = {
    "fnb": FNB_HEADER,
    "sbsa": SBSA_HEADER,
    "absa": ABSA_HEADER,
    "nedbank": NEDBANK_HEADER,
    "capitec": CAPITEC_HEADER,
    "discovery": DISCOVERY_HEADER,
    "tymebank": TYMEBANK_HEADER,
}


@pytest.mark.parametrize("expected_name", sorted(ALL_HEADERS))
def test_each_bank_header_detects_as_that_bank(expected_name: str) -> None:
    detected = detect_format(sorted(ALL_HEADERS[expected_name]))
    assert detected is not None, expected_name
    name, mapping = detected
    assert name == expected_name
    assert mapping.date_column in ALL_HEADERS[expected_name]
    assert mapping.description_column in ALL_HEADERS[expected_name]


def test_an_unknown_header_detects_as_nothing_rather_than_guessing() -> None:
    assert detect_format(["When", "What", "How much"]) is None


def test_an_empty_header_detects_as_nothing() -> None:
    assert detect_format([]) is None


def test_a_single_column_format_keeps_the_sign_the_bank_wrote() -> None:
    mapping = ColumnMapping(
        date_column="Date", description_column="Description", amount_column="Amount"
    )
    assert extract_amount(mapping, {"Amount": "-1 234.56"}) == Decimal("-1234.56")
    assert extract_amount(mapping, {"Amount": "2,500.00"}) == Decimal("2500.00")


def test_a_split_column_debit_is_always_negative() -> None:
    """A debit imported as positive would inflate income by the amount spent — the
    silent corruption specs/transactions.md exists to prevent. Both conventions (the
    bank writing the minus sign, and the bank omitting it) must import identically.
    """
    mapping = ColumnMapping(
        date_column="Date",
        description_column="Description",
        debit_column="Debit",
        credit_column="Credit",
    )

    unsigned = extract_amount(mapping, {"Debit": "900.00", "Credit": ""})
    signed = extract_amount(mapping, {"Debit": "-900.00", "Credit": ""})

    assert unsigned == Decimal("-900.00")
    assert signed == Decimal("-900.00")


def test_a_split_column_credit_is_always_positive() -> None:
    mapping = ColumnMapping(
        date_column="Date",
        description_column="Description",
        debit_column="Debit",
        credit_column="Credit",
    )
    assert extract_amount(mapping, {"Debit": "", "Credit": "5,200.00"}) == Decimal("5200.00")


def test_a_blank_split_row_is_zero_not_an_error() -> None:
    mapping = ColumnMapping(
        date_column="Date",
        description_column="Description",
        debit_column="Debit",
        credit_column="Credit",
    )
    assert extract_amount(mapping, {"Debit": "", "Credit": ""}) == Decimal("0")


def test_a_mapping_needs_exactly_one_amount_convention() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        ColumnMapping(date_column="Date", description_column="Description")
    with pytest.raises(ValueError, match="exactly one"):
        ColumnMapping(
            date_column="Date",
            description_column="Description",
            amount_column="Amount",
            debit_column="Debit",
            credit_column="Credit",
        )
