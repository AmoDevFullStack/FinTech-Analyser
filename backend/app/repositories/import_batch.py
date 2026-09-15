from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from app.core.db import DbSession

from app.models.import_batch import ImportBatch, StagedTransaction


class ImportBatchRepository:
    def __init__(self, session: DbSession) -> None:
        self._session = session

    def get_for_user(self, batch_id: UUID, *, user_id: UUID) -> ImportBatch | None:
        stmt = select(ImportBatch).where(
            ImportBatch.id == batch_id, ImportBatch.user_id == user_id
        )
        return self._session.scalars(stmt).first()

    def add(self, batch: ImportBatch) -> ImportBatch:
        self._session.add(batch)
        self._session.flush()
        return batch

    def add_staged(self, rows: list[StagedTransaction]) -> None:
        self._session.add_all(rows)
        self._session.flush()

    def staged_for(self, batch_id: UUID) -> list[StagedTransaction]:
        stmt = select(StagedTransaction).where(StagedTransaction.import_batch_id == batch_id)
        return list(self._session.scalars(stmt))

    def clear_staged(self, batch_id: UUID) -> None:
        self._session.execute(
            delete(StagedTransaction).where(StagedTransaction.import_batch_id == batch_id)
        )
        self._session.flush()
