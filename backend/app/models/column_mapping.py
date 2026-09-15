from __future__ import annotations

from uuid import UUID

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AccountColumnMapping(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A remembered manual column mapping for one account.

    specs/transactions.md: "Where detection fails, the user maps columns manually and the
    mapping is remembered for that account." One mapping per account — a re-map replaces
    it, since an account exports from one bank in one shape, and keeping a history of
    wrong guesses helps nobody.
    """

    __tablename__ = "account_column_mappings"
    __table_args__ = (UniqueConstraint("account_id", name="uq_account_column_mapping"),)

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    account_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False
    )
    mapping: Mapped[dict] = mapped_column(JSONB, nullable=False)
    label: Mapped[str | None] = mapped_column(String, nullable=True)
