"""Forecast generation. See specs/forecasting.md and docs/architecture.md §3.5.

A thin entry point calling the same application-service path the API would — there is
never a second, worker-only implementation of a calculation. Idempotent: re-running for a
user replaces the prior forecast rather than appending, via ForecastRepository.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.core.db import DbSession
from app.domain.projection import project_forward
from app.models.forecast import Forecast, ForecastPeriod
from app.repositories.forecast import ForecastRepository
from app.services.position import PositionService

ENGINE_VERSION = "1.0.0"
HORIZON_MONTHS = 60


def generate_forecast(session: DbSession, *, user_id: UUID) -> Forecast:
    position_service = PositionService(session)
    snapshot = position_service.capture_snapshot(user_id=user_id)

    from app.domain.projection import FinancialPosition

    position = FinancialPosition(
        as_of=snapshot.captured_at.date(),
        liquid_savings=snapshot.liquid_savings,
        total_debt=snapshot.total_debt,
        net_worth=snapshot.net_worth,
        monthly_income=snapshot.monthly_income,
        monthly_essential=snapshot.monthly_essential,
        monthly_discretionary=snapshot.monthly_discretionary,
    )
    projected_periods = project_forward(position=position, horizon_months=HORIZON_MONTHS)

    forecast = Forecast(
        user_id=user_id,
        horizon_months=HORIZON_MONTHS,
        generated_at=datetime.now(UTC),
        input_snapshot_id=snapshot.id,
        assumptions={},
        engine_version=ENGINE_VERSION,
        is_stale=False,
    )
    period_rows = [
        ForecastPeriod(
            forecast_id=forecast.id,
            period_index=p.period,
            month=p.month,
            projected_income=position.monthly_income,
            projected_expenses=position.monthly_essential + position.monthly_discretionary,
            cash_flow=p.cash_flow,
            savings_balance=p.savings,
            debt_balance=p.debt,
            emergency_fund_months=_fund_months(p.savings, position.monthly_essential),
            net_worth=p.net_worth,
        )
        for p in projected_periods
    ]

    repo = ForecastRepository(session)
    repo.replace_for_user(user_id=user_id, forecast=forecast, periods=period_rows)
    session.commit()
    return forecast


def _fund_months(savings, monthly_essential):
    from app.domain.emergency_fund import emergency_fund_months

    return emergency_fund_months(
        liquid_savings=max(savings, savings.__class__("0")),
        monthly_essential_spending=monthly_essential,
    )
