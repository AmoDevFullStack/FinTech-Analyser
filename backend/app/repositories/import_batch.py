from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, text

from app.core.db import DbSession

from app.models.import_batch import ImportBatch, StagedTransaction

_GET_FOR_USER = text(
    """
    SELECT *
      FROM ledger.import_batches
     WHERE id = :batch_id
       AND user_id = :user_id
    """
)

_STAGED_FOR = text(
    """
    SELECT *
      FROM ledger.staged_transactions
     WHERE import_batch_id = :batch_id
    """
)

_CLEAR_STAGED = text(
    """
    DELETE FROM ledger.staged_transactions
     WHERE import_batch_id = :batch_id
    """
)


class ImportBatchRepository:
    def __init__(self, session: DbSession) -> None:
        self._session = session

    def get_for_user(self, batch_id: UUID, *, user_id: UUID) -> ImportBatch | None:
        return self._session.scalars(
            select(ImportBatch).from_statement(_GET_FOR_USER),
            {"batch_id": batch_id, "user_id": user_id},
        ).first()

    def add(self, batch: ImportBatch) -> ImportBatch:
        self._session.add(batch)
        self._session.flush()
        return batch

    def add_staged(self, rows: list[StagedTransaction]) -> None:
        self._session.add_all(rows)
        self._session.flush()

    def staged_for(self, batch_id: UUID) -> list[StagedTransaction]:
        return list(
            self._session.scalars(
                select(StagedTransaction).from_statement(_STAGED_FOR), {"batch_id": batch_id}
            )
        )

    def clear_staged(self, batch_id: UUID) -> None:
        self._session.execute(_CLEAR_STAGED, {"batch_id": batch_id})
        self._session.flush()
