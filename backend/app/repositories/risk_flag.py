from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.core.db import DbSession
from app.models.risk_flag import RiskFlag, RiskStatus


class RiskFlagRepository:
    """Every method takes `user_id` and filters on it — see docs/architecture.md §3.4."""

    def __init__(self, session: DbSession) -> None:
        self._session = session

    def list_for_user(
        self, *, user_id: UUID, status: RiskStatus | None = RiskStatus.ACTIVE
    ) -> list[RiskFlag]:
        stmt = select(RiskFlag).where(RiskFlag.user_id == user_id)
        if status is not None:
            stmt = stmt.where(RiskFlag.status == status)
        stmt = stmt.order_by(RiskFlag.detected_on.desc())
        return list(self._session.scalars(stmt))

    def latest_of_type(self, *, user_id: UUID, risk_type: str) -> RiskFlag | None:
        """The most recent flag of a type in any status.

        Deduplication and suppression both need the last flag of a type regardless of
        status: an active one is updated rather than duplicated, and a dismissed one
        suppresses for 30 days.
        """
        stmt = (
            select(RiskFlag)
            .where(RiskFlag.user_id == user_id, RiskFlag.risk_type == risk_type)
            .order_by(RiskFlag.detected_on.desc(), RiskFlag.created_at.desc())
        )
        return self._session.scalars(stmt).first()

    def get_for_user(self, flag_id: UUID, *, user_id: UUID) -> RiskFlag | None:
        stmt = select(RiskFlag).where(RiskFlag.id == flag_id, RiskFlag.user_id == user_id)
        return self._session.scalars(stmt).first()

    def add(self, flag: RiskFlag) -> RiskFlag:
        self._session.add(flag)
        self._session.flush()
        return flag

    def count_active(self, *, user_id: UUID) -> int:
        return len(self.list_for_user(user_id=user_id, status=RiskStatus.ACTIVE))
