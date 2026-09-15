from decimal import Decimal

from flask import Blueprint, g, jsonify, request

from app.core.auth import require_auth
from app.core.errors import NotFoundError
from app.core.extensions import db
from app.domain.forecast import ForecastAssumptions
from app.models.forecast import Forecast, ForecastPeriod
from app.services.forecast import ForecastService
from app.workers.forecast import generate_forecast

bp = Blueprint("forecasts", __name__, url_prefix="/forecasts")


def _period_dict(period: ForecastPeriod) -> dict:
    return {
        "period_index": period.period_index,
        "month": period.month,
        "projected_income": str(period.projected_income),
        "projected_expenses": str(period.projected_expenses),
        "cash_flow": str(period.cash_flow),
        "savings_balance": str(period.savings_balance),
        "debt_balance": str(period.debt_balance),
        "emergency_fund_months": str(period.emergency_fund_months),
        "net_worth": str(period.net_worth),
    }


def _forecast_dict(forecast: Forecast, periods: list[ForecastPeriod]) -> dict:
    """Always carries `generated_at` and `is_stale`, per docs/api.md — a forecast whose
    age the client cannot see is a forecast the client will present as current.
    """
    assumptions = forecast.assumptions or {}
    return {
        "id": str(forecast.id),
        "horizon_months": forecast.horizon_months,
        "generated_at": forecast.generated_at.isoformat(),
        "is_stale": forecast.is_stale,
        "engine_version": forecast.engine_version,
        "input_snapshot_id": str(forecast.input_snapshot_id),
        "assumptions": assumptions,
        "is_low_confidence": assumptions.get("is_low_confidence") == "true",
        "months_observed": int(assumptions.get("months_observed", 0)),
        "periods": [_period_dict(p) for p in periods],
    }


@bp.get("/current")
@require_auth
def get_current_forecast():
    """Reads stored results only — never computes. See ADR-003."""
    view = ForecastService(db.session).current(user_id=g.user_id)
    if view is None:
        return jsonify({"forecast": None, "is_stale": True}), 200
    return jsonify(_forecast_dict(view.forecast, view.periods)), 200


@bp.get("/accuracy")
@require_auth
def get_accuracy():
    """Prior projections against realised actuals — the feedback loop in requirement 6."""
    service = ForecastService(db.session)
    rows = service.accuracy_history(user_id=g.user_id)
    summaries = service.accuracy_summaries(user_id=g.user_id)
    return (
        jsonify(
            {
                "measurements": [
                    {
                        "month": row.month,
                        "metric": row.metric,
                        "projected": str(row.projected),
                        "actual": str(row.actual),
                        "absolute_error": str(row.absolute_error),
                        "signed_error": str(row.signed_error),
                        "percentage_error": (
                            str(row.percentage_error)
                            if row.percentage_error is not None
                            else None
                        ),
                        "engine_version": row.engine_version,
                    }
                    for row in rows
                ],
                "summaries": [
                    {
                        "metric": s.metric.value,
                        "months_measured": s.months_measured,
                        "mean_absolute_error": str(s.mean_absolute_error),
                        "mean_percentage_error": (
                            str(s.mean_percentage_error)
                            if s.mean_percentage_error is not None
                            else None
                        ),
                        "has_persistent_bias": s.has_persistent_bias,
                        "bias_direction": s.bias_direction,
                        "suggested_adjustment": str(s.suggested_adjustment),
                    }
                    for s in summaries
                ],
            }
        ),
        200,
    )


@bp.post("/refresh")
@require_auth
def refresh_forecast():
    """Regenerates synchronously in this build and returns the forecast.

    docs/api.md specifies 202 with a queued job. There is no queue worker running in the
    development stack, so this returns 201 with the finished forecast instead of a job
    identifier the client could never resolve. The computation itself is the same worker
    entry point a queue would call.
    """
    body = request.get_json(force=True, silent=True) or {}
    assumptions = ForecastAssumptions(
        inflation_annual=Decimal(str(body.get("inflation_annual", "0.05"))),
        salary_growth_annual=Decimal(str(body.get("salary_growth_annual", "0.05"))),
        horizon_months=int(body.get("horizon_months", 60)),
    )
    forecast = generate_forecast(db.session, user_id=g.user_id, assumptions=assumptions)
    view = ForecastService(db.session).current(user_id=g.user_id)
    assert view is not None
    return jsonify(_forecast_dict(forecast, view.periods)), 201


@bp.get("/<uuid:forecast_id>")
@require_auth
def get_forecast(forecast_id):
    service = ForecastService(db.session)
    view = service.current(user_id=g.user_id)
    if view is None or view.forecast.id != forecast_id:
        raise NotFoundError("No forecast with that identifier exists for this user.")
    return jsonify(_forecast_dict(view.forecast, view.periods)), 200
