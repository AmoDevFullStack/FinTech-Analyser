from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AssistantConversation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A question thread. See specs/ai-cfo.md and docs/api.md's assistant section."""

    __tablename__ = "assistant_conversations"

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)


class AssistantMessage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One question and its answer.

    `answer` holds the prose shown to the reader and `figures` holds the computed figures
    that prose was written over — for a capability with no figures (a greeting), it may
    instead be the deterministic fallback line. `narration_available` says which one it
    is, so the client never has to guess from `answer`'s presence alone. Both are
    transcript columns on a conversation table: no financial table has a column populated
    from model output, which is the invariant tests/services/test_assistant_boundary.py
    asserts and ADR-002 requires.
    """

    __tablename__ = "assistant_messages"

    conversation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("assistant_conversations.id"), nullable=False, index=True
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    asked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    question: Mapped[str] = mapped_column(String, nullable=False)
    answer: Mapped[str | None] = mapped_column(String, nullable=True)
    capability: Mapped[str] = mapped_column(String, nullable=False)
    supported: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    narration_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    figures: Mapped[list] = mapped_column(JSONB, nullable=False)
