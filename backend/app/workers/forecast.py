"""Forecast generation. See specs/forecasting.md and docs/architecture.md §3.5.

A thin entry point calling the same application-service path the API would — there is
never a second, worker-only implementation of a calculation. Idempotent: re-running for a
user replaces the prior forecast rather than appending, via ForecastRepository.

After regenerating, risk is re-evaluated, because specs/risk-detection.md requires
detection to run "after each forecast regeneration" and the detectors read the forecast
periods this job just wrote.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from app.core.db import DbSession
from app.domain.forecast import ForecastAssumptions
from app.models.forecast import Forecast
from app.services.forecast import ForecastService
from app.services.risk import RiskService


def generate_forecast(
    session: DbSession,
    *,
    user_id: UUID,
    as_of: date | None = None,
    assumptions: ForecastAssumptions | None = None,
    evaluate_risk: bool = True,
) -> Forecast:
    service = ForecastService(session)
    forecast = service.generate(user_id=user_id, as_of=as_of, assumptions=assumptions)
    service.measure_accuracy(user_id=user_id, as_of=as_of)
    if evaluate_risk:
        RiskService(session).evaluate(user_id=user_id, as_of=as_of)
    return forecast
