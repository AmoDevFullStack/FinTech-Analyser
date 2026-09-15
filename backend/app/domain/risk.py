"""Risk detection. See specs/risk-detection.md.

Six detectors, each a pure function over already-computed figures. Every finding carries
the quantified amount, the date it materialises, and a `computation_reference` naming the
engine result it came from — "A flag whose figure cannot be traced back to a computation
is not created."

This module deliberately produces no user-facing prose. The spec's copy conventions
(state the figure and the date, never characterise the person) are applied in
app/services/risk.py, because rendering a Decimal into a sentence is presentation, and
presentation does not belong in an engine.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

CENTS = Decimal("0.01")
RATE_PLACES = Decimal("0.000001")

# Thresholds named by the spec.
DEBT_BURDEN_THRESHOLD = Decimal("0.40")
CREDIT_UTILISATION_THRESHOLD = Decimal("0.70")
EMERGENCY_COVER_FLOOR_MONTHS = Decimal("1")

# "Materiality. Below a threshold scaled to income, no flag is raised." Two percent of
# monthly income: at R20,000 income that is R400, at R80,000 it is R1,600 — the spec's own
# reasoning for why an absolute rand threshold is the wrong instrument.
MATERIALITY_RATIO_OF_INCOME = Decimal("0.02")

# Anomalous spending: how far above the user's own trailing baseline a category must sit
# before it is worth naming, expressed as a fraction of monthly income rather than of the
# category, so a 50% overspend on a tiny category does not flag.
ANOMALY_RATIO_OF_INCOME = Decimal("0.05")


class RiskType(str, enum.Enum):
    CASH_FLOW_SHORTFALL = "cash_flow_shortfall"
    OBLIGATION_COVERAGE_GAP = "obligation_coverage_gap"
    EMERGENCY_RESERVE_DEPLETION = "emergency_reserve_depletion"
    DEBT_BURDEN_THRESHOLD = "debt_burden_threshold"
    ANOMALOUS_SPENDING = "anomalous_spending"
    CREDIT_UTILISATION = "credit_utilisation"


class Severity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


_SEVERITY_ORDER = {
    Severity.LOW: 0,
    Severity.MEDIUM: 1,
    Severity.HIGH: 2,
    Severity.CRITICAL: 3,
}


def severity_rank(severity: Severity) -> int:
    """Ordinal rank, so a caller can compare severities without hardcoding the order.

    Used by the 30-day dismissal suppression, which is overridden only by an increase.
    """
    return _SEVERITY_ORDER[severity]


@dataclass(frozen=True, slots=True)
class RiskFinding:
    risk_type: RiskType
    severity: Severity
    projected_date: date | None
    quantified_amount: Decimal
    computation_reference: str
    details: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ProjectedPeriod:
    """One month of a stored forecast, as the detectors need it."""

    month: str
    starts_on: date
    inflows: Decimal
    outflows: Decimal
    liquid_funds: Decimal
    emergency_fund_months: Decimal


@dataclass(frozen=True, slots=True)
class Obligation:
    label: str
    amount: Decimal
    due_on: date


@dataclass(frozen=True, slots=True)
class CategorySpend:
    category: str
    baseline_monthly: Decimal
    current_monthly: Decimal


def _quantise(value: Decimal) -> Decimal:
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)


def materiality_threshold(*, monthly_income: Decimal) -> Decimal:
    """The rand amount below which nothing is flagged, scaled to income.

    Formula:
        threshold = monthly_income * 0.02

    Rounding: two places, ROUND_HALF_UP.

    Raises:
        ValueError: if monthly_income < 0.
    """
    if monthly_income < 0:
        raise ValueError(f"monthly_income must be >= 0, got {monthly_income}")
    return _quantise(monthly_income * MATERIALITY_RATIO_OF_INCOME)


def _severity_from_ratio(ratio: Decimal) -> Severity:
    """Map "how far past the threshold" to a severity band.

    ratio is the overshoot expressed as a fraction of the reference figure: 0.1 is ten
    percent past, 1.0 is double. The bands are deliberately coarse — a severity is a
    sorting aid for the user's attention, not a computed quantity, and pretending to
    finer resolution than that would be false precision.
    """
    if ratio >= Decimal("1.0"):
        return Severity.CRITICAL
    if ratio >= Decimal("0.5"):
        return Severity.HIGH
    if ratio >= Decimal("0.2"):
        return Severity.MEDIUM
    return Severity.LOW


def detect_cash_flow_shortfall(
    *, periods: list[ProjectedPeriod], monthly_income: Decimal, forecast_id: str
) -> RiskFinding | None:
    """A forecast month whose outflows exceed inflows plus available liquid funds.

    Formula:
        shortfall_t = outflows_t - (inflows_t + liquid_funds_{t-1})
        flagged where shortfall_t > materiality_threshold(monthly_income)

    The earliest qualifying month wins: it is the one the user can still act on, and
    flagging the largest instead would name a date months after the problem starts.

    Assumptions:
        - `liquid_funds` on a period is the balance at the END of that period, so the
          funds available to meet month t's outflows are month t-1's closing balance;
          for the first period the caller supplies the opening balance via
          `periods[0].liquid_funds` being the closing balance and the opening being
          reconstructed as closing - (inflows - outflows). This keeps the caller from
          having to pass two balance series.
        - Periods arrive in chronological order.

    Rounding: two places, ROUND_HALF_UP.

    Raises:
        ValueError: if monthly_income < 0.
    """
    threshold = materiality_threshold(monthly_income=monthly_income)

    for index, period in enumerate(periods):
        if index == 0:
            available = period.liquid_funds - (period.inflows - period.outflows)
        else:
            available = periods[index - 1].liquid_funds

        shortfall = period.outflows - (period.inflows + available)
        if shortfall > threshold:
            reference = monthly_income if monthly_income > 0 else shortfall
            return RiskFinding(
                risk_type=RiskType.CASH_FLOW_SHORTFALL,
                severity=_severity_from_ratio(shortfall / reference),
                projected_date=period.starts_on,
                quantified_amount=_quantise(shortfall),
                computation_reference=f"forecast:{forecast_id}:period:{period.month}",
                details={
                    "month": period.month,
                    "projected_inflows": str(_quantise(period.inflows)),
                    "projected_outflows": str(_quantise(period.outflows)),
                    "available_funds": str(_quantise(available)),
                },
            )
    return None


def detect_obligation_coverage_gap(
    *,
    obligations: list[Obligation],
    periods: list[ProjectedPeriod],
    monthly_income: Decimal,
    forecast_id: str,
) -> RiskFinding | None:
    """A specific obligation whose due date falls in a month that cannot cover it.

    "The most actionable flag the system produces, because it names a date and an amount."

    Formula:
        For each obligation, find the projected period containing its due date.
        available = that period's inflows + the prior period's closing liquid funds
        gap      = obligation.amount - available
        flagged where gap > materiality_threshold(monthly_income)

    Assumptions:
        - Obligations are outflows stated as positive magnitudes.
        - An obligation whose due date falls outside the projected horizon is skipped
          rather than assumed uncovered — absence of a projection is not evidence.
        - The earliest uncovered obligation is returned, for the same reason as the
          shortfall detector.

    Rounding: two places, ROUND_HALF_UP.
    """
    threshold = materiality_threshold(monthly_income=monthly_income)
    by_month = {p.month: (index, p) for index, p in enumerate(periods)}

    for obligation in sorted(obligations, key=lambda o: o.due_on):
        key = f"{obligation.due_on.year:04d}-{obligation.due_on.month:02d}"
        found = by_month.get(key)
        if found is None:
            continue
        index, period = found
        if index == 0:
            opening = period.liquid_funds - (period.inflows - period.outflows)
        else:
            opening = periods[index - 1].liquid_funds

        available = opening + period.inflows
        gap = obligation.amount - available
        if gap > threshold:
            reference = obligation.amount if obligation.amount > 0 else gap
            return RiskFinding(
                risk_type=RiskType.OBLIGATION_COVERAGE_GAP,
                severity=_severity_from_ratio(gap / reference),
                projected_date=obligation.due_on,
                quantified_amount=_quantise(gap),
                computation_reference=f"forecast:{forecast_id}:period:{period.month}",
                details={
                    "obligation": obligation.label,
                    "obligation_amount": str(_quantise(obligation.amount)),
                    "available_funds": str(_quantise(available)),
                    "month": period.month,
                },
            )
    return None


def detect_emergency_reserve_depletion(
    *,
    periods: list[ProjectedPeriod],
    monthly_essential: Decimal,
    forecast_id: str,
    floor_months: Decimal = EMERGENCY_COVER_FLOOR_MONTHS,
) -> RiskFinding | None:
    """Projected emergency cover falling below one month inside the horizon.

    Formula:
        flagged at the first period where emergency_fund_months < floor_months
        quantified_amount = the rand shortfall against the floor:
            (floor_months - cover_months) * monthly_essential

    Quantifying in rand rather than months is deliberate: "Flags state a date and an
    amount", and an amount the user can act on is a rand figure, not a ratio.

    Assumptions:
        - A user with no essential spending has no meaningful cover requirement, so
          nothing is flagged rather than dividing by zero.

    Rounding: two places, ROUND_HALF_UP.

    Raises:
        ValueError: if floor_months <= 0 or monthly_essential < 0.
    """
    if floor_months <= 0:
        raise ValueError(f"floor_months must be positive, got {floor_months}")
    if monthly_essential < 0:
        raise ValueError(f"monthly_essential must be >= 0, got {monthly_essential}")
    if monthly_essential == 0:
        return None

    for period in periods:
        if period.emergency_fund_months < floor_months:
            months_short = floor_months - period.emergency_fund_months
            amount_short = months_short * monthly_essential
            return RiskFinding(
                risk_type=RiskType.EMERGENCY_RESERVE_DEPLETION,
                severity=_severity_from_ratio(months_short / floor_months),
                projected_date=period.starts_on,
                quantified_amount=_quantise(amount_short),
                computation_reference=f"forecast:{forecast_id}:period:{period.month}",
                details={
                    "month": period.month,
                    "projected_cover_months": str(
                        period.emergency_fund_months.quantize(
                            RATE_PLACES, rounding=ROUND_HALF_UP
                        )
                    ),
                    "floor_months": str(floor_months),
                },
            )
    return None


def detect_debt_burden(
    *,
    monthly_debt_service: Decimal,
    monthly_income: Decimal,
    assessment_reference: str,
    as_of: date,
    threshold: Decimal = DEBT_BURDEN_THRESHOLD,
) -> RiskFinding | None:
    """Debt obligations exceeding 40% of net income.

    Formula:
        ratio = monthly_debt_service / monthly_income
        flagged where ratio > threshold
        quantified_amount = monthly_debt_service - (monthly_income * threshold)
            — the monthly rand amount by which debt service exceeds the threshold, which
            is the figure a user can act on; the ratio alone is not.

    Assumptions:
        - A user with no income cannot have a meaningful ratio; nothing is flagged rather
          than dividing by zero. Their problem is not debt burden.

    Rounding: amount to two places, ratio to six, both ROUND_HALF_UP.

    Raises:
        ValueError: if monthly_debt_service < 0 or threshold <= 0.
    """
    if monthly_debt_service < 0:
        raise ValueError(
            f"monthly_debt_service must be >= 0, got {monthly_debt_service}"
        )
    if threshold <= 0:
        raise ValueError(f"threshold must be positive, got {threshold}")
    if monthly_income <= 0:
        return None

    ratio = monthly_debt_service / monthly_income
    if ratio <= threshold:
        return None

    excess = monthly_debt_service - (monthly_income * threshold)
    return RiskFinding(
        risk_type=RiskType.DEBT_BURDEN_THRESHOLD,
        severity=_severity_from_ratio((ratio - threshold) / threshold),
        projected_date=as_of,
        quantified_amount=_quantise(excess),
        computation_reference=assessment_reference,
        details={
            "debt_to_income": str(ratio.quantize(RATE_PLACES, rounding=ROUND_HALF_UP)),
            "threshold": str(threshold),
            "monthly_debt_service": str(_quantise(monthly_debt_service)),
        },
    )


def detect_anomalous_spending(
    *,
    categories: list[CategorySpend],
    monthly_income: Decimal,
    as_of: date,
    position_reference: str,
    anomaly_ratio: Decimal = ANOMALY_RATIO_OF_INCOME,
) -> RiskFinding | None:
    """A category exceeding the user's own trailing baseline by a material margin.

    Formula:
        excess_c = current_monthly_c - baseline_monthly_c
        flagged where excess_c > monthly_income * anomaly_ratio
        the largest qualifying excess is returned

    Measuring the margin against income rather than against the category is the spec's
    explicit requirement: "R2,000 over on groceries means something different at R20,000
    income than at R80,000."

    Assumptions:
        - A category with no established baseline (zero) is not an anomaly — it is a new
          category, and calling a first occurrence anomalous is how a system starts crying
          wolf.
        - A user with no income has no scale to measure against; nothing is flagged.

    Rounding: two places, ROUND_HALF_UP.

    Raises:
        ValueError: if anomaly_ratio <= 0.
    """
    if anomaly_ratio <= 0:
        raise ValueError(f"anomaly_ratio must be positive, got {anomaly_ratio}")
    if monthly_income <= 0:
        return None

    margin = monthly_income * anomaly_ratio
    candidates = [
        (category, category.current_monthly - category.baseline_monthly)
        for category in categories
        if category.baseline_monthly > 0
    ]
    qualifying = [(c, excess) for c, excess in candidates if excess > margin]
    if not qualifying:
        return None

    category, excess = max(qualifying, key=lambda pair: pair[1])
    return RiskFinding(
        risk_type=RiskType.ANOMALOUS_SPENDING,
        severity=_severity_from_ratio(excess / margin if margin > 0 else Decimal("0")),
        projected_date=as_of,
        quantified_amount=_quantise(excess),
        computation_reference=position_reference,
        details={
            "category": category.category,
            "baseline_monthly": str(_quantise(category.baseline_monthly)),
            "current_monthly": str(_quantise(category.current_monthly)),
        },
    )


def detect_credit_utilisation(
    *,
    revolving_balance: Decimal,
    credit_limit: Decimal,
    as_of: date,
    position_reference: str,
    threshold: Decimal = CREDIT_UTILISATION_THRESHOLD,
) -> RiskFinding | None:
    """Revolving utilisation above 70%.

    Formula:
        utilisation = revolving_balance / credit_limit
        flagged where utilisation > threshold
        quantified_amount = revolving_balance - (credit_limit * threshold)
            — the rand repayment that brings utilisation back to the threshold.

    Assumptions:
        - A user with no revolving facility (limit of zero) has no utilisation; nothing
          is flagged rather than dividing by zero.
        - `revolving_balance` is the positive magnitude owed, the caller having already
          resolved the credit card's negative-balance sign convention.

    Rounding: amount to two places, ratio to six, both ROUND_HALF_UP.

    Raises:
        ValueError: if revolving_balance < 0, credit_limit < 0, or threshold <= 0.
    """
    if revolving_balance < 0:
        raise ValueError(f"revolving_balance must be >= 0, got {revolving_balance}")
    if credit_limit < 0:
        raise ValueError(f"credit_limit must be >= 0, got {credit_limit}")
    if threshold <= 0:
        raise ValueError(f"threshold must be positive, got {threshold}")
    if credit_limit == 0:
        return None

    utilisation = revolving_balance / credit_limit
    if utilisation <= threshold:
        return None

    excess = revolving_balance - (credit_limit * threshold)
    return RiskFinding(
        risk_type=RiskType.CREDIT_UTILISATION,
        severity=_severity_from_ratio((utilisation - threshold) / threshold),
        projected_date=as_of,
        quantified_amount=_quantise(excess),
        computation_reference=position_reference,
        details={
            "utilisation": str(utilisation.quantize(RATE_PLACES, rounding=ROUND_HALF_UP)),
            "threshold": str(threshold),
            "revolving_balance": str(_quantise(revolving_balance)),
            "credit_limit": str(_quantise(credit_limit)),
        },
    )
