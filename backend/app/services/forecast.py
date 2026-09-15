"""Forecast generation and accuracy measurement. See specs/forecasting.md.

This service assembles history, hands it to app/domain/forecast.py, persists the result,
and later scores that result against what actually happened. It calculates nothing: the
medians, the growth, and the error arithmetic all live in the domain.

Per ADR-003 forecasts are never computed during a request — `generate` is called by the
worker (app/workers/forecast.py) and by an explicit refresh, and the API reads stored rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select

from app.core.db import DbSession
from app.domain.accuracy import AccuracySummary, Metric, MonthAccuracy, compare_month, summarise
from app.domain.amortisation import AmortisationPeriod
from app.domain.debt_payoff import DebtInput, avalanche_schedule
from app.domain.forecast import (
    ENGINE_VERSION,
    BehaviouralBaseline,
    ForecastAssumptions,
    MonthlyObservation,
    derive_baselines,
    project_forecast,
)
from app.models.category import CategoryKind
from app.models.forecast import Forecast, ForecastPeriod
from app.models.forecast_accuracy import ForecastAccuracy
from app.repositories.account import AccountRepository
from app.repositories.debt import DebtRepository
from app.repositories.forecast import ForecastRepository
from app.services.position import PositionService

HISTORY_MONTHS = 12


def _month_key(value: date) -> str:
    return f"{value.year:04d}-{value.month:02d}"


def _month_start(value: date, *, months_back: int) -> date:
    total = value.month - 1 - months_back
    year = value.year + total // 12
    month = total % 12 + 1
    return date(year, month, 1)


def _month_end(month_start: date) -> date:
    if month_start.month == 12:
        return date(month_start.year, 12, 31)
    return date(month_start.year, month_start.month + 1, 1) - timedelta(days=1)


@dataclass(frozen=True, slots=True)
class ForecastView:
    forecast: Forecast
    periods: list[ForecastPeriod]
    baseline: BehaviouralBaseline | None


class ForecastService:
    def __init__(self, session: DbSession) -> None:
        self._session = session
        self._forecasts = ForecastRepository(session)
        self._accounts = AccountRepository(session)
        self._debts = DebtRepository(session)
        self._position = PositionService(session)

    def monthly_observations(
        self, *, user_id: UUID, as_of: date, months: int = HISTORY_MONTHS
    ) -> list[MonthlyObservation]:
        """One `MonthlyObservation` per complete calendar month of history.

        The current month is excluded: it is partial, and a half-finished month read as a
        whole one would halve the apparent income and drag every median down.
        """
        accounts = self._accounts.list_for_user(user_id=user_id)
        observations: list[MonthlyObservation] = []

        for offset in range(months, 0, -1):
            start = _month_start(as_of, months_back=offset)
            end = _month_end(start)
            sums = self._position.category_kind_sums(
                user_id=user_id, accounts=accounts, since=start, until=end
            )
            if (
                sums[CategoryKind.INCOME] == 0
                and sums[CategoryKind.ESSENTIAL] == 0
                and sums[CategoryKind.DISCRETIONARY] == 0
            ):
                continue  # no data for that month; an absent month is not a zero month
            observations.append(
                MonthlyObservation(
                    month=_month_key(start),
                    income=sums[CategoryKind.INCOME],
                    essential=sums[CategoryKind.ESSENTIAL],
                    discretionary=sums[CategoryKind.DISCRETIONARY],
                )
            )
        return observations

    def _existing_debt_schedule(self, *, user_id: UUID) -> tuple[AmortisationPeriod, ...]:
        debts = [
            d for d in self._debts.list_for_user(user_id=user_id) if d.current_balance > 0
        ]
        if not debts:
            return ()

        inputs = [
            DebtInput(
                id=str(d.id),
                current_balance=d.current_balance,
                annual_rate=d.annual_rate,
                minimum_payment=(d.instalment if d.instalment is not None else d.minimum_payment),
            )
            for d in debts
        ]
        total_monthly = sum((d.minimum_payment for d in inputs), Decimal("0"))
        result = avalanche_schedule(inputs, total_monthly)
        return tuple(
            AmortisationPeriod(
                period=p.month,
                opening_balance=p.total_balance + p.principal,
                instalment=p.payment,
                interest=p.interest,
                principal=p.principal,
                closing_balance=p.total_balance,
            )
            for p in result.schedule
        )

    def generate(
        self,
        *,
        user_id: UUID,
        as_of: date | None = None,
        assumptions: ForecastAssumptions | None = None,
    ) -> Forecast:
        """Compute and persist a fresh forecast, replacing the user's previous one."""
        as_of = as_of or date.today()
        assumptions = assumptions or ForecastAssumptions()

        snapshot = self._position.capture_snapshot(user_id=user_id)
        observations = self.monthly_observations(user_id=user_id, as_of=as_of)
        baseline = derive_baselines(observations=observations)

        if baseline.months_observed == 0:
            # No history at all: project from the position's current month rather than
            # from nothing, and let is_low_confidence carry the caveat.
            baseline = BehaviouralBaseline(
                median_income=snapshot.monthly_income,
                median_essential=snapshot.monthly_essential,
                median_discretionary=snapshot.monthly_discretionary,
                discretionary_variability=Decimal("0.000000"),
                months_observed=0,
                is_low_confidence=True,
            )

        schedule = self._existing_debt_schedule(user_id=user_id)
        projected = project_forecast(
            baseline=baseline,
            opening_savings=snapshot.liquid_savings,
            opening_debt=snapshot.total_debt,
            opening_net_worth=snapshot.net_worth,
            as_of=as_of,
            assumptions=assumptions,
            existing_debt_schedule=schedule,
        )

        forecast = Forecast(
            user_id=user_id,
            horizon_months=assumptions.horizon_months,
            generated_at=datetime.now(UTC),
            input_snapshot_id=snapshot.id,
            assumptions={
                **assumptions.as_dict(),
                "months_observed": str(baseline.months_observed),
                "is_low_confidence": "true" if baseline.is_low_confidence else "false",
                "median_income": str(baseline.median_income),
                "median_essential": str(baseline.median_essential),
                "median_discretionary": str(baseline.median_discretionary),
                "discretionary_variability": str(baseline.discretionary_variability),
            },
            engine_version=ENGINE_VERSION,
            is_stale=False,
        )
        period_rows = [
            ForecastPeriod(
                forecast_id=forecast.id,
                period_index=p.period,
                month=p.month,
                projected_income=p.projected_income,
                projected_expenses=p.projected_expenses,
                cash_flow=p.cash_flow,
                savings_balance=p.savings_balance,
                debt_balance=p.debt_balance,
                emergency_fund_months=p.emergency_fund_months,
                net_worth=p.net_worth,
            )
            for p in projected
        ]

        self._forecasts.replace_for_user(
            user_id=user_id, forecast=forecast, periods=period_rows
        )
        self._session.commit()
        return forecast

    def current(self, *, user_id: UUID) -> ForecastView | None:
        forecast = self._forecasts.latest_for_user(user_id=user_id)
        if forecast is None:
            return None
        return ForecastView(
            forecast=forecast,
            periods=self._forecasts.periods_for(forecast.id),
            baseline=None,
        )

    def mark_stale(self, *, user_id: UUID) -> None:
        """Flag the stored forecast as out of date after a material change.

        specs/forecasting.md: "Marking stale is enough — regeneration is queued, not
        immediate." Callers are the import, debt, goal and assumption paths.
        """
        forecast = self._forecasts.latest_for_user(user_id=user_id)
        if forecast is not None and not forecast.is_stale:
            forecast.is_stale = True
            self._session.commit()

    def measure_accuracy(self, *, user_id: UUID, as_of: date | None = None) -> list[MonthAccuracy]:
        """Score the months that have now been realised against what was projected for them.

        Only complete months are measured, and only months for which a projection exists.
        Re-measuring a month overwrites its previous score rather than appending, so the
        history stays one row per month per metric.
        """
        as_of = as_of or date.today()
        forecast = self._forecasts.latest_for_user(user_id=user_id)
        if forecast is None:
            return []

        accounts = self._accounts.list_for_user(user_id=user_id)
        projected_by_month = {
            row.month: row for row in self._forecasts.periods_for(forecast.id)
        }

        measured: list[MonthAccuracy] = []
        for offset in range(HISTORY_MONTHS, 0, -1):
            start = _month_start(as_of, months_back=offset)
            key = _month_key(start)
            projection = projected_by_month.get(key)
            if projection is None:
                continue

            sums = self._position.category_kind_sums(
                user_id=user_id, accounts=accounts, since=start, until=_month_end(start)
            )
            actual_income = sums[CategoryKind.INCOME]
            actual_expenses = (
                sums[CategoryKind.ESSENTIAL]
                + sums[CategoryKind.DISCRETIONARY]
                + sums[CategoryKind.DEBT]
            )
            if actual_income == 0 and actual_expenses == 0:
                continue

            accuracy = compare_month(
                month=key,
                projected={
                    Metric.INCOME: projection.projected_income,
                    Metric.EXPENSES: projection.projected_expenses,
                    Metric.CASH_FLOW: projection.cash_flow,
                },
                actual={
                    Metric.INCOME: actual_income,
                    Metric.EXPENSES: actual_expenses,
                    Metric.CASH_FLOW: actual_income - actual_expenses,
                },
            )
            measured.append(accuracy)
            self._persist_accuracy(
                user_id=user_id, forecast_id=forecast.id, accuracy=accuracy
            )

        self._session.commit()
        return measured

    def _persist_accuracy(
        self, *, user_id: UUID, forecast_id: UUID, accuracy: MonthAccuracy
    ) -> None:
        for comparison in accuracy.comparisons:
            existing = self._session.scalars(
                select(ForecastAccuracy).where(
                    ForecastAccuracy.user_id == user_id,
                    ForecastAccuracy.month == accuracy.month,
                    ForecastAccuracy.metric == comparison.metric.value,
                )
            ).first()
            row = existing or ForecastAccuracy(
                user_id=user_id,
                month=accuracy.month,
                metric=comparison.metric.value,
            )
            row.forecast_id = forecast_id
            row.projected = comparison.projected
            row.actual = comparison.actual
            row.absolute_error = comparison.absolute_error
            row.signed_error = comparison.signed_error
            row.percentage_error = comparison.percentage_error
            row.engine_version = ENGINE_VERSION
            if existing is None:
                self._session.add(row)

    def accuracy_history(self, *, user_id: UUID) -> list[ForecastAccuracy]:
        stmt = (
            select(ForecastAccuracy)
            .where(ForecastAccuracy.user_id == user_id)
            .order_by(ForecastAccuracy.month)
        )
        return list(self._session.scalars(stmt))

    def accuracy_summaries(self, *, user_id: UUID) -> list[AccuracySummary]:
        """Per-metric summary, including whether the engine is persistently biased."""
        rows = self.accuracy_history(user_id=user_id)
        by_month: dict[str, dict[Metric, tuple[Decimal, Decimal]]] = {}
        for row in rows:
            try:
                metric = Metric(row.metric)
            except ValueError:
                continue
            by_month.setdefault(row.month, {})[metric] = (row.projected, row.actual)

        history = [
            compare_month(
                month=month,
                projected={metric: values[0] for metric, values in metrics.items()},
                actual={metric: values[1] for metric, values in metrics.items()},
            )
            for month, metrics in sorted(by_month.items())
        ]
        return [summarise(metric=metric, history=history) for metric in Metric]
