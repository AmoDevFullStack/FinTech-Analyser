from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from app.core.db import DbSession

from app.models.forecast import Forecast, ForecastPeriod


class ForecastRepository:
    def __init__(self, session: DbSession) -> None:
        self._session = session

    def latest_for_user(self, *, user_id: UUID) -> Forecast | None:
        stmt = (
            select(Forecast)
            .where(Forecast.user_id == user_id)
            .order_by(Forecast.generated_at.desc())
        )
        return self._session.scalars(stmt).first()

    def replace_for_user(
        self, *, user_id: UUID, forecast: Forecast, periods: list[ForecastPeriod]
    ) -> Forecast:
        """Jobs are idempotent: re-running a forecast replaces the prior result rather
        than appending, per docs/architecture.md §3.5.
        """
        existing = self.latest_for_user(user_id=user_id)
        if existing is not None:
            self._session.execute(
                delete(ForecastPeriod).where(ForecastPeriod.forecast_id == existing.id)
            )
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
        stmt = (
            select(ForecastPeriod)
            .where(ForecastPeriod.forecast_id == forecast_id)
            .order_by(ForecastPeriod.period_index)
        )
        return list(self._session.scalars(stmt))
