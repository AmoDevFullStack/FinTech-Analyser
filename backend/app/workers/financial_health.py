"""See docs/architecture.md §3.5 — a thin entry point calling the same service the API
would. Computed on a schedule and on material change, per specs/financial-health.md;
"on material change" (an import commit, a new debt) is wired at those call sites, not here.
"""

from __future__ import annotations

from uuid import UUID

from app.core.db import DbSession
from app.models.health_assessment import HealthAssessment
from app.services.financial_health import FinancialHealthService


def assess_financial_health(session: DbSession, *, user_id: UUID) -> HealthAssessment:
    """Score the current month, and re-score the months behind it.

    Both, not just the current month: an imported statement usually carries months that
    were already scored against transactions which had not arrived yet, and a series whose
    older points are stale is worse than no series. Returns the most recent month, which is
    what the caller shows.
    """
    assessed = FinancialHealthService(session).assess_recent(user_id=user_id)
    return assessed[-1]
