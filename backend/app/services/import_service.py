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
from difflib import SequenceMatcher
from uuid import UUID

from app.core.db import DbSession

from app.core.errors import NotFoundError, SemanticError, ValidationError
from app.models.category import Category, CategoryKind
from app.models.import_batch import ImportBatch, ImportStatus, StagedTransaction
from app.models.transaction import Direction, Transaction
from app.repositories.account import AccountRepository
from app.repositories.category import CategoryRepository
from app.repositories.import_batch import ImportBatchRepository
from app.repositories.transaction import TransactionRepository
from app.services.csv_formats import ColumnMapping, detect_format, extract_amount
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


class ImportService:
    def __init__(self, session: DbSession) -> None:
        self._session = session
        self._accounts = AccountRepository(session)
        self._transactions = TransactionRepository(session)
        self._categories = CategoryRepository(session)
        self._batches = ImportBatchRepository(session)

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

        text = file_bytes.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        header = list(reader.fieldnames or [])

        detected_name = None
        if mapping is None:
            detected = detect_format(header)
            if detected is None:
                raise ValidationError(
                    "Could not detect a known bank format. Provide a column mapping.",
                    details={"header": header},
                )
            detected_name, mapping = detected

        batch = ImportBatch(
            user_id=user_id,
            account_id=account_id,
            status=ImportStatus.STAGED,
            detected_format=detected_name,
        )
        self._batches.add(batch)

        staged_rows: list[StagedTransaction] = []
        seen_fingerprints: set[str] = set()
        rows_parsed = 0
        for row in reader:
            if not row[mapping.date_column].strip():
                continue  # statement summary line (e.g. opening balance), not a transaction
            rows_parsed += 1
            occurred_on = _parse_date(row[mapping.date_column])
            amount = extract_amount(mapping, row)
            description = row[mapping.description_column]
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
            if not r.is_exact_duplicate and r.resolution != "skip"
        ]

        categories = self._categories.list_for_user(user_id=user_id)
        transactions = [
            self._build_transaction(
                row, batch=batch, user_id=user_id, categories=categories
            )
            for row in importable
        ]
        self._transactions.add_all(transactions)
        self._detect_transfers(transactions)
        self._session.flush()
        RecurrenceService(self._session).apply(user_id=user_id)

        self._batches.clear_staged(batch_id)
        batch.rows_imported = len(transactions)
        batch.status = ImportStatus.COMMITTED
        self._session.commit()

        return ImportSummary(
            batch_id=batch.id,
            status=batch.status,
            rows_parsed=batch.rows_parsed,
            rows_imported=batch.rows_imported,
            rows_skipped_duplicate=batch.rows_skipped_duplicate,
            rows_pending_conflict=0,
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
        self._session.commit()
        return len(undone)

    def _build_transaction(
        self,
        row: StagedTransaction,
        *,
        batch: ImportBatch,
        user_id: UUID,
        categories: list[Category],
    ) -> Transaction:
        category = _categorise(row.normalised_description, categories)
        return Transaction(
            user_id=user_id,
            account_id=batch.account_id,
            category_id=category.id if category else None,
            occurred_on=row.occurred_on,
            amount=row.amount,
            description=row.description,
            normalised_description=row.normalised_description,
            direction=Direction.CREDIT if row.amount >= 0 else Direction.DEBIT,
            category_confidence=Decimal("0.500000") if category else None,
            category_set_by_user=False,
            import_batch_id=batch.id,
            fingerprint=row.fingerprint,
        )

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
            similarity = SequenceMatcher(
                None, candidate.normalised_description, normalised
            ).ratio()
            if similarity >= PROBABLE_MATCH_THRESHOLD:
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

def _categorise(
    normalised_description: str, categories: list[Category]
) -> Category | None:
    for category in categories:
        if category.name.lower() in normalised_description:
            return category
    return next((c for c in categories if c.kind == CategoryKind.DISCRETIONARY), None)


def _parse_date(raw: str) -> date:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d %b %y"):
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
    raise ValidationError(f"Unrecognised date format: {raw!r}")
