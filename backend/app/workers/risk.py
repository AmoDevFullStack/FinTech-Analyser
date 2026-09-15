"""Risk evaluation worker. See specs/risk-detection.md: "Evaluated by a worker after each
forecast regeneration and after each import."

A thin entry point calling the same service the API calls — there is never a second,
worker-only implementation of a calculation (docs/architecture.md §3.5).
"""

from __future__ import annotations

from uuid import UUID

from app.core.db import DbSession
from app.models.risk_flag import RiskFlag
from app.services.risk import RiskService


def evaluate_risk(session: DbSession, *, user_id: UUID) -> list[RiskFlag]:
    return RiskService(session).evaluate(user_id=user_id)
