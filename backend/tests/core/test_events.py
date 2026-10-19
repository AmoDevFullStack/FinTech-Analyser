"""The outbox and its dispatcher. See app/core/events.py.

The registry tests need no database: they assert over what the decorators built, which is
where a handler silently failing to register would show up.
"""

from __future__ import annotations

import pytest

from app.core.auth import hash_password
from app.core.events import (
    IMPORT_COMMITTED,
    IMPORT_UNDONE,
    MAX_ATTEMPTS,
    TRANSACTION_CREATED,
    TRANSACTIONS_RECLASSIFIED,
    dispatch_pending,
    handles,
    handlers_for,
    record,
    registered_events,
    unregister,
)
from app.models.domain_event import DomainEvent
from app.models.user import User
from app.repositories.domain_event import DomainEventRepository
from app.services.event_handlers import LEDGER_CHANGED


def _make_user(session, email: str = "events@example.com") -> User:
    user = User(email=email, password_hash=hash_password("x"), full_name="Test User")
    session.add(user)
    session.flush()
    return user


@pytest.fixture()
def register_handler():
    """Register a handler for the duration of one test and take it off afterwards.

    The registry is process-wide, so a handler left behind would run during every later
    test's dispatch.
    """
    registered: list[str] = []

    def _register(name: str, handler):
        handles(name)(handler)
        registered.append(name)

    yield _register

    for name in registered:
        unregister(name)


# ---------------------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------------------
def test_every_ledger_event_has_the_same_handlers():
    """The point of the outbox: one list of what a material change recomputes.

    Before it, an import commit and a manual entry ran different subsets from different
    places. If these four ever diverge again, it is a decision someone has to make on
    purpose rather than a side effect of editing one call site.
    """
    expected = [handler.__name__ for handler in handlers_for(IMPORT_COMMITTED)]
    assert expected, "no handlers registered for import.committed"

    for name in LEDGER_CHANGED:
        assert [handler.__name__ for handler in handlers_for(name)] == expected


def test_the_recorded_event_names_are_the_ones_with_handlers():
    """A name recorded by a service but registered by nobody is a silent no-op."""
    recorded = {
        IMPORT_COMMITTED,
        IMPORT_UNDONE,
        TRANSACTION_CREATED,
        TRANSACTIONS_RECLASSIFIED,
    }
    assert recorded <= set(registered_events())


def test_snapshot_is_captured_before_the_figures_computed_from_it():
    """Handlers run in registration order, and this one has to be first: the health score
    and the risk flags are read against the snapshot, so a snapshot taken after them would
    describe a position they were not computed from."""
    names = [handler.__name__ for handler in handlers_for(IMPORT_COMMITTED)]
    assert names[0] == "capture_position_snapshot"


# ---------------------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------------------
def test_recording_an_event_does_not_commit_it(session):
    """The event has to land with the work it describes, not before it."""
    user = _make_user(session)
    record(session, user_id=user.id, name="test.only", payload={"a": 1})
    session.rollback()

    assert DomainEventRepository(session).unprocessed_for_user(user_id=user.id) == []


def test_dispatch_marks_an_event_processed(session, register_handler):
    user = _make_user(session)
    session.commit()

    seen = []
    register_handler("test.dispatch", lambda _session, event: seen.append(event.id))

    recorded = record(session, user_id=user.id, name="test.dispatch")
    session.commit()

    report = dispatch_pending(session, user_id=user.id)

    assert report.processed == 1
    assert report.failed == 0
    assert seen == [recorded.id]
    assert session.get(DomainEvent, recorded.id).processed_at is not None


def test_a_processed_event_is_not_dispatched_twice(session, register_handler):
    user = _make_user(session)
    session.commit()

    calls = []
    register_handler("test.once", lambda _session, event: calls.append(event.id))

    record(session, user_id=user.id, name="test.once")
    session.commit()

    dispatch_pending(session, user_id=user.id)
    dispatch_pending(session, user_id=user.id)

    assert len(calls) == 1


def test_a_failing_handler_does_not_raise_and_is_recorded(session, register_handler):
    """A handler failing must not take down the request whose work already committed —
    but it must be visible afterwards, which is what `attempts` and `last_error` are for.
    """
    user = _make_user(session)
    session.commit()

    def explode(_session, _event):
        raise RuntimeError("handler is broken")

    register_handler("test.failure", explode)

    recorded = record(session, user_id=user.id, name="test.failure")
    session.commit()
    event_id = recorded.id

    report = dispatch_pending(session, user_id=user.id)

    assert report.failed == 1
    assert report.processed == 0

    stored = session.get(DomainEvent, event_id)
    assert stored.processed_at is None, "a failed event stays pending so it can be retried"
    assert stored.attempts == 1
    assert "handler is broken" in stored.last_error


def test_an_event_stops_being_retried_after_max_attempts(session):
    user = _make_user(session)
    event = record(session, user_id=user.id, name="test.exhausted")
    event.attempts = MAX_ATTEMPTS
    session.commit()

    report = dispatch_pending(session, user_id=user.id)

    assert report.total == 0
    assert DomainEventRepository(session).failed(max_attempts=MAX_ATTEMPTS) != []


def test_dispatch_is_scoped_to_one_user(session, register_handler):
    """Dispatch runs inside one user's request; it must not do another user's work there."""
    mine = _make_user(session, "mine@example.com")
    theirs = _make_user(session, "theirs@example.com")
    session.commit()

    handled = []
    register_handler("test.scope", lambda _session, event: handled.append(event.user_id))

    record(session, user_id=mine.id, name="test.scope")
    record(session, user_id=theirs.id, name="test.scope")
    session.commit()

    dispatch_pending(session, user_id=mine.id)

    assert handled == [mine.id]
