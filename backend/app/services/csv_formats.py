"""Bank CSV format detection. See specs/transactions.md step 1.

Detectors for the seven South African banks the spec names: FNB, Standard Bank (SBSA),
Absa, Nedbank, Capitec, Discovery Bank and TymeBank — plus the manual-mapping fallback
the PLAN.md sprint-1 risk mitigation calls for. Adding a bank is adding a detector
function and a row to `DETECTORS`; nothing else in the import pipeline changes, aside
from `extract_amount` below for formats that split debit/credit into separate columns
instead of one signed amount column.

Provenance, stated because it matters for trust: the FNB and SBSA header shapes were
present in this repository before this change. The five added here are built from the
column names those banks' exports are documented as using, and have NOT been validated
against a real export from each institution. Detection failing is a recoverable outcome —
the user maps columns manually and the mapping is remembered for that account — but a
detector matching the wrong shape would not be, so each is deliberately strict: it
requires its full header set, not a subset that another bank might also satisfy. Validate
each against a real file before relying on it, and widen only with a sample in hand.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


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


def _to_decimal(raw: str) -> Decimal:
    """Parse a money cell as a bank actually writes it.

    South African exports separate thousands with a space as often as with a comma, and
    some emit a non-breaking space. Stripping only commas leaves "1 234.56" unparseable,
    which fails an import for a formatting choice rather than a data problem.

    Raises:
        ValueError: if the cell is not a number once separators are removed.
    """
    cleaned = (
        raw.replace(" ", "")
        .replace(" ", "")
        .replace(" ", "")
        .replace(",", "")
        .strip()
    )
    if not cleaned:
        return Decimal("0")
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"Unrecognised amount: {raw!r}") from exc


def extract_amount(mapping: ColumnMapping, row: dict[str, str]) -> Decimal:
    """Read the signed transaction amount for one CSV row per `mapping`.

    Single-column formats (amount_column) already carry a sign. Split-column formats
    (debit_column/credit_column) put the debit and the credit in separate cells, with
    exactly one populated per row.

    A split-column debit is normalised to negative here regardless of how the bank wrote
    it. Some exports carry the minus sign in the debit column and some do not, and a
    debit silently imported as positive would inflate income by the amount spent — the
    exact "silent corruption" specs/transactions.md is written to prevent. The magnitude
    is taken and the sign applied from which column the value was in, so both conventions
    import identically.
    """
    if mapping.amount_column is not None:
        return _to_decimal(row[mapping.amount_column])

    assert mapping.debit_column is not None and mapping.credit_column is not None
    credit_raw = row[mapping.credit_column].strip()
    if credit_raw:
        return abs(_to_decimal(credit_raw))
    debit_raw = row[mapping.debit_column].strip()
    if not debit_raw:
        return Decimal("0")
    return -abs(_to_decimal(debit_raw))


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


ABSA_HEADER = {"Transaction Date", "Description", "Amount", "Balance"}


def detect_absa(header: list[str]) -> ColumnMapping | None:
    if ABSA_HEADER.issubset(set(header)):
        return ColumnMapping(
            date_column="Transaction Date",
            description_column="Description",
            amount_column="Amount",
            balance_column="Balance",
        )
    return None


NEDBANK_HEADER = {"Date", "Narrative", "Debit Amount", "Credit Amount", "Balance"}


def detect_nedbank(header: list[str]) -> ColumnMapping | None:
    if NEDBANK_HEADER.issubset(set(header)):
        return ColumnMapping(
            date_column="Date",
            description_column="Narrative",
            debit_column="Debit Amount",
            credit_column="Credit Amount",
            balance_column="Balance",
        )
    return None


CAPITEC_HEADER = {"Posting Date", "Transaction Description", "Money In", "Money Out", "Balance"}


def detect_capitec(header: list[str]) -> ColumnMapping | None:
    if CAPITEC_HEADER.issubset(set(header)):
        return ColumnMapping(
            date_column="Posting Date",
            description_column="Transaction Description",
            debit_column="Money Out",
            credit_column="Money In",
            balance_column="Balance",
        )
    return None


DISCOVERY_HEADER = {"Transaction Date", "Transaction Description", "Transaction Amount", "Running Balance"}


def detect_discovery(header: list[str]) -> ColumnMapping | None:
    if DISCOVERY_HEADER.issubset(set(header)):
        return ColumnMapping(
            date_column="Transaction Date",
            description_column="Transaction Description",
            amount_column="Transaction Amount",
            balance_column="Running Balance",
        )
    return None


TYMEBANK_HEADER = {"Date", "Description", "Debit", "Credit", "Balance"}


def detect_tymebank(header: list[str]) -> ColumnMapping | None:
    if TYMEBANK_HEADER.issubset(set(header)):
        return ColumnMapping(
            date_column="Date",
            description_column="Description",
            debit_column="Debit",
            credit_column="Credit",
            balance_column="Balance",
        )
    return None


# Order matters where header sets overlap: the more specific shape must be tried first.
# Absa and Discovery both use "Transaction Date", so Discovery — which also requires
# "Transaction Description" and "Running Balance" — is checked before Absa's looser set.
DETECTORS = {
    "fnb": detect_fnb,
    "sbsa": detect_sbsa,
    "capitec": detect_capitec,
    "nedbank": detect_nedbank,
    "discovery": detect_discovery,
    "absa": detect_absa,
    "tymebank": detect_tymebank,
}


def detect_format(header: list[str]) -> tuple[str, ColumnMapping] | None:
    for name, detector in DETECTORS.items():
        mapping = detector(header)
        if mapping is not None:
            return name, mapping
    return None
