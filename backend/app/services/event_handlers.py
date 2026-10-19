"""What recomputes after a material change, in one place.

Before this module the answer was spread across three call sites and differed at each:
committing an import recalculated the health score from the API route and marked the
forecast stale from the service; entering one transaction by hand also captured a position
snapshot; neither evaluated risk, although specs/risk-detection.md says risk is evaluated
"after each import". None of that was a decision — it was the order the features were
written in.

Every handler here is idempotent: each recomputes a value from current state rather than
applying a delta, so a retried event produces the same figures. That property is what makes
`dispatch_pending`'s retry safe, and a handler that does not have it does not belong here.

Handlers call the worker entry points in app/workers/, which call the same services the API
calls — there is never a second implementation of a calculation (docs/architecture.md §3.5).
"""

from __future__ import annotations

from app.core.db import DbSession
from app.core.events import (
    IMPORT_COMMITTED,
    IMPORT_UNDONE,
    TRANSACTION_CREATED,
    TRANSACTIONS_RECLASSIFIED,
    handles,
)
from app.models.domain_event import DomainEvent
from app.services.forecast import ForecastService
from app.services.position import PositionService
from app.workers.financial_health import assess_financial_health
from app.workers.risk import evaluate_risk

# Every event that means "this user's transactions changed". They all recompute the same
# things, because the figures do not care which path moved them.
LEDGER_CHANGED = (
    IMPORT_COMMITTED,
    IMPORT_UNDONE,
    TRANSACTION_CREATED,
    TRANSACTIONS_RECLASSIFIED,
)


def _for_ledger_changes(handler):
    for name in LEDGER_CHANGED:
        handles(name)(handler)
    return handler


@_for_ledger_changes
def capture_position_snapshot(session: DbSession, event: DomainEvent) -> None:
    """Freeze the position the changed ledger now implies.

    First, because the forecast and the health assessment below are read against a
    snapshot: computing them from one taken before the change would date them immediately.
    """
    PositionService(session).capture_snapshot(user_id=event.user_id)


@_for_ledger_changes
def assess_health(session: DbSession, event: DomainEvent) -> None:
    """specs/financial-health.md: computed on a schedule and on material change. This is
    the "material change" half, now for every path that is one."""
    assess_financial_health(session, user_id=event.user_id)


@_for_ledger_changes
def mark_forecast_stale(session: DbSession, event: DomainEvent) -> None:
    """specs/forecasting.md: marking stale is enough — regeneration is queued, not
    immediate. A changed ledger invalidates every baseline the projection rests on."""
    ForecastService(session).mark_stale(user_id=event.user_id)


@_for_ledger_changes
def evaluate_risk_flags(session: DbSession, event: DomainEvent) -> None:
    """specs/risk-detection.md: evaluated after each import. It was not, before this —
    the import path simply never called it."""
    evaluate_risk(session, user_id=event.user_id)
