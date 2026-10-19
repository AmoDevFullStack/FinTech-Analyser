from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, text

from app.core.db import DbSession
from app.models.domain_event import DomainEvent

# `FOR UPDATE SKIP LOCKED` so two dispatchers — two web workers, or a request and the
# drain command — never run the same handler twice: whichever gets the row first holds it,
# and the other moves past it rather than blocking on it.
_CLAIM_PENDING = text(
    """
    SELECT *
      FROM audit.events
     WHERE processed_at IS NULL
       AND attempts < :max_attempts
       AND (CAST(:user_id AS uuid) IS NULL OR user_id = CAST(:user_id AS uuid))
     ORDER BY occurred_at, created_at
     LIMIT :limit
       FOR UPDATE SKIP LOCKED
    """
)

_UNPROCESSED_FOR_USER = text(
    """
    SELECT *
      FROM audit.events
     WHERE user_id = :user_id
       AND processed_at IS NULL
     ORDER BY occurred_at
    """
)

_FAILED = text(
    """
    SELECT *
      FROM audit.events
     WHERE processed_at IS NULL
       AND attempts >= :max_attempts
     ORDER BY occurred_at
    """
)


class DomainEventRepository:
    """Every read takes `user_id` except the two operational ones, which exist to answer
    "what has not run yet, across everyone" — see docs/architecture.md §3.4.
    """

    def __init__(self, session: DbSession) -> None:
        self._session = session

    def add(self, *, user_id: UUID, name: str, payload: dict) -> DomainEvent:
        event = DomainEvent(
            user_id=user_id,
            name=name,
            payload=payload,
            occurred_at=datetime.now(timezone.utc),
        )
        self._session.add(event)
        return event

    def claim_pending(
        self, *, user_id: UUID | None, limit: int, max_attempts: int
    ) -> list[DomainEvent]:
        return list(
            self._session.scalars(
                select(DomainEvent).from_statement(_CLAIM_PENDING),
                {"user_id": user_id, "limit": limit, "max_attempts": max_attempts},
            )
        )

    def unprocessed_for_user(self, *, user_id: UUID) -> list[DomainEvent]:
        return list(
            self._session.scalars(
                select(DomainEvent).from_statement(_UNPROCESSED_FOR_USER),
                {"user_id": user_id},
            )
        )

    def failed(self, *, max_attempts: int) -> list[DomainEvent]:
        return list(
            self._session.scalars(
                select(DomainEvent).from_statement(_FAILED),
                {"max_attempts": max_attempts},
            )
        )

    def get(self, event_id: UUID) -> DomainEvent | None:
        return self._session.get(DomainEvent, event_id)
