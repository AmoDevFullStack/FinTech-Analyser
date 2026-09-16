from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, text

from app.core.db import DbSession
from app.models.risk_flag import RiskFlag, RiskStatus

_LIST_FOR_USER = text(
    """
    SELECT *
      FROM risk_flags
     WHERE user_id = :user_id
       AND (
         CAST(:status AS risk_status_enum) IS NULL
         OR status = CAST(:status AS risk_status_enum)
       )
     ORDER BY detected_on DESC
    """
)

_LATEST_OF_TYPE = text(
    """
    SELECT *
      FROM risk_flags
     WHERE user_id = :user_id
       AND risk_type = :risk_type
     ORDER BY detected_on DESC, created_at DESC
    """
)

_GET_FOR_USER = text(
    """
    SELECT *
      FROM risk_flags
     WHERE id = :flag_id
       AND user_id = :user_id
    """
)


class RiskFlagRepository:
    """Every method takes `user_id` and filters on it — see docs/architecture.md §3.4."""

    def __init__(self, session: DbSession) -> None:
        self._session = session

    def list_for_user(
        self, *, user_id: UUID, status: RiskStatus | None = RiskStatus.ACTIVE
    ) -> list[RiskFlag]:
        return list(
            self._session.scalars(
                select(RiskFlag).from_statement(_LIST_FOR_USER),
                {"user_id": user_id, "status": status.value if status is not None else None},
            )
        )

    def latest_of_type(self, *, user_id: UUID, risk_type: str) -> RiskFlag | None:
        """The most recent flag of a type in any status.

        Deduplication and suppression both need the last flag of a type regardless of
        status: an active one is updated rather than duplicated, and a dismissed one
        suppresses for 30 days.
        """
        return self._session.scalars(
            select(RiskFlag).from_statement(_LATEST_OF_TYPE),
            {"user_id": user_id, "risk_type": risk_type},
        ).first()

    def get_for_user(self, flag_id: UUID, *, user_id: UUID) -> RiskFlag | None:
        return self._session.scalars(
            select(RiskFlag).from_statement(_GET_FOR_USER),
            {"flag_id": flag_id, "user_id": user_id},
        ).first()

    def add(self, flag: RiskFlag) -> RiskFlag:
        self._session.add(flag)
        self._session.flush()
        return flag

    def count_active(self, *, user_id: UUID) -> int:
        return len(self.list_for_user(user_id=user_id, status=RiskStatus.ACTIVE))
