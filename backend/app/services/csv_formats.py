"""Bank CSV format detection. See specs/transactions.md step 1.

v1 ships two detectors — FNB's and Standard Bank's (SBSA) statement exports — plus the
manual-mapping fallback the PLAN.md sprint-1 risk mitigation calls for. Adding a bank is
adding a detector function and a row to `DETECTORS`; nothing else in the import pipeline
changes, aside from `extract_amount` below for formats that split debit/credit into
separate columns instead of one signed amount column.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ColumnMapping:
    date_column: str
    description_column: str
    balance_column: str | None = None
    amount_column: str | None = None
    debit_column: str | None = None
    credit_column: str | None = None

    def __post_init__(self) -> None:
        has_single = self.amount_column is not None
        has_split = self.debit_column is not None and self.credit_column is not None
        if has_single == has_split:
            raise ValueError(
                "ColumnMapping needs exactly one of amount_column or "
                "debit_column+credit_column."
            )


def extract_amount(mapping: ColumnMapping, row: dict[str, str]) -> Decimal:
    """Read the signed transaction amount for one CSV row per `mapping`.

    Single-column formats (amount_column) already carry a sign. Split-column formats
    (debit_column/credit_column) store the amount already signed too — a debit negative,
    a credit positive — with exactly one of the two cells populated per row; this just
    picks whichever one is non-blank.
    """
    if mapping.amount_column is not None:
        return Decimal(row[mapping.amount_column].replace(",", ""))

    assert mapping.debit_column is not None and mapping.credit_column is not None
    credit_raw = row[mapping.credit_column].strip()
    if credit_raw:
        return Decimal(credit_raw.replace(",", ""))
    debit_raw = row[mapping.debit_column].strip()
    return Decimal(debit_raw.replace(",", ""))


FNB_HEADER = {"Date", "Description", "Amount", "Balance"}


def detect_fnb(header: list[str]) -> ColumnMapping | None:
    if FNB_HEADER.issubset(set(header)):
        return ColumnMapping(
            date_column="Date",
            description_column="Description",
            amount_column="Amount",
            balance_column="Balance",
        )
    return None


SBSA_HEADER = {
    "Date",
    "Description",
    "Transaction Type",
    "Payments",
    "Deposits",
    "Balance",
}


def detect_sbsa(header: list[str]) -> ColumnMapping | None:
    if SBSA_HEADER.issubset(set(header)):
        return ColumnMapping(
            date_column="Date",
            description_column="Description",
            debit_column="Payments",
            credit_column="Deposits",
            balance_column="Balance",
        )
    return None


DETECTORS = {"fnb": detect_fnb, "sbsa": detect_sbsa}


def detect_format(header: list[str]) -> tuple[str, ColumnMapping] | None:
    for name, detector in DETECTORS.items():
        mapping = detector(header)
        if mapping is not None:
            return name, mapping
    return None
