"""Reading a bank statement PDF. See specs/transactions.md step 1.

Banks hand out PDFs by default; the CSV export is the one you have to go looking for. So
this is the path most statements will actually take, and it has a property the CSV path
does not: a statement PDF prints its opening balance, its closing balance, and usually a
running balance beside every line. That is a checksum on the parse, and this module is
built around it.

How the sign of an amount is decided, which is the thing most likely to be silently wrong:

    Where a running balance is present, the amount is `balance(n) - balance(n - 1)`.

Not the printed amount's sign. Statements write debits as `-1 234,56`, as `1 234,56-`, as
`1 234,56 Dr`, and as an unmarked figure in a debit column, and a debit imported as a credit
inflates income by the amount spent — the silent corruption specs/transactions.md exists to
prevent. The balance column cannot express that ambiguity: money either left the account or
it did not. The printed amount is still parsed, and a line where its magnitude disagrees
with the balance movement is reported rather than guessed at.

Structure, deliberately:

- `parse_statement_text` is pure — it takes lines of text and returns rows. Every parsing
  rule is testable without a PDF, which is what makes the rules testable at all.
- `extract_text_lines` is the only part that touches pdfplumber, and it does nothing but
  pull the text layer out.
- A PDF with no text layer — a scan, a photo of a statement — is refused. OCR guessing at a
  digit in a money column has no place behind a financial figure.

Provenance, stated because it matters for trust:

- **Capitec is verified.** These rules were built against two real Capitec statements — a
  666-row main account statement and a loan statement — and the main account one parses to
  a reconciliation of exactly zero: opening R1 804.22, every movement, closing R282.52, no
  disputed line. What that file taught is written into tests/services/
  test_pdf_statements_capitec.py, quirk by quirk.
- **The other banks are not.** Their line shapes are the common South African layouts, not
  validated against a real export. The reconciliation gate is what makes shipping that
  acceptable: a layout this module reads wrongly will not balance, and a statement that
  does not balance is refused rather than imported.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

# Every date shape these statements print. Ordered most explicit first, because a parser
# that guesses between `03/04/2026` readings is a parser that will eventually read a South
# African statement as American.
_DATE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^(\d{4})-(\d{2})-(\d{2})$"), "ymd"),
    (re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$"), "dmy"),
    (re.compile(r"^(\d{1,2})-(\d{1,2})-(\d{4})$"), "dmy"),
    (re.compile(r"^(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{4})$"), "dMy"),
    (re.compile(r"^(\d{1,2})\s+([A-Za-z]{3,9})$"), "dM"),
    (re.compile(r"^(\d{1,2})([A-Za-z]{3})$"), "dM"),
)

#: The characters a statement may use between thousands: an ordinary space, a non-breaking
#: space, and a narrow non-breaking space. Built with `chr` rather than written literally —
#: two of the three are invisible in a source file, and a regex that depends on which
#: invisible character someone pasted is a regex that breaks silently.
_SPACES = " " + chr(0x00A0) + chr(0x202F)

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

#: A money figure as statements print it: `1 234,56`, `1,234.56`, `-1234.56`, `1 234,56-`,
#: `R1 804.22`, `-R733.75`, `-7.00*`, `1 234,56 Cr`.
#:
#: The currency prefix, the sign markers and the VAT asterisk are all matched here so that
#: none of them can be mistaken for the start of the next field. `*` is Capitec's "includes
#: VAT at 15%" marker and is glued straight onto the figure.
_MONEY = re.compile(
    rf"(?P<sign>-)?R?\s?(?P<sign2>-)?(?P<digits>\d[\d,.{_SPACES}]*\d|\d)"
    rf"(?P<trail>-|\*|\s?(?:Cr|CR|Dr|DR))?\*?$"
)

#: A money figure at the END of a line, matched rather than split on, because thousands are
#: separated by a space as often as by a comma — `52 000,00` is one figure and splitting the
#: line on whitespace makes it two.
#:
#: A trailing `*` is Capitec's "includes VAT at 15%" marker, glued to the figure:
#: `-7.00*`. Without it in this pattern the figure does not match, the line silently loses
#: its amount, and the fee beside it is read as the amount instead.
#:
#: Cents are required. Statements print them on every figure, and demanding them is what
#: stops a description ending in `CARD 4471` being read as an amount. A figure without cents
#: at the end of a line is part of the description, which is the safer reading: a missed
#: amount fails the reconciliation check loudly, while a description read as money would
#: post a transaction that never happened.
_MONEY_TAIL = re.compile(
    r"(?:^|\s)"
    rf"(?P<figure>-?R?\s?-?\d{{1,3}}(?:[{_SPACES},]\d{{3}})*[.,]\d{{2}}"
    r"|-?R?\s?-?\d+[.,]\d{2})"
    r"(?P<trail>-|\*|\s?(?:Cr|CR|Dr|DR))?\*?\s*$"
)


def _strip_money_tail(text: str) -> tuple[str, Decimal] | None:
    """Pull one money figure off the end of a line, returning the rest and the figure."""
    match = _MONEY_TAIL.search(text)
    if match is None:
        return None
    try:
        value = parse_money(match.group("figure") + (match.group("trail") or ""))
    except ValueError:
        return None
    return text[: match.start()].rstrip(), value


#: `Statement period: 24 April 2026 to 24 July 2026`, and the shapes near it. Used only to
#: supply the year for lines that print `24 Jul` with no year of their own.
_PERIOD = re.compile(
    r"(?:statement\s+period|period|from)\D{0,20}"
    r"(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4})"
    r"\D{1,10}"
    r"(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4})",
    re.IGNORECASE,
)

_OPENING = re.compile(r"(opening|brought\s+forward|balance\s+b/?f)", re.IGNORECASE)
_CLOSING = re.compile(r"(closing|carried\s+forward|balance\s+c/?f)", re.IGNORECASE)

#: Which bank produced this, read from the text. Detection only names the format in the
#: import record; it changes no parsing rule, because the rules below are shared.
_BANK_MARKERS = (
    ("sbsa_pdf", re.compile(r"standard\s+bank", re.IGNORECASE)),
    ("fnb_pdf", re.compile(r"\bfnb\b|first\s+national\s+bank", re.IGNORECASE)),
    ("absa_pdf", re.compile(r"\babsa\b", re.IGNORECASE)),
    ("nedbank_pdf", re.compile(r"\bnedbank\b", re.IGNORECASE)),
    ("capitec_pdf", re.compile(r"\bcapitec\b", re.IGNORECASE)),
    ("discovery_pdf", re.compile(r"discovery\s+bank", re.IGNORECASE)),
    ("tymebank_pdf", re.compile(r"\btyme\s?bank\b", re.IGNORECASE)),
)


class StatementParseError(ValueError):
    """The text could not be read as a statement. Carries `details` for the error envelope."""

    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


@dataclass(frozen=True, slots=True)
class StatementLine:
    occurred_on: date
    description: str
    #: Signed: negative left the account. Derived from the balance movement where a running
    #: balance is present, and from the printed sign where it is not.
    amount: Decimal
    balance: Decimal | None
    #: The line exactly as it appeared, kept for `staged_transactions.raw_row` so a user
    #: querying a figure can be shown the text it came from.
    raw: str
    #: True where the printed amount's magnitude disagreed with the balance movement. The
    #: balance wins; this marks the line as worth a human's eye.
    amount_disputed: bool = False


@dataclass(frozen=True, slots=True)
class ParsedStatement:
    format_name: str
    lines: tuple[StatementLine, ...]
    opening_balance: Decimal | None
    closing_balance: Decimal | None
    #: Lines whose printed amount contradicted the balance movement.
    disputed_lines: tuple[str, ...]
    #: Lines that printed an amount while the balance did not move — a due date, a notice.
    #: Reported rather than imported, so a row count that looks short can be explained.
    informational_lines: tuple[str, ...] = ()
    #: True for a loan or credit-card statement, where a RISING balance means more owed.
    #: The movements below are still what the balance did; what they mean is inverted, and
    #: only the account they are imported into can settle that.
    balance_is_liability: bool = False

    @property
    def reconciles(self) -> bool:
        """Whether this parse can be trusted against what the statement itself says.

        Two checks, and the second is the one that matters:

        1. The opening balance plus everything read equals the closing balance. This catches
           a parse that missed lines at the very start or the very end.
        2. No line's printed amount contradicts its balance movement.

        The second exists because the first cannot fail on its own once amounts are derived
        from balances: drop a line in the middle and the next line's balance movement simply
        absorbs it, and the total still lands on the closing balance. What gives it away is
        that the absorbed line's printed amount no longer matches the movement — which is
        exactly what `disputed_lines` collects.

        `None` balances mean the statement did not print them. That is not a failure, it is
        the absence of check 1, and `reconciliation_gap` is `None` to say so.
        """
        gap_is_fine = self.reconciliation_gap is None or self.reconciliation_gap == 0
        return gap_is_fine and not self.disputed_lines

    @property
    def reconciliation_gap(self) -> Decimal | None:
        if self.opening_balance is None or self.closing_balance is None:
            return None
        moved = sum((line.amount for line in self.lines), Decimal("0"))
        return (self.opening_balance + moved) - self.closing_balance


def parse_money(raw: str) -> Decimal:
    """Parse a money figure as a South African statement prints it.

    Handles `1 234,56`, `1,234.56`, `1234.56`, non-breaking and narrow spaces, a leading or
    trailing minus, and a `Cr`/`Dr` suffix.

    The separator rule: where both `,` and `.` appear, the rightmost is the decimal point
    and the other is a thousands separator. Where only one appears, it is a decimal point
    only if exactly two digits follow it — `1,234` is one thousand two hundred and thirty
    four, and `1,23` is one and twenty three cents. Guessing the other way turns R1,234.00
    into R1.23.

    Raises:
        ValueError: if the text is not a money figure.
    """
    match = _MONEY.match(raw.strip())
    if match is None:
        raise ValueError(f"Unrecognised amount: {raw!r}")

    digits = re.sub(f"[{_SPACES}]", "", match.group("digits"))
    last_comma = digits.rfind(",")
    last_dot = digits.rfind(".")

    if last_comma >= 0 and last_dot >= 0:
        decimal_at = max(last_comma, last_dot)
    elif last_comma >= 0:
        decimal_at = last_comma if len(digits) - last_comma - 1 == 2 else -1
    elif last_dot >= 0:
        decimal_at = last_dot if len(digits) - last_dot - 1 == 2 else -1
    else:
        decimal_at = -1

    if decimal_at >= 0:
        whole = re.sub(r"[,.]", "", digits[:decimal_at])
        cents = digits[decimal_at + 1 :]
        cleaned = f"{whole}.{cents}"
    else:
        cleaned = re.sub(r"[,.]", "", digits)

    try:
        value = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"Unrecognised amount: {raw!r}") from exc

    trail = (match.group("trail") or "").strip().lower()
    negative = (
        match.group("sign") == "-"
        or match.group("sign2") == "-"
        or trail == "-"
        or trail == "dr"
    )
    return -value if negative else value


def parse_date(raw: str, *, default_year: int | None = None) -> date:
    """Parse a statement date. `03/04/2026` is 3 April, never 4 March.

    Day-first because these are South African statements; a parser that guesses would
    silently move a third of every month's transactions into the wrong month.

    Raises:
        ValueError: if the text is not a date, or omits the year with no `default_year`.
    """
    text = raw.strip()
    for pattern, shape in _DATE_PATTERNS:
        match = pattern.match(text)
        if match is None:
            continue

        if shape == "ymd":
            year, month, day = (int(part) for part in match.groups())
        elif shape == "dmy":
            day, month, year = (int(part) for part in match.groups())
        elif shape == "dMy":
            day = int(match.group(1))
            month = _month_number(match.group(2))
            year = int(match.group(3))
        else:
            if default_year is None:
                raise ValueError(f"Date {raw!r} has no year and none was supplied")
            day = int(match.group(1))
            month = _month_number(match.group(2))
            year = default_year

        return date(year, month, day)

    raise ValueError(f"Unrecognised date: {raw!r}")


def _month_number(name: str) -> int:
    key = name[:3].lower()
    if key not in _MONTHS:
        raise ValueError(f"Unrecognised month: {name!r}")
    return _MONTHS[key]


def looks_like_statement_date(token: str) -> bool:
    return any(pattern.match(token.strip()) for pattern, _ in _DATE_PATTERNS)


def detect_bank(lines: list[str]) -> str:
    """Name the format from the text. Cosmetic: it is recorded on the import batch so a
    user can see what was recognised, and changes no parsing rule."""
    head = "\n".join(lines[:40])
    for name, marker in _BANK_MARKERS:
        if marker.search(head):
            return name
    return "pdf"


def statement_years(lines: list[str]) -> tuple[int | None, int | None]:
    """The years the statement period spans, for lines that print `24 Jul` with no year.

    Returns `(first_year, last_year)`. A statement running December to January spans two,
    which is why both are reported rather than one.
    """
    text = " ".join(lines[:60])
    match = _PERIOD.search(text)
    if match is None:
        return None, None
    try:
        start = parse_date(match.group(1))
        end = parse_date(match.group(2))
    except ValueError:
        return None, None
    return start.year, end.year


#: Where the transaction table starts, and where anything after it stops being one.
#:
#: A statement is not only its transactions. Capitec opens with a fee summary, a money-in
#: and money-out summary, scheduled payments and a spending summary — pages of lines that
#: begin with a date and end with an amount, and that are summaries OF the transactions
#: below. Reading them as transactions imports every debit order twice.
#:
#: It closes with pending card transactions: authorisations that have not been taken off
#: the balance yet. Those are not transactions either, and importing one posts money that
#: has not moved.
_SECTION_START = re.compile(r"^\s*transaction\s+history\s*$", re.IGNORECASE)
_SECTION_END = re.compile(r"^\s*pending\s+card\s+transactions\s*$", re.IGNORECASE)


def transaction_section(lines: list[str]) -> list[str]:
    """The part of the statement that is the transaction table.

    Where no `Transaction History` heading exists — a simpler statement that is nothing but
    its table — the whole document is the section, which is the old behaviour.
    """
    start = next((i for i, line in enumerate(lines) if _SECTION_START.match(line)), None)
    if start is None:
        body = lines
    else:
        body = lines[start + 1 :]

    end = next((i for i, line in enumerate(body) if _SECTION_END.match(line)), None)
    return body if end is None else body[:end]


_LIABILITY_STATEMENT = re.compile(
    r"loan\s+statement|credit\s+card\s+statement|term\s+loan|outstanding\s+balance",
    re.IGNORECASE,
)


def is_liability_statement(lines: list[str]) -> bool:
    """Whether a rising balance on this statement means more owed rather than more held.

    On a cheque account a balance going up is money arriving. On a loan or a credit card it
    is the opposite, and a parser that reads the movement the same way in both cases turns
    a R116 interest charge into R116 of income. What the movements mean is decided by the
    account, not by the parser, so this only reports what the document says it is.
    """
    return bool(_LIABILITY_STATEMENT.search(chr(10).join(lines[:60])))


def _is_descending(dates: list[date]) -> bool:
    """Whether these rows are printed newest-first.

    Judged on the whole run rather than on the first pair: a statement can print two
    transactions from one day in either order, and one inversion says nothing. Ties are
    ignored for the same reason.
    """
    if len(dates) < 3:
        return False
    forward = sum(1 for a, b in zip(dates, dates[1:]) if b > a)
    backward = sum(1 for a, b in zip(dates, dates[1:]) if b < a)
    return backward > forward


def parse_statement_text(lines: list[str]) -> ParsedStatement:
    """Read transaction rows out of a statement's text.

    A transaction line is one that begins with a date and ends with at least one money
    figure. Everything else — headers, addresses, the marketing block, page footers — is
    skipped by that rule alone rather than by a list of things to ignore, which would need
    extending for every bank.

    Raises:
        StatementParseError: if no transaction lines could be read at all.
    """
    format_name = detect_bank(lines)
    first_year, last_year = statement_years(lines)
    opening = _labelled_balance(lines, _OPENING)
    closing = _labelled_balance(lines, _CLOSING)
    body = transaction_section(lines)

    parsed: list[StatementLine] = []
    disputed: list[str] = []
    informational: list[str] = []
    previous_balance = opening
    year_cursor = first_year
    previous_month: int | None = None

    rows = []
    for raw in body:
        line = raw.strip()
        if not line:
            continue
        row = _split_transaction_line(line, default_year=year_cursor)
        if row is not None:
            rows.append((line, row))

    # Newest-first statements exist — Capitec's loan statement is one. The balance movement
    # between two rows only means anything in the order the money actually moved, so the
    # rows are turned around before the walk rather than read backwards.
    if _is_descending([row[1][0] for row in rows]):
        rows.reverse()

    for line, row in rows:

        occurred_on, description, figures = row

        # `OPENING BALANCE 5 463.52` is a marker, not a transaction. It carries a date and a
        # figure like any row, and importing it posts the whole balance as income.
        if _OPENING.search(description) or _CLOSING.search(description):
            continue

        # A statement that prints `24 Dec` then `03 Jan` has crossed into the next year.
        if previous_month is not None and occurred_on.month < previous_month and year_cursor:
            year_cursor = min(year_cursor + 1, last_year or year_cursor + 1)
            occurred_on = occurred_on.replace(year=year_cursor)
        previous_month = occurred_on.month

        # The balance is the LAST figure on the line, never the second. A statement with a
        # fee column prints three — amount, fee, balance — and reading the fee as the
        # balance turns R0.50 into the state of the account.
        #
        # Everything before the balance is movement. Capitec charges the fee on the same
        # line as the transaction it belongs to and includes it in the balance, so the two
        # are summed: the pair is what actually left the account.
        if len(figures) > 1:
            balance = figures[-1]
            printed_amount = sum(figures[:-1], Decimal("0"))
        else:
            balance = None
            printed_amount = figures[0]

        amount = printed_amount
        amount_disputed = False
        if balance is not None and previous_balance is not None:
            moved = balance - previous_balance

            # A line that prints an amount while the balance stays put moved no money. A
            # loan statement's `MONTHLY DUES` is the instalment that falls due, not a
            # payment of it. The balance is the authority on whether anything happened, so
            # the line is counted and dropped rather than imported as a transaction that
            # did not occur — or disputed, which would block an otherwise perfect parse.
            if moved == 0 and printed_amount != 0:
                previous_balance = balance
                informational.append(line)
                continue

            # The balance decides. It cannot express the ambiguity a printed debit can.
            if abs(moved) != abs(printed_amount):
                amount_disputed = True
                disputed.append(line)
            amount = moved
        if balance is not None:
            previous_balance = balance

        parsed.append(
            StatementLine(
                occurred_on=occurred_on,
                description=description,
                amount=amount,
                balance=balance,
                raw=line,
                amount_disputed=amount_disputed,
            )
        )

    if not parsed:
        raise StatementParseError(
            "No transactions could be read from this statement.",
            details={"lines_examined": len(lines), "format": format_name},
        )

    return ParsedStatement(
        format_name=format_name,
        lines=tuple(parsed),
        opening_balance=opening,
        closing_balance=closing,
        disputed_lines=tuple(disputed),
        informational_lines=tuple(informational),
        balance_is_liability=is_liability_statement(lines),
    )


def _split_transaction_line(
    line: str, *, default_year: int | None
) -> tuple[date, str, list[Decimal]] | None:
    """`24 Jul 2026  POS PURCHASE WOOLWORTHS  -450,00  12 345,67` to its three parts.

    Returns `None` for any line that is not a transaction, which is most of them.
    """
    tokens = line.split()
    if not tokens:
        return None

    occurred_on = None
    for size in (3, 2, 1):
        if len(tokens) < size:
            continue
        try:
            occurred_on = parse_date(" ".join(tokens[:size]), default_year=default_year)
        except ValueError:
            continue
        tokens = tokens[size:]
        break
    if occurred_on is None:
        return None

    # Money figures run backwards from the end: [.. description ..] amount [balance].
    rest = " ".join(tokens)
    figures: list[Decimal] = []
    while len(figures) < 3:
        stripped = _strip_money_tail(rest)
        if stripped is None:
            break
        rest, figure = stripped
        figures.insert(0, figure)

    description = rest.strip()
    if not figures or not description:
        return None

    return occurred_on, description, figures


def _labelled_balance(lines: list[str], label: re.Pattern[str]) -> Decimal | None:
    """The figure on the line that names itself the opening or closing balance."""
    for raw in lines:
        if not label.search(raw):
            continue
        stripped = _strip_money_tail(raw.strip())
        if stripped is not None:
            return stripped[1]
    return None


def extract_text_lines(file_bytes: bytes, *, password: str | None = None) -> list[str]:
    """Pull the text layer out of a PDF, one line per line of the page.

    The only part of this module that touches a PDF library, and it does nothing but read.

    Raises:
        StatementParseError: if the file is encrypted and no password was given, if the
            password is wrong, or if the PDF carries no text layer at all — a scan or a
            photograph. The last case is refused rather than sent to OCR: a digit guessed
            out of an image has no business behind a financial figure, and "we could not
            read this" is a better answer than a wrong balance.
    """
    try:
        import pdfplumber
    except ImportError as exc:  # pragma: no cover - a deployment problem, not a user one
        raise StatementParseError(
            "Statement PDFs cannot be read on this deployment.",
            details={"missing_dependency": "pdfplumber"},
        ) from exc

    import io

    try:
        with pdfplumber.open(io.BytesIO(file_bytes), password=password or "") as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
    except Exception as exc:
        message = str(exc).lower()
        if "password" in message or "encrypt" in message:
            raise StatementParseError(
                "This statement is password protected. Supply the password to read it.",
                details={"password_required": True},
            ) from exc
        raise StatementParseError(
            "This PDF could not be opened.", details={"reason": str(exc)}
        ) from exc

    lines = [line for page in pages for line in page.splitlines()]
    if not any(line.strip() for line in lines):
        raise StatementParseError(
            "This PDF has no text in it — it looks like a scan or a photograph. Ask your "
            "bank for the original PDF, or export the statement as CSV.",
            details={"text_layer": False, "pages": len(pages)},
        )
    return lines
