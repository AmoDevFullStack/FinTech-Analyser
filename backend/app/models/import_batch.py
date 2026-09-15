from __future__ import annotations

import enum
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Date, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, pg_enum


class ImportStatus(str, enum.Enum):
    STAGED = "staged"
    AWAITING_RESOLUTION = "awaiting_resolution"
    COMMITTED = "committed"
    UNDONE = "undone"
    FAILED = "failed"


class ImportBatch(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Tracks one CSV upload through staging, commit, and undo. See specs/transactions.md."""

    __tablename__ = "import_batches"

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    account_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False
    )
    status: Mapped[ImportStatus] = mapped_column(
        pg_enum(ImportStatus, name="import_status_enum"), nullable=False
    )
    detected_format: Mapped[str | None] = mapped_column(String, nullable=True)
    rows_parsed: Mapped[int] = mapped_column(nullable=False, default=0)
    rows_imported: Mapped[int] = mapped_column(nullable=False, default=0)
    rows_skipped_duplicate: Mapped[int] = mapped_column(nullable=False, default=0)
    rows_pending_conflict: Mapped[int] = mapped_column(nullable=False, default=0)
    rows_merged: Mapped[int] = mapped_column(nullable=False, default=0)


class StagedTransaction(UUIDPrimaryKeyMixin, Base):
    """Nothing here has reached `transactions` yet — see specs/transactions.md step 7.

    No `TimestampMixin`: staging rows are transient and are purged on commit or undo,
    so an updated_at trigger would be pure overhead.
    """

    __tablename__ = "staged_transactions"

    import_batch_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("import_batches.id"), nullable=False, index=True
    )
    occurred_on: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    normalised_description: Mapped[str] = mapped_column(String, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String, nullable=False, index=True)
    is_exact_duplicate: Mapped[bool] = mapped_column(nullable=False, default=False)
    conflict_candidate_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("transactions.id"), nullable=True
    )
    resolution: Mapped[str | None] = mapped_column(String, nullable=True)
    raw_row: Mapped[dict] = mapped_column(JSONB, nullable=False)
