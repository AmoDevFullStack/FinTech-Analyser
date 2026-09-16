from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, text

from app.core.db import DbSession

from app.models.forecast import Forecast, ForecastPeriod

_LATEST_FOR_USER = text(
    """
    SELECT *
      FROM forecasts
     WHERE user_id = :user_id
     ORDER BY generated_at DESC
    """
)

_DELETE_PERIODS = text(
    """
    DELETE FROM forecast_periods
     WHERE forecast_id = :forecast_id
    """
)

_PERIODS_FOR = text(
    """
    SELECT *
      FROM forecast_periods
     WHERE forecast_id = :forecast_id
     ORDER BY period_index
    """
)


class ForecastRepository:
    def __init__(self, session: DbSession) -> None:
        self._session = session

    def latest_for_user(self, *, user_id: UUID) -> Forecast | None:
        return self._session.scalars(
            select(Forecast).from_statement(_LATEST_FOR_USER), {"user_id": user_id}
        ).first()

    def replace_for_user(
        self, *, user_id: UUID, forecast: Forecast, periods: list[ForecastPeriod]
    ) -> Forecast:
        """Jobs are idempotent: re-running a forecast replaces the prior result rather
        than appending, per docs/architecture.md §3.5.
        """
        existing = self.latest_for_user(user_id=user_id)
        if existing is not None:
            self._session.execute(_DELETE_PERIODS, {"forecast_id": existing.id})
            self._session.delete(existing)
            self._session.flush()

        self._session.add(forecast)
        self._session.flush()
        for period in periods:
            period.forecast_id = forecast.id
        self._session.add_all(periods)
        self._session.flush()
        return forecast

    def periods_for(self, forecast_id: UUID) -> list[ForecastPeriod]:
        return list(
            self._session.scalars(
                select(ForecastPeriod).from_statement(_PERIODS_FOR),
                {"forecast_id": forecast_id},
            )
        )
