from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, text

from app.core.db import DbSession

from app.models.position_snapshot import PositionSnapshot

_LATEST_FOR_USER = text(
    """
    SELECT *
      FROM position_snapshots
     WHERE user_id = :user_id
     ORDER BY captured_at DESC
    """
)

_GET_FOR_USER = text(
    """
    SELECT *
      FROM position_snapshots
     WHERE id = :snapshot_id
       AND user_id = :user_id
    """
)


class PositionSnapshotRepository:
    def __init__(self, session: DbSession) -> None:
        self._session = session

    def latest_for_user(self, *, user_id: UUID) -> PositionSnapshot | None:
        return self._session.scalars(
            select(PositionSnapshot).from_statement(_LATEST_FOR_USER), {"user_id": user_id}
        ).first()

    def get_for_user(self, snapshot_id: UUID, *, user_id: UUID) -> PositionSnapshot | None:
        return self._session.scalars(
            select(PositionSnapshot).from_statement(_GET_FOR_USER),
            {"snapshot_id": snapshot_id, "user_id": user_id},
        ).first()

    def add(self, snapshot: PositionSnapshot) -> PositionSnapshot:
        self._session.add(snapshot)
        self._session.flush()
        return snapshot
