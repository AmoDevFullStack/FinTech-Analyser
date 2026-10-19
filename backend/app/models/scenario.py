from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, pg_enum


class ScenarioType(str, enum.Enum):
    VEHICLE_PURCHASE = "vehicle_purchase"
    PROPERTY_PURCHASE = "property_purchase"
    INCOME_CHANGE = "income_change"
    NEW_LOAN = "new_loan"
    DEBT_REPAYMENT_CHANGE = "debt_repayment_change"
    SAVINGS_CHANGE = "savings_change"
    DISCRETIONARY_EXPENSE = "discretionary_expense"


class ScenarioStatus(str, enum.Enum):
    DRAFT = "draft"
    RUN = "run"


class Scenario(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """See ADR-005: never a foreign key from any real financial table to this table —
    the dependency runs one way only, from here to a PositionSnapshot.
    """

    __tablename__ = "scenarios"
    __table_args__ = {"schema": "analytics"}

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    scenario_type: Mapped[ScenarioType] = mapped_column(
        pg_enum(ScenarioType, name="scenario_type_enum"), nullable=False
    )
    snapshot_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("analytics.position_snapshots.id"), nullable=False
    )
    status: Mapped[ScenarioStatus] = mapped_column(
        pg_enum(ScenarioStatus, name="scenario_status_enum"), nullable=False
    )


class ScenarioAssumption(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "scenario_assumptions"
    __table_args__ = {"schema": "analytics"}

    scenario_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("analytics.scenarios.id"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[str] = mapped_column(String, nullable=False)


class ScenarioResult(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "scenario_results"
    __table_args__ = {"schema": "analytics"}

    scenario_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("analytics.scenarios.id"), nullable=False, index=True
    )
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    engine_version: Mapped[str] = mapped_column(String, nullable=False)
    assumptions_hash: Mapped[str] = mapped_column(String, nullable=False)
    impact: Mapped[dict] = mapped_column(JSONB, nullable=False)
    periods: Mapped[list] = mapped_column(JSONB, nullable=False)
    baseline_periods: Mapped[list] = mapped_column(JSONB, nullable=False)
