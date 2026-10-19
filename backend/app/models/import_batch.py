from __future__ import annotations

import enum
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Date, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.payment_taxonomy import PaymentMethod, SpendingPurpose
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, pg_enum
from app.models.enums import PAYMENT_METHOD_ENUM, SPENDING_PURPOSE_ENUM


class ImportStatus(str, enum.Enum):
    STAGED = "staged"
    AWAITING_RESOLUTION = "awaiting_resolution"
    COMMITTED = "committed"
    UNDONE = "undone"
    FAILED = "failed"


class ImportBatch(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Tracks one CSV upload through staging, commit, and undo. See specs/transactions.md."""

    __tablename__ = "import_batches"
    __table_args__ = {"schema": "ledger"}

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=False, index=True
    )
    account_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ledger.accounts.id"), nullable=False
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
    __table_args__ = {"schema": "ledger"}

    import_batch_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ledger.import_batches.id"), nullable=False, index=True
    )
    occurred_on: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    normalised_description: Mapped[str] = mapped_column(String, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String, nullable=False, index=True)
    is_exact_duplicate: Mapped[bool] = mapped_column(nullable=False, default=False)
    conflict_candidate_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ledger.transactions.id"), nullable=True
    )
    resolution: Mapped[str | None] = mapped_column(String, nullable=True)
    # Detection runs at staging, not at commit, so the impact preview the user approves is
    # computed from the same classification the committed rows will carry. Classifying
    # twice would let the preview and the result disagree.
    payment_method: Mapped[PaymentMethod | None] = mapped_column(
        PAYMENT_METHOD_ENUM, nullable=True
    )
    spending_purpose: Mapped[SpendingPurpose | None] = mapped_column(
        SPENDING_PURPOSE_ENUM, nullable=True
    )
    merchant: Mapped[str | None] = mapped_column(String, nullable=True)
    purpose_confidence: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    raw_row: Mapped[dict] = mapped_column(JSONB, nullable=False)
