"""Domain events: what happened, and what has to be recomputed because of it.

The problem this solves is not throughput. It is that "a material change happened" had no
single meaning in this codebase: committing an import recomputed the health score from the
API route, marked the forecast stale from the service, and never evaluated risk, while
entering one transaction by hand did a different three things from a third place. Every
new downstream calculation meant editing every call site, and forgetting one was silent.

A service now records one event — `import.committed`, `transaction.created` — inside the
transaction that did the work, and the handlers registered for that event decide what
recomputes. Adding a calculation is one registration in app/services/event_handlers.py.

This is deliberately in-process. There is no broker and no worker: `dispatch_pending` runs
the handlers on the same connection, right after the service commits. What makes that
upgradeable rather than a shortcut is that the event is a committed row before any handler
runs, so moving dispatch into a separate process later changes where `dispatch_pending` is
called from and nothing else.

Handlers must be idempotent. Every one of them recomputes a value from current state
rather than applying a delta, so running one twice produces the same figures — which is
what makes retrying a failed event safe.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from app.core.db import DbSession
from app.models.domain_event import DomainEvent
from app.repositories.domain_event import DomainEventRepository

logger = logging.getLogger(__name__)

# Event names. Past tense, `subject.verb`, and named after what happened rather than after
# what should follow — `import.committed`, never `import.recalculate_everything`. A handler
# decides what follows; an event only reports.
IMPORT_COMMITTED = "import.committed"
IMPORT_UNDONE = "import.undone"
TRANSACTION_CREATED = "transaction.created"
TRANSACTIONS_RECLASSIFIED = "transactions.reclassified"

#: How many times a failing event is retried before it is left alone. A handler that fails
#: because of a bug fails identically every time, and retrying it on every subsequent
#: request would turn one broken event into an unbounded cost. `flask events failed` lists
#: what stopped here.
MAX_ATTEMPTS = 5

#: How many events one dispatch pass claims. A pass runs inside a user's request, so it is
#: bounded on purpose: the backlog drains over several requests rather than one request
#: paying for all of it.
DISPATCH_LIMIT = 25

Handler = Callable[[DbSession, DomainEvent], None]

_HANDLERS: dict[str, list[Handler]] = {}


def handles(name: str) -> Callable[[Handler], Handler]:
    """Register a handler for an event name. Handlers run in registration order."""

    def register(handler: Handler) -> Handler:
        _HANDLERS.setdefault(name, []).append(handler)
        return handler

    return register


def unregister(name: str) -> None:
    """Drop every handler for an event name.

    The counterpart to `handles`, so a caller that registers one can take it back off
    again — tests register a handler they then have to remove, and leaving it in a
    process-wide registry would make the next test's dispatch run it too.
    """
    _HANDLERS.pop(name, None)


def handlers_for(name: str) -> tuple[Handler, ...]:
    return tuple(_HANDLERS.get(name, ()))


def registered_events() -> tuple[str, ...]:
    return tuple(sorted(_HANDLERS))


def record(session: DbSession, *, user_id: UUID, name: str, payload: dict | None = None) -> DomainEvent:
    """Write the event. The caller's transaction is what makes it true.

    Deliberately no commit and no flush here: the event has to land or not land with the
    work it describes, and committing it early would let a failed import leave behind a
    record that it succeeded.
    """
    return DomainEventRepository(session).add(
        user_id=user_id, name=name, payload=payload or {}
    )


@dataclass(frozen=True, slots=True)
class DispatchReport:
    """What one dispatch pass did. Returned rather than logged alone so a caller — a test,
    the CLI — can assert on it."""

    processed: int
    failed: int

    @property
    def total(self) -> int:
        return self.processed + self.failed


def dispatch_pending(
    session: DbSession,
    *,
    user_id: UUID | None = None,
    limit: int = DISPATCH_LIMIT,
) -> DispatchReport:
    """Run the handlers for events that have not been processed yet.

    Called after the recording service has committed, never before: a handler reads the
    state the event describes, and an uncommitted import is not that state.

    A failing handler does not fail the caller. The user's import succeeded — that is
    already committed and true — and taking their request down because a score could not be
    recalculated would be a worse answer than a stale score. The failure is recorded on the
    event with its error and its attempt count, logged at error level, and left unprocessed
    so the next pass retries it. It is not swallowed: `flask events failed` lists every
    event that exhausted MAX_ATTEMPTS.
    """
    repository = DomainEventRepository(session)
    claimed = repository.claim_pending(
        user_id=user_id, limit=limit, max_attempts=MAX_ATTEMPTS
    )

    processed = 0
    failed = 0
    for event in claimed:
        event_id = event.id
        name = event.name
        try:
            for handler in handlers_for(name):
                handler(session, event)
        except Exception as error:  # noqa: BLE001 - recorded on the row, see docstring
            session.rollback()
            logger.exception("Handler for domain event %s (%s) failed", name, event_id)
            stored = repository.get(event_id)
            if stored is not None:
                stored.attempts += 1
                stored.last_error = f"{type(error).__name__}: {error}"[:2000]
                session.commit()
            failed += 1
            continue

        stored = repository.get(event_id)
        if stored is not None:
            stored.processed_at = datetime.now(timezone.utc)
            stored.last_error = None
            session.commit()
        processed += 1

    return DispatchReport(processed=processed, failed=failed)
