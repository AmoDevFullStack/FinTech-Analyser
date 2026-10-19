from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class PositionSnapshot(UUIDPrimaryKeyMixin, Base):
    """A frozen, immutable copy of the user's computed position. See docs/database.md §4.

    No TimestampMixin: a snapshot is never updated after creation, only `captured_at`
    matters, and it is never queried across users.
    """

    __tablename__ = "position_snapshots"
    __table_args__ = {"schema": "analytics"}

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=False, index=True
    )
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    net_worth: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    monthly_income: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    monthly_essential: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    monthly_discretionary: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    total_debt: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    liquid_savings: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    position: Mapped[dict] = mapped_column(JSONB, nullable=False)
