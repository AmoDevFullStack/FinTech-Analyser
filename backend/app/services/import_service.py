"""CSV import orchestration. See specs/transactions.md.

Steps: detect format -> stage -> normalise -> deduplicate (exact + probable) -> transfer
detection -> categorise -> recurrence detection -> commit. Nothing reaches `transactions`
before an explicit commit call.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from app.core.db import DbSession

from app.core.events import IMPORT_COMMITTED, IMPORT_UNDONE, dispatch_pending, record
from app.core.errors import NotFoundError, SemanticError, ValidationError
from app.domain.payment_taxonomy import classify_payment
from app.domain.text_match import description_similarity
from app.models.category import Category
from app.models.import_batch import ImportBatch, ImportStatus, StagedTransaction
from app.models.transaction import Direction, Transaction
from app.repositories.account import AccountRepository
from app.repositories.category import CategoryRepository
from app.repositories.import_batch import ImportBatchRepository
from app.repositories.transaction import TransactionRepository
from app.repositories.column_mapping import ColumnMappingRepository
from app.services.categorisation import CategorisationService
from app.services.csv_formats import ColumnMapping, detect_format, extract_amount
from app.services.pdf_statements import (
    StatementParseError,
    extract_text_lines,
    parse_statement_text,
)
from app.services.spending_insight import SpendingInsight, SpendingInsightService
from app.services.recurrence import RecurrenceService

PROBABLE_MATCH_WINDOW_DAYS = 3
PROBABLE_MATCH_THRESHOLD = 0.8
_NOISE_PATTERN = re.compile(r"\b(?:ref|reference)?\s*#?\d{4,}\b", re.IGNORECASE)


def normalise_description(raw: str) -> str:
    cleaned = _NOISE_PATTERN.sub("", raw)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().lower()
    return cleaned


def make_fingerprint(
    *,
    user_id: UUID,
    account_id: UUID,
    occurred_on: date,
    amount: Decimal,
    normalised: str,
) -> str:
    payload = f"{user_id}|{account_id}|{occurred_on.isoformat()}|{amount}|{normalised}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ImportSummary:
    batch_id: UUID
    status: ImportStatus
    rows_parsed: int
    rows_imported: int
    rows_skipped_duplicate: int
    rows_pending_conflict: int
    rows_merged: int = 0
    # Present on the staging and commit responses, absent on resolve. What the file was,
    # and what it moved — see app/services/spending_insight.py. Optional rather than
    # required because a summary is also built for a batch that imported nothing, and a
    # zero-row impact report is noise, not information.
    insight: SpendingInsight | None = None


#: A .xlsx is a zip; a legacy .xls is an OLE compound file. Both arrive here regularly,
#: because "export" and "save as" are the same button in most banking portals.
_ZIP_MAGIC = bytes.fromhex("504b0304")
_OLE_MAGIC = bytes.fromhex("d0cf11e0")


@dataclass(frozen=True, slots=True)
class ParsedRow:
    """One transaction as a reader produced it, before anything is decided about it.

    The CSV reader and the PDF reader both end here, so dedup, conflict detection,
    classification and staging are written once and cannot drift between the two paths.
    `raw` is kept verbatim on the staged row: a user querying a figure should be shown the
    line it came from, whether that line was a CSV row or a line of statement text.
    """

    occurred_on: date
    amount: Decimal
    description: str
    raw: dict


def _decode_csv(file_bytes: bytes) -> str:
    """Read the upload as text, or say plainly why it is not.

    A PDF decoded as UTF-8 raises `UnicodeDecodeError`, which reached the catch-all handler
    as a 500 — "an unexpected error occurred" for the single most predictable thing a user
    can do wrong. A bank statement arrives as a PDF far more often than as a CSV, so this
    is the expected case, not the exotic one, and it deserves an answer that says what to do
    next.

    Recognised by content, not by filename: a PDF renamed `statement.csv` is still a PDF,
    and the magic bytes are what the parser will actually meet.
    """
    if file_bytes.startswith(b"%PDF-"):
        # Reached only when something calls `stage_csv` with a PDF directly; the upload
        # path sends PDFs to `stage_pdf` before this.
        raise ValidationError(
            "This is a PDF. Upload it as a statement rather than as a CSV.",
            details={"detected_type": "pdf"},
        )
    if file_bytes[:4] in (_ZIP_MAGIC, _OLE_MAGIC):
        raise ValidationError(
            "This is a spreadsheet, not a CSV. Save it as CSV and upload that.",
            details={"detected_type": "spreadsheet"},
        )

    try:
        return file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValidationError(
            "This file is not text. A statement must be a CSV export from your bank.",
            details={"detected_type": "binary", "reason": str(exc)},
        ) from exc


class ImportService:
    def __init__(self, session: DbSession) -> None:
        self._session = session
        self._accounts = AccountRepository(session)
        self._transactions = TransactionRepository(session)
        self._categories = CategoryRepository(session)
        self._batches = ImportBatchRepository(session)
        self._mappings = ColumnMappingRepository(session)
        self._categorisation = CategorisationService(session)
        self._insight = SpendingInsightService(session)

    def stage_file(
        self,
        *,
        user_id: UUID,
        account_id: UUID,
        file_bytes: bytes,
        mapping: ColumnMapping | None = None,
        password: str | None = None,
    ) -> ImportSummary:
        """Stage an uploaded statement, whichever form it arrived in.

        Decided by the file's leading bytes rather than its name: a PDF renamed
        `statement.csv` is still a PDF, and the parser is what meets it.
        """
        if file_bytes.startswith(b"%PDF-"):
            return self.stage_pdf(
                user_id=user_id,
                account_id=account_id,
                file_bytes=file_bytes,
                password=password,
            )
        return self.stage_csv(
            user_id=user_id,
            account_id=account_id,
            file_bytes=file_bytes,
            mapping=mapping,
        )

    def stage_csv(
        self,
        *,
        user_id: UUID,
        account_id: UUID,
        file_bytes: bytes,
        mapping: ColumnMapping | None = None,
    ) -> ImportSummary:
        account = self._accounts.get_for_user(account_id, user_id=user_id)
        if account is None:
            raise NotFoundError("No account with that identifier exists for this user.")

        text = _decode_csv(file_bytes)
        reader = csv.DictReader(io.StringIO(text))
        header = list(reader.fieldnames or [])

        detected_name = None
        if mapping is not None:
            # An explicitly supplied mapping is remembered for this account, so the next
            # import of the same export shape needs no mapping step at all.
            detected_name = "manual"
            self._mappings.remember(
                user_id=user_id,
                account_id=account_id,
                mapping=_mapping_to_dict(mapping),
                label="manual",
            )
        else:
            detected = detect_format(header)
            if detected is not None:
                detected_name, mapping = detected
            else:
                remembered = self._mappings.for_account(account_id, user_id=user_id)
                if remembered is None:
                    raise ValidationError(
                        "Could not detect a known bank format. Provide a column mapping.",
                        details={"header": header},
                    )
                mapping = _mapping_from_dict(remembered.mapping)
                detected_name = remembered.label or "remembered"
                missing = [
                    column for column in _mapping_columns(mapping) if column not in header
                ]
                if missing:
                    raise ValidationError(
                        "The mapping remembered for this account does not fit this file.",
                        details={"header": header, "missing_columns": missing},
                    )

        rows = [
            ParsedRow(
                occurred_on=_parse_date(row[mapping.date_column]),
                amount=extract_amount(mapping, row),
                description=row[mapping.description_column],
                raw=row,
            )
            for row in reader
            # A statement summary line (an opening balance, a page total) has no date.
            if row.get(mapping.date_column, "").strip()
        ]
        return self._stage(
            user_id=user_id,
            account_id=account_id,
            detected_format=detected_name,
            rows=rows,
        )

    def stage_pdf(
        self,
        *,
        user_id: UUID,
        account_id: UUID,
        file_bytes: bytes,
        password: str | None = None,
    ) -> ImportSummary:
        """Stage a statement PDF.

        The rows go through exactly the pipeline a CSV's do. What is different is the gate
        in front of them: a statement prints its opening and closing balance, so the parse
        can be checked against what the bank itself says moved. A parse that does not
        balance is refused rather than staged — a missed line or a misread decimal is the
        real risk of reading text, and the statement is holding the answer.

        Raises:
            ValidationError: if the PDF cannot be read, or if the rows read from it do not
                account for the movement between the balances it prints.
        """
        account = self._accounts.get_for_user(account_id, user_id=user_id)
        if account is None:
            raise NotFoundError("No account with that identifier exists for this user.")

        try:
            lines = extract_text_lines(file_bytes, password=password)
            statement = parse_statement_text(lines)
        except StatementParseError as exc:
            raise ValidationError(str(exc), details=exc.details) from exc

        # A loan or credit-card statement's balance rises when MORE is owed, so its
        # movements mean the opposite of a cheque account's. Reading them the same way turns
        # a R116 interest charge into R116 of income. Refused rather than guessed at: making
        # this right needs the sign convention worked through per account type, and a
        # plausible wrong figure is the thing specs/transactions.md exists to prevent.
        if statement.balance_is_liability:
            raise ValidationError(
                "This is a loan or credit-card statement. Those cannot be imported yet, "
                "because a rising balance on them means more owed rather than more held.",
                details={"format": statement.format_name, "balance_is_liability": True},
            )

        gap = statement.reconciliation_gap
        if gap is not None and gap != 0:
            raise ValidationError(
                "The transactions read from this statement do not add up to the balances "
                "it reports, so it has not been imported. Some lines were probably missed.",
                details={
                    "opening_balance": str(statement.opening_balance),
                    "closing_balance": str(statement.closing_balance),
                    "rows_read": len(statement.lines),
                    "unexplained_difference": str(gap),
                    "format": statement.format_name,
                },
            )

        if statement.disputed_lines:
            # A line whose printed amount disagrees with its balance movement means either a
            # line was missed just before it — its movement absorbed into this one — or a
            # figure was misread. Both are reasons not to import. Refusing is the point of
            # reading the balances at all: the alternative is posting an amount nobody wrote.
            raise ValidationError(
                "Some lines on this statement do not match the running balance beside "
                "them, so it has not been imported. A line was probably missed or misread.",
                details={
                    "rows_read": len(statement.lines),
                    "lines_in_dispute": list(statement.disputed_lines[:5]),
                    "lines_in_dispute_count": len(statement.disputed_lines),
                    "format": statement.format_name,
                },
            )

        rows = [
            ParsedRow(
                occurred_on=line.occurred_on,
                amount=line.amount,
                description=line.description,
                raw={
                    "line": line.raw,
                    "balance": str(line.balance) if line.balance is not None else None,
                    # True where the printed amount disagreed with the balance movement.
                    # The balance was used; this says the line is worth a second look.
                    "amount_disputed": line.amount_disputed,
                },
            )
            for line in statement.lines
        ]
        return self._stage(
            user_id=user_id,
            account_id=account_id,
            detected_format=statement.format_name,
            rows=rows,
        )

    def _stage(
        self,
        *,
        user_id: UUID,
        account_id: UUID,
        detected_format: str | None,
        rows: list[ParsedRow],
    ) -> ImportSummary:
        """Everything that happens to a parsed row, whatever read it."""
        batch = ImportBatch(
            user_id=user_id,
            account_id=account_id,
            status=ImportStatus.STAGED,
            detected_format=detected_format,
        )
        self._batches.add(batch)

        staged_rows: list[StagedTransaction] = []
        seen_fingerprints: set[str] = set()
        rows_parsed = 0
        for parsed in rows:
            rows_parsed += 1
            occurred_on = parsed.occurred_on
            amount = parsed.amount
            description = parsed.description
            row = parsed.raw
            normalised = normalise_description(description)
            fingerprint = make_fingerprint(
                user_id=user_id,
                account_id=account_id,
                occurred_on=occurred_on,
                amount=amount,
                normalised=normalised,
            )

            is_exact_duplicate = (
                fingerprint in seen_fingerprints
                or self._transactions.fingerprint_exists(fingerprint, user_id=user_id)
            )
            seen_fingerprints.add(fingerprint)
            conflict_candidate_id = None
            if not is_exact_duplicate:
                conflict_candidate_id = self._find_probable_duplicate(
                    account_id=account_id,
                    user_id=user_id,
                    occurred_on=occurred_on,
                    amount=amount,
                    normalised=normalised,
                )

            # Detection at staging, not at commit: the impact preview the user approves
            # has to be computed from the same classification the committed rows carry.
            # See app/services/spending_insight.py.
            classification = classify_payment(description=normalised, amount=amount)

            staged_rows.append(
                StagedTransaction(
                    import_batch_id=batch.id,
                    occurred_on=occurred_on,
                    amount=amount,
                    description=description,
                    normalised_description=normalised,
                    fingerprint=fingerprint,
                    is_exact_duplicate=is_exact_duplicate,
                    conflict_candidate_id=conflict_candidate_id,
                    payment_method=classification.method,
                    spending_purpose=classification.purpose,
                    merchant=classification.merchant,
                    purpose_confidence=classification.purpose_confidence,
                    raw_row=row,
                )
            )

        self._batches.add_staged(staged_rows)

        pending = sum(1 for r in staged_rows if r.conflict_candidate_id is not None)
        batch.rows_parsed = rows_parsed
        batch.rows_skipped_duplicate = sum(
            1 for r in staged_rows if r.is_exact_duplicate
        )
        batch.rows_pending_conflict = pending
        batch.status = (
            ImportStatus.AWAITING_RESOLUTION if pending else ImportStatus.STAGED
        )
        self._session.commit()

        return ImportSummary(
            batch_id=batch.id,
            status=batch.status,
            rows_parsed=rows_parsed,
            rows_imported=0,
            rows_skipped_duplicate=batch.rows_skipped_duplicate,
            rows_pending_conflict=pending,
            # Computed here so the user sees what the file contains and what committing it
            # would do before they commit it, which is the whole reason staging exists.
            insight=self._insight.preview_batch(batch.id, user_id=user_id),
        )

    def resolve_conflicts(
        self, batch_id: UUID, *, user_id: UUID, resolutions: dict[UUID, str]
    ) -> None:
        batch = self._batches.get_for_user(batch_id, user_id=user_id)
        if batch is None:
            raise NotFoundError(
                "No import batch with that identifier exists for this user."
            )

        for staged in self._batches.staged_for(batch_id):
            if staged.id in resolutions:
                staged.resolution = resolutions[staged.id]

        remaining = [
            r
            for r in self._batches.staged_for(batch_id)
            if r.conflict_candidate_id is not None and r.resolution is None
        ]
        if not remaining:
            batch.status = ImportStatus.STAGED
        self._session.commit()

    def commit(self, batch_id: UUID, *, user_id: UUID) -> ImportSummary:
        batch = self._batches.get_for_user(batch_id, user_id=user_id)
        if batch is None:
            raise NotFoundError(
                "No import batch with that identifier exists for this user."
            )
        if batch.status == ImportStatus.AWAITING_RESOLUTION:
            raise SemanticError("Unresolved conflicts remain for this import batch.")

        staged_rows = self._batches.staged_for(batch_id)
        importable = [
            r
            for r in staged_rows
            if not r.is_exact_duplicate and r.resolution not in ("skip", "merge")
        ]
        merged = self._apply_merges(
            [r for r in staged_rows if r.resolution == "merge"], user_id=user_id
        )

        categories = self._categories.list_for_user(user_id=user_id)
        corrections = self._categorisation.corrected_history(user_id=user_id)
        transactions = [
            self._build_transaction(
                row,
                batch=batch,
                user_id=user_id,
                categories=categories,
                corrections=corrections,
            )
            for row in importable
        ]
        self._transactions.add_all(transactions)
        self._detect_transfers(transactions)
        self._session.flush()
        # Built before the batch is marked committed and the staged rows are cleared, but
        # after the transfer pass, so a transfer's two legs are already excluded from the
        # totals it reports. `exclude_batch_id` keeps the rows just written out of the
        # "before" side; without it every import would report itself as changing nothing.
        insight = self._insight.insight_for_transactions(
            user_id=user_id,
            account_id=batch.account_id,
            transactions=transactions,
            exclude_batch_id=batch.id,
        )
        RecurrenceService(self._session).apply(user_id=user_id)

        self._batches.clear_staged(batch_id)
        batch.rows_imported = len(transactions)
        batch.rows_merged = merged
        batch.status = ImportStatus.COMMITTED
        # Recorded in the same transaction as the rows themselves, so a committed import
        # and the record that it happened cannot disagree. What it triggers — the snapshot,
        # the health score, forecast staleness, risk flags — is in
        # app/services/event_handlers.py, not here: this method knows an import committed,
        # not what the rest of the product wants to do about it.
        record(
            self._session,
            user_id=user_id,
            name=IMPORT_COMMITTED,
            payload={
                "batch_id": str(batch.id),
                "account_id": str(batch.account_id),
                "rows_imported": len(transactions),
                "rows_merged": merged,
            },
        )
        self._session.commit()

        # After the commit, never before: a handler reads the state the event describes,
        # and uncommitted rows are not that state.
        dispatch_pending(self._session, user_id=user_id)

        return ImportSummary(
            batch_id=batch.id,
            status=batch.status,
            rows_parsed=batch.rows_parsed,
            rows_imported=batch.rows_imported,
            rows_skipped_duplicate=batch.rows_skipped_duplicate,
            rows_pending_conflict=0,
            rows_merged=merged,
            insight=insight,
        )

    def undo(self, batch_id: UUID, *, user_id: UUID) -> int:
        batch = self._batches.get_for_user(batch_id, user_id=user_id)
        if batch is None:
            raise NotFoundError(
                "No import batch with that identifier exists for this user."
            )
        if batch.status != ImportStatus.COMMITTED:
            raise SemanticError("Only a committed import batch can be undone.")

        rows = self._transactions.for_user(user_id=user_id, limit=1_000_000)
        undone = [t for t in rows if t.import_batch_id == batch_id]
        now = datetime.utcnow()
        for txn in undone:
            txn.deleted_at = now
        batch.status = ImportStatus.UNDONE
        record(
            self._session,
            user_id=user_id,
            name=IMPORT_UNDONE,
            payload={"batch_id": str(batch.id), "rows_removed": len(undone)},
        )
        self._session.commit()

        # Undoing an import moves the same figures committing it moved, in the opposite
        # direction. Before events, this path recomputed nothing at all.
        dispatch_pending(self._session, user_id=user_id)
        return len(undone)

    def _apply_merges(self, rows: list[StagedTransaction], *, user_id: UUID) -> int:
        """Resolve a probable duplicate by updating the existing row in place.

        Merge means "this is the same transaction, and the imported version is the better
        record of it" — a re-export with a corrected posting date or a fuller description.
        It updates rather than inserting, so the resolution the user chose never produces
        the duplicate they were asked about.
        """
        merged = 0
        if not rows:
            return merged

        history = {
            t.id: t for t in self._transactions.for_user(user_id=user_id, limit=100_000)
        }
        for row in rows:
            if row.conflict_candidate_id is None:
                continue
            existing = history.get(row.conflict_candidate_id)
            if existing is None:
                continue
            existing.occurred_on = row.occurred_on
            existing.amount = row.amount
            existing.description = row.description
            existing.normalised_description = row.normalised_description
            existing.fingerprint = row.fingerprint
            merged += 1
        return merged

    def _build_transaction(
        self,
        row: StagedTransaction,
        *,
        batch: ImportBatch,
        user_id: UUID,
        categories: list[Category],
        corrections: dict[str, UUID] | None = None,
    ) -> Transaction:
        suggestion = self._categorisation.suggest(
            normalised_description=row.normalised_description,
            categories=categories,
            corrections=corrections or {},
            amount=row.amount,
        )
        transaction = Transaction(
            user_id=user_id,
            account_id=batch.account_id,
            category_id=suggestion.category.id if suggestion.category else None,
            occurred_on=row.occurred_on,
            amount=row.amount,
            description=row.description,
            normalised_description=row.normalised_description,
            direction=Direction.CREDIT if row.amount >= 0 else Direction.DEBIT,
            category_confidence=suggestion.confidence if suggestion.category else None,
            category_set_by_user=False,
            import_batch_id=batch.id,
            fingerprint=row.fingerprint,
        )
        # Carried across from the staged row rather than recomputed, so a classification a
        # user saw in the preview is the one that lands in the table.
        transaction.payment_method = row.payment_method
        transaction.spending_purpose = row.spending_purpose
        transaction.merchant = row.merchant
        transaction.purpose_confidence = row.purpose_confidence
        if transaction.payment_method is None:
            self._insight.classify_transaction(transaction)
        return transaction

    def _find_probable_duplicate(
        self,
        *,
        account_id: UUID,
        user_id: UUID,
        occurred_on: date,
        amount: Decimal,
        normalised: str,
    ) -> UUID | None:
        from datetime import timedelta

        candidates = self._transactions.by_account(
            account_id,
            user_id=user_id,
            since=occurred_on - timedelta(days=PROBABLE_MATCH_WINDOW_DAYS),
            until=occurred_on + timedelta(days=PROBABLE_MATCH_WINDOW_DAYS),
            limit=1000,
        )
        for candidate in candidates:
            if candidate.amount != amount:
                continue
            similarity = description_similarity(candidate.normalised_description, normalised)
            if similarity >= Decimal(str(PROBABLE_MATCH_THRESHOLD)):
                return candidate.id
        return None

    def _detect_transfers(self, transactions: list[Transaction]) -> None:
        from uuid import uuid4

        for outflow in transactions:
            if outflow.amount >= 0 or outflow.transfer_group_id is not None:
                continue
            for inflow in transactions:
                if (
                    inflow.amount != -outflow.amount
                    or inflow.account_id == outflow.account_id
                    or inflow.transfer_group_id is not None
                ):
                    continue
                if abs((inflow.occurred_on - outflow.occurred_on).days) <= 3:
                    group_id = uuid4()
                    outflow.transfer_group_id = group_id
                    inflow.transfer_group_id = group_id
                    break

def _mapping_to_dict(mapping: ColumnMapping) -> dict[str, str | None]:
    return {
        "date_column": mapping.date_column,
        "description_column": mapping.description_column,
        "balance_column": mapping.balance_column,
        "amount_column": mapping.amount_column,
        "debit_column": mapping.debit_column,
        "credit_column": mapping.credit_column,
    }


def _mapping_from_dict(raw: dict) -> ColumnMapping:
    return ColumnMapping(
        date_column=raw["date_column"],
        description_column=raw["description_column"],
        balance_column=raw.get("balance_column"),
        amount_column=raw.get("amount_column"),
        debit_column=raw.get("debit_column"),
        credit_column=raw.get("credit_column"),
    )


def _mapping_columns(mapping: ColumnMapping) -> list[str]:
    """Every column the mapping requires the file to contain."""
    return [
        column
        for column in (
            mapping.date_column,
            mapping.description_column,
            mapping.amount_column,
            mapping.debit_column,
            mapping.credit_column,
        )
        if column is not None
    ]


def _parse_date(raw: str) -> date:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d %b %y"):
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
    raise ValidationError(f"Unrecognised date format: {raw!r}")
