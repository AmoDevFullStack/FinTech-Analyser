"""Forecast accuracy measurement. See specs/forecasting.md.

"A forecasting product that never checks itself is a horoscope." This engine compares what
was projected for a month against what the month actually did, and reports the error
signed — because the direction of a persistent error is the useful part. A discretionary
baseline that is always too low is a baseline to raise, not noise to average away.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

CENTS = Decimal("0.01")
RATE_PLACES = Decimal("0.000001")

# How many consecutive same-signed months before an error counts as a bias worth acting
# on rather than a run of luck. Three is the same threshold the recurrence engine uses for
# calling something a pattern, for the same reason: two of anything is a coincidence.
BIAS_MONTHS = 3

# A bias smaller than this fraction of the projected figure is not worth adjusting for —
# it is within the noise of when a debit order lands relative to month end.
BIAS_MATERIALITY = Decimal("0.05")


class Metric(str, enum.Enum):
    INCOME = "income"
    EXPENSES = "expenses"
    CASH_FLOW = "cash_flow"
    SAVINGS_BALANCE = "savings_balance"
    NET_WORTH = "net_worth"


def _quantise(value: Decimal) -> Decimal:
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class MetricComparison:
    metric: Metric
    projected: Decimal
    actual: Decimal
    absolute_error: Decimal
    percentage_error: Decimal | None
    signed_error: Decimal


@dataclass(frozen=True, slots=True)
class MonthAccuracy:
    month: str
    comparisons: tuple[MetricComparison, ...]

    def for_metric(self, metric: Metric) -> MetricComparison | None:
        return next((c for c in self.comparisons if c.metric is metric), None)


def compare_month(
    *, month: str, projected: dict[Metric, Decimal], actual: dict[Metric, Decimal]
) -> MonthAccuracy:
    """Compare one month's projection against its realised actuals.

    Formula, per metric present in both dictionaries:
        signed_error     = actual - projected
        absolute_error   = |signed_error|
        percentage_error = signed_error / |projected|, or None when projected is zero

    `percentage_error` is None rather than zero or infinity when the projection was zero:
    there is no meaningful percentage against a zero base, and reporting one would make a
    R500 miss on a R0 projection look like either perfection or catastrophe depending on
    which fiction was chosen.

    Rounding:
        Money to two places, percentages to six, both ROUND_HALF_UP.

    Raises:
        ValueError: if `month` is empty.
    """
    if not month:
        raise ValueError("month must be a non-empty YYYY-MM string")

    comparisons = []
    for metric in Metric:
        if metric not in projected or metric not in actual:
            continue
        projected_value = projected[metric]
        actual_value = actual[metric]
        signed = actual_value - projected_value
        percentage = (
            (signed / abs(projected_value)).quantize(RATE_PLACES, rounding=ROUND_HALF_UP)
            if projected_value != 0
            else None
        )
        comparisons.append(
            MetricComparison(
                metric=metric,
                projected=_quantise(projected_value),
                actual=_quantise(actual_value),
                absolute_error=_quantise(abs(signed)),
                percentage_error=percentage,
                signed_error=_quantise(signed),
            )
        )

    return MonthAccuracy(month=month, comparisons=tuple(comparisons))


@dataclass(frozen=True, slots=True)
class AccuracySummary:
    metric: Metric
    months_measured: int
    mean_absolute_error: Decimal
    mean_percentage_error: Decimal | None
    has_persistent_bias: bool
    bias_direction: str | None  # "over_projected" | "under_projected" | None
    suggested_adjustment: Decimal


def summarise(
    *,
    metric: Metric,
    history: list[MonthAccuracy],
    bias_months: int = BIAS_MONTHS,
    materiality: Decimal = BIAS_MATERIALITY,
) -> AccuracySummary:
    """Summarise a metric's error history and say whether it is biased.

    Formula:
        mean_absolute_error   = sum(|error_m|) / months
        mean_percentage_error = sum(percentage_error_m) / months over months where it exists
        has_persistent_bias   = the last `bias_months` months all share a sign
                                AND |mean_percentage_error| > materiality
        suggested_adjustment  = mean signed error over the biased run, which is the amount
                                to move the baseline by to remove the bias

    "used to adjust the discretionary spending baseline where error is persistently
    one-directional" — `suggested_adjustment` is that adjustment, and it is signed:
    positive means actuals came in above projection, so the baseline should rise.

    Assumptions:
        - `history` is chronological, oldest first; the bias test reads the tail.
        - A metric with fewer than `bias_months` observations is never called biased, no
          matter how consistent it looks.

    Rounding:
        Money to two places, percentages to six, both ROUND_HALF_UP.

    Raises:
        ValueError: if bias_months < 2 or materiality < 0.
    """
    if bias_months < 2:
        raise ValueError(f"bias_months must be >= 2, got {bias_months}")
    if materiality < 0:
        raise ValueError(f"materiality must be >= 0, got {materiality}")

    comparisons = [
        comparison
        for month in history
        if (comparison := month.for_metric(metric)) is not None
    ]
    if not comparisons:
        return AccuracySummary(
            metric=metric,
            months_measured=0,
            mean_absolute_error=Decimal("0.00"),
            mean_percentage_error=None,
            has_persistent_bias=False,
            bias_direction=None,
            suggested_adjustment=Decimal("0.00"),
        )

    count = Decimal(len(comparisons))
    mean_absolute = _quantise(
        sum((c.absolute_error for c in comparisons), Decimal("0")) / count
    )

    percentages = [c.percentage_error for c in comparisons if c.percentage_error is not None]
    mean_percentage = (
        (sum(percentages, Decimal("0")) / Decimal(len(percentages))).quantize(
            RATE_PLACES, rounding=ROUND_HALF_UP
        )
        if percentages
        else None
    )

    tail = comparisons[-bias_months:]
    consistent = len(tail) >= bias_months and (
        all(c.signed_error > 0 for c in tail) or all(c.signed_error < 0 for c in tail)
    )
    material = mean_percentage is not None and abs(mean_percentage) > materiality
    has_bias = consistent and material

    if not has_bias:
        return AccuracySummary(
            metric=metric,
            months_measured=len(comparisons),
            mean_absolute_error=mean_absolute,
            mean_percentage_error=mean_percentage,
            has_persistent_bias=False,
            bias_direction=None,
            suggested_adjustment=Decimal("0.00"),
        )

    adjustment = _quantise(sum((c.signed_error for c in tail), Decimal("0")) / Decimal(len(tail)))
    return AccuracySummary(
        metric=metric,
        months_measured=len(comparisons),
        mean_absolute_error=mean_absolute,
        mean_percentage_error=mean_percentage,
        has_persistent_bias=True,
        bias_direction="under_projected" if adjustment > 0 else "over_projected",
        suggested_adjustment=adjustment,
    )
