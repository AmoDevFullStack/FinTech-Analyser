from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class DomainEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Something that happened, written in the same transaction as the thing itself.

    This is a transactional outbox, not a message queue. The row is inserted by the
    service that did the work, inside that service's transaction, so a committed import
    and the record that it was committed cannot disagree: either both are there or
    neither is. Handlers then run afterwards, from the row, rather than being called
    inline by whoever happened to be holding the request.

    Why it exists: before this table, a committed import recomputed the financial health
    score in the API route, marked the forecast stale in the service, and never evaluated
    risk at all — while a manually entered transaction did a fourth, different subset from
    a third place. The list of what a material change triggers now lives in one file
    (app/services/event_handlers.py) rather than being distributed across whichever call
    site was edited most recently.

    `processed_at IS NULL` means the work still has to happen; a row is never deleted, so
    "what recomputed, and when" is answerable after the fact. See docs/architecture.md.
    """

    __tablename__ = "events"
    __table_args__ = {"schema": "audit"}

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Bounded retry. A handler that fails for a reason that will not go away — a bug, not
    # a lost connection — must not be retried forever on every subsequent request, and the
    # count is what makes that visible rather than silent.
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(String, nullable=True)
