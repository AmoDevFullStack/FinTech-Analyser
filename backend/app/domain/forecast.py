"""Behavioural forecasting. See specs/forecasting.md.

Two jobs: derive how a user actually behaves from their history, and project that forward
under stated assumptions. Both are deliberately boring — the value is in using medians
rather than means, in applying growth on the dates it actually happens, and in labelling
a thin history as thin instead of projecting confidently from three weeks of data.

Nothing here reads the clock: `as_of` and every assumption arrives as a parameter, so a
forecast regenerated from the same stored inputs reproduces exactly, which is what
specs/forecasting.md's reproducibility criterion requires.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.domain.amortisation import AmortisationPeriod

CENTS = Decimal("0.01")
RATE_PLACES = Decimal("0.000001")
TWELVE = Decimal("12")

MINIMUM_CONFIDENT_MONTHS = 3
DEFAULT_INFLATION_ANNUAL = Decimal("0.05")
DEFAULT_SALARY_GROWTH_ANNUAL = Decimal("0.05")
DEFAULT_HORIZON_MONTHS = 60
ENGINE_VERSION = "1.1.0"


def _quantise(value: Decimal) -> Decimal:
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)


def _median(values: list[Decimal]) -> Decimal:
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / Decimal("2")


@dataclass(frozen=True, slots=True)
class MonthlyObservation:
    month: str
    income: Decimal
    essential: Decimal
    discretionary: Decimal


@dataclass(frozen=True, slots=True)
class BehaviouralBaseline:
    median_income: Decimal
    median_essential: Decimal
    median_discretionary: Decimal
    discretionary_variability: Decimal
    months_observed: int
    is_low_confidence: bool


@dataclass(frozen=True, slots=True)
class ForecastAssumptions:
    inflation_annual: Decimal = DEFAULT_INFLATION_ANNUAL
    salary_growth_annual: Decimal = DEFAULT_SALARY_GROWTH_ANNUAL
    horizon_months: int = DEFAULT_HORIZON_MONTHS

    def as_dict(self) -> dict[str, str]:
        return {
            "inflation_annual": str(self.inflation_annual),
            "salary_growth_annual": str(self.salary_growth_annual),
            "horizon_months": str(self.horizon_months),
        }


@dataclass(frozen=True, slots=True)
class ForecastPeriodProjection:
    period: int
    month: str
    projected_income: Decimal
    projected_expenses: Decimal
    cash_flow: Decimal
    savings_balance: Decimal
    debt_balance: Decimal
    emergency_fund_months: Decimal
    net_worth: Decimal


def derive_baselines(
    *, observations: list[MonthlyObservation], minimum_months: int = MINIMUM_CONFIDENT_MONTHS
) -> BehaviouralBaseline:
    """Reduce a history of monthly totals to the figures a projection runs on.

    Formula:
        median_income        = median(observed monthly income)
        median_essential     = median(observed monthly essential spending)
        median_discretionary = median(observed monthly discretionary spending)
        discretionary_variability = median(|discretionary_m - median_discretionary|)
                                    / median_discretionary

    Medians, not means: "One bonus month or one medical emergency should not shift the
    baseline, and means are exactly the statistic that lets them." The variability figure
    is a median absolute deviation for the same reason, expressed as a fraction of the
    baseline so it can be compared across users of different incomes.

    Assumptions:
        - Each observation is one complete month, already summed and sign-normalised by
          the caller (spending positive).
        - Fewer than `minimum_months` observations sets `is_low_confidence`, which the
          caller must surface — specs/forecasting.md requires such a forecast be labelled,
          not suppressed.
        - An empty history returns zeros rather than raising: a brand-new user has a
          position and no behaviour, and that is a legitimate state to project from (flat).

    Rounding:
        Money to two places, variability to six, both ROUND_HALF_UP.

    Raises:
        ValueError: if minimum_months < 1.
    """
    if minimum_months < 1:
        raise ValueError(f"minimum_months must be >= 1, got {minimum_months}")

    if not observations:
        return BehaviouralBaseline(
            median_income=Decimal("0.00"),
            median_essential=Decimal("0.00"),
            median_discretionary=Decimal("0.00"),
            discretionary_variability=Decimal("0.000000"),
            months_observed=0,
            is_low_confidence=True,
        )

    income = _median([o.income for o in observations])
    essential = _median([o.essential for o in observations])
    discretionary = _median([o.discretionary for o in observations])

    if discretionary > 0:
        deviations = [abs(o.discretionary - discretionary) for o in observations]
        variability = _median(deviations) / discretionary
    else:
        variability = Decimal("0")

    return BehaviouralBaseline(
        median_income=_quantise(income),
        median_essential=_quantise(essential),
        median_discretionary=_quantise(discretionary),
        discretionary_variability=variability.quantize(RATE_PLACES, rounding=ROUND_HALF_UP),
        months_observed=len(observations),
        is_low_confidence=len(observations) < minimum_months,
    )


def project_forecast(
    *,
    baseline: BehaviouralBaseline,
    opening_savings: Decimal,
    opening_debt: Decimal,
    opening_net_worth: Decimal,
    as_of: date,
    assumptions: ForecastAssumptions = ForecastAssumptions(),
    existing_debt_schedule: tuple[AmortisationPeriod, ...] = (),
    monthly_debt_service: Decimal = Decimal("0"),
) -> list[ForecastPeriodProjection]:
    """Project every metric the dashboard and risk engine read, month by month.

    Formula, per period t (1-indexed from the month after `as_of`):
        years_elapsed_t = (t - 1) // 12
        income_t        = median_income * (1 + salary_growth_annual) ** years_elapsed_t
        essential_t     = median_essential * (1 + inflation_annual) ** years_elapsed_t
        discretionary_t = median_discretionary * (1 + inflation_annual) ** years_elapsed_t
        debt_service_t  = existing_debt_schedule[t-1].instalment, else monthly_debt_service
        cash_flow_t     = income_t - essential_t - discretionary_t - debt_service_t
        savings_t       = savings_{t-1} + cash_flow_t
        debt_t          = existing_debt_schedule[t-1].closing_balance, else opening_debt
        cover_t         = savings_t / essential_t          (0 when essential_t is 0)
        net_worth_t     = net_worth_{t-1} + cash_flow_t + principal repaid in t

    Assumptions:
        - Salary growth applies annually, on the anniversary of the forecast's start
          rather than on a stored increase date — the increase date is not modelled yet,
          and pretending to know it would be false precision.
        - Inflation applies to essential AND discretionary spending: discretionary is held
          flat in REAL terms per the spec, which means it grows with inflation in nominal
          terms. Holding it flat nominally would quietly forecast the user consuming less
          every year.
        - Growth compounds on whole elapsed years, not monthly, so the projection steps at
          the anniversary the way a salary actually does.
        - Emergency cover is clamped at zero for a negative savings balance: a projection
          can legitimately run a balance negative, and negative months of cover is not a
          meaningful figure.

    Rounding:
        Every period figure to two places (cover to six), ROUND_HALF_UP, applied per
        period rather than at the end, so the stored series sums consistently.

    Raises:
        ValueError: if horizon_months < 1, inflation or growth < -1 (a rate below -100%
            is not a rate), or monthly_debt_service < 0.
    """
    if assumptions.horizon_months < 1:
        raise ValueError(
            f"horizon_months must be >= 1, got {assumptions.horizon_months}"
        )
    if assumptions.inflation_annual < -1:
        raise ValueError(
            f"inflation_annual must be >= -1, got {assumptions.inflation_annual}"
        )
    if assumptions.salary_growth_annual < -1:
        raise ValueError(
            f"salary_growth_annual must be >= -1, got {assumptions.salary_growth_annual}"
        )
    if monthly_debt_service < 0:
        raise ValueError(
            f"monthly_debt_service must be >= 0, got {monthly_debt_service}"
        )

    periods: list[ForecastPeriodProjection] = []
    savings = opening_savings
    net_worth = opening_net_worth
    year, month = as_of.year, as_of.month

    for t in range(1, assumptions.horizon_months + 1):
        month += 1
        if month > 12:
            month = 1
            year += 1

        years_elapsed = (t - 1) // 12
        income = baseline.median_income * (
            (1 + assumptions.salary_growth_annual) ** years_elapsed
        )
        inflator = (1 + assumptions.inflation_annual) ** years_elapsed
        essential = baseline.median_essential * inflator
        discretionary = baseline.median_discretionary * inflator

        if existing_debt_schedule and t <= len(existing_debt_schedule):
            debt_period = existing_debt_schedule[t - 1]
            debt_service = debt_period.instalment
            principal_repaid = debt_period.principal
            debt_balance = debt_period.closing_balance
        elif existing_debt_schedule:
            debt_service = Decimal("0")
            principal_repaid = Decimal("0")
            debt_balance = Decimal("0")
        else:
            debt_service = monthly_debt_service
            principal_repaid = Decimal("0")
            debt_balance = opening_debt

        cash_flow = _quantise(income - essential - discretionary - debt_service)
        savings = _quantise(savings + cash_flow)
        net_worth = _quantise(net_worth + cash_flow + principal_repaid)

        if essential > 0 and savings > 0:
            cover = (savings / essential).quantize(RATE_PLACES, rounding=ROUND_HALF_UP)
        else:
            cover = Decimal("0.000000")

        periods.append(
            ForecastPeriodProjection(
                period=t,
                month=f"{year:04d}-{month:02d}",
                projected_income=_quantise(income),
                projected_expenses=_quantise(essential + discretionary + debt_service),
                cash_flow=cash_flow,
                savings_balance=savings,
                debt_balance=_quantise(debt_balance),
                emergency_fund_months=cover,
                net_worth=net_worth,
            )
        )

    return periods
