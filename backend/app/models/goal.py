from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Goal(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """See docs/database.md §3 and specs/goals.md.

    `current_amount` is not stored as a running total maintained by application code —
    it is derived from `GoalContribution` rows, or from the linked account's balance
    movement where `account_id` is set. The column exists for the opening balance a user
    states when creating a goal ("I already have R12,000 towards this"), and the service
    adds evidenced movement to it. Per the spec, a goal with neither a linked account nor
    contributions shows that opening figure and no progress beyond it, never an estimate.
    """

    __tablename__ = "goals"
    __table_args__ = {"schema": "obligations"}

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=False, index=True
    )
    account_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ledger.accounts.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    target_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    current_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    target_date: Mapped[date] = mapped_column(Date, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    planned_monthly_contribution: Mapped[Decimal | None] = mapped_column(
        Numeric(15, 2), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GoalContribution(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An actual movement toward a goal — "progress is evidenced rather than asserted"
    (docs/database.md §3). A planned contribution is not one of these; only a recorded
    movement is.
    """

    __tablename__ = "goal_contributions"
    __table_args__ = {"schema": "obligations"}

    goal_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("obligations.goals.id"), nullable=False, index=True
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=False, index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    occurred_on: Mapped[date] = mapped_column(Date, nullable=False)
    note: Mapped[str | None] = mapped_column(String, nullable=True)
