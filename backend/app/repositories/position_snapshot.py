from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from app.core.db import DbSession

from app.models.position_snapshot import PositionSnapshot


class PositionSnapshotRepository:
    def __init__(self, session: DbSession) -> None:
        self._session = session

    def latest_for_user(self, *, user_id: UUID) -> PositionSnapshot | None:
        stmt = (
            select(PositionSnapshot)
            .where(PositionSnapshot.user_id == user_id)
            .order_by(PositionSnapshot.captured_at.desc())
        )
        return self._session.scalars(stmt).first()

    def get_for_user(self, snapshot_id: UUID, *, user_id: UUID) -> PositionSnapshot | None:
        stmt = select(PositionSnapshot).where(
            PositionSnapshot.id == snapshot_id, PositionSnapshot.user_id == user_id
        )
        return self._session.scalars(stmt).first()

    def add(self, snapshot: PositionSnapshot) -> PositionSnapshot:
        self._session.add(snapshot)
        self._session.flush()
        return snapshot
