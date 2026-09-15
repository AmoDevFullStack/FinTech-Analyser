"""Recurring series detection. See specs/transactions.md step 6.

A recurring commitment and a one-off that happens to repeat behave differently under
projection: "A R900 monthly debit order continues; a R900 restaurant bill may not." This
engine decides which of the two a group of transactions is, from the regularity of its
intervals and the stability of its amounts — never from the merchant name, which is not
evidence.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

CENTS = Decimal("0.01")
MINIMUM_OCCURRENCES = 3

# A monthly debit order lands on the 1st of months that are 28, 30, and 31 days long, so
# its observed gaps vary by up to three days with nothing irregular happening. These
# bands are wide enough to absorb that and month-end/weekend shifts, and narrow enough
# that they do not overlap each other.
_FREQUENCY_BANDS: tuple[tuple[int, int, str], ...] = (
    (6, 8, "weekly"),
    (12, 16, "fortnightly"),
    (26, 35, "monthly"),
    (84, 96, "quarterly"),
    (175, 190, "semi_annual"),
    (350, 380, "annual"),
)

DEFAULT_AMOUNT_TOLERANCE = Decimal("0.15")  # 15% either side of the median
DEFAULT_INTERVAL_TOLERANCE_DAYS = 5


class Frequency(str, enum.Enum):
    WEEKLY = "weekly"
    FORTNIGHTLY = "fortnightly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    SEMI_ANNUAL = "semi_annual"
    ANNUAL = "annual"

    @property
    def months_per_year(self) -> Decimal:
        """Occurrences per year, used to annualise a series' cost."""
        return {
            Frequency.WEEKLY: Decimal("52"),
            Frequency.FORTNIGHTLY: Decimal("26"),
            Frequency.MONTHLY: Decimal("12"),
            Frequency.QUARTERLY: Decimal("4"),
            Frequency.SEMI_ANNUAL: Decimal("2"),
            Frequency.ANNUAL: Decimal("1"),
        }[self]


@dataclass(frozen=True, slots=True)
class Occurrence:
    occurred_on: date
    amount: Decimal


@dataclass(frozen=True, slots=True)
class RecurringSeries:
    key: str
    frequency: Frequency
    median_amount: Decimal
    occurrence_count: int
    first_seen: date
    last_seen: date
    interval_days: int
    next_expected_on: date

    @property
    def monthly_equivalent(self) -> Decimal:
        """The series' cost expressed per month, for comparison against monthly cash flow.

        Rounding: two places, ROUND_HALF_UP, since this is a period result.
        """
        annual = abs(self.median_amount) * self.frequency.months_per_year
        return (annual / Decimal("12")).quantize(CENTS, rounding=ROUND_HALF_UP)

    @property
    def annual_cost(self) -> Decimal:
        """The series' cost over a year — what the subscription audit reports.

        Rounding: two places, ROUND_HALF_UP.
        """
        return (abs(self.median_amount) * self.frequency.months_per_year).quantize(
            CENTS, rounding=ROUND_HALF_UP
        )


def _median(values: list[Decimal]) -> Decimal:
    """Median of a non-empty list, in `Decimal` throughout.

    Medians rather than means, per specs/forecasting.md: "One bonus month or one medical
    emergency should not shift the baseline, and means are exactly the statistic that
    lets them." The same reasoning applies to a series' representative amount.
    """
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / Decimal("2")


def _median_int(values: list[int]) -> int:
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) // 2


def _frequency_for(interval_days: int) -> Frequency | None:
    for low, high, name in _FREQUENCY_BANDS:
        if low <= interval_days <= high:
            return Frequency(name)
    return None


def detect_series(
    *,
    key: str,
    occurrences: list[Occurrence],
    amount_tolerance: Decimal = DEFAULT_AMOUNT_TOLERANCE,
    interval_tolerance_days: int = DEFAULT_INTERVAL_TOLERANCE_DAYS,
    minimum_occurrences: int = MINIMUM_OCCURRENCES,
) -> RecurringSeries | None:
    """Decide whether one group of same-description occurrences is a recurring series.

    Formula:
        gaps          = [d(i+1) - d(i) for consecutive occurrence dates]
        interval_days = median(gaps)
        frequency     = the band interval_days falls in (weekly .. annual), else None
        median_amount = median(amounts)
        next_expected = last_seen + interval_days

    A group is a series when all three hold:
        1. It has at least `minimum_occurrences` occurrences (three, per the spec).
        2. Every gap is within `interval_tolerance_days` of the median gap.
        3. Every amount is within `amount_tolerance` (a fraction) of the median amount.

    Assumptions:
        - `occurrences` all share a normalised description; grouping is the caller's job,
          since it depends on how descriptions were normalised, which is not this
          engine's concern.
        - Amounts keep their sign convention (outflows negative); comparison is on
          magnitude, so a series of debits and a series of credits both detect.
        - A median amount of zero cannot anchor a proportional tolerance, so a group whose
          median amount is zero is not a series.

    Rounding:
        `median_amount` is returned unrounded — it is an input to other engines, not a
        period result. `monthly_equivalent` and `annual_cost` on the returned object
        quantise to two places with ROUND_HALF_UP.

    Raises:
        ValueError: if amount_tolerance < 0, interval_tolerance_days < 0, or
            minimum_occurrences < 2.
    """
    if amount_tolerance < 0:
        raise ValueError(f"amount_tolerance must be >= 0, got {amount_tolerance}")
    if interval_tolerance_days < 0:
        raise ValueError(
            f"interval_tolerance_days must be >= 0, got {interval_tolerance_days}"
        )
    if minimum_occurrences < 2:
        raise ValueError(f"minimum_occurrences must be >= 2, got {minimum_occurrences}")

    if len(occurrences) < minimum_occurrences:
        return None

    ordered = sorted(occurrences, key=lambda o: o.occurred_on)
    gaps = [
        (later.occurred_on - earlier.occurred_on).days
        for earlier, later in zip(ordered, ordered[1:])
    ]
    if any(gap <= 0 for gap in gaps):
        # Two occurrences on the same day are not an interval — a duplicated charge or a
        # split payment, neither of which is evidence of a schedule.
        return None

    interval_days = _median_int(gaps)
    if any(abs(gap - interval_days) > interval_tolerance_days for gap in gaps):
        return None

    frequency = _frequency_for(interval_days)
    if frequency is None:
        return None

    median_amount = _median([o.amount for o in ordered])
    if median_amount == 0:
        return None

    tolerance = abs(median_amount) * amount_tolerance
    if any(abs(o.amount - median_amount) > tolerance for o in ordered):
        return None

    return RecurringSeries(
        key=key,
        frequency=frequency,
        median_amount=median_amount,
        occurrence_count=len(ordered),
        first_seen=ordered[0].occurred_on,
        last_seen=ordered[-1].occurred_on,
        interval_days=interval_days,
        next_expected_on=ordered[-1].occurred_on + timedelta(days=interval_days),
    )


def detect_all(
    *,
    groups: dict[str, list[Occurrence]],
    amount_tolerance: Decimal = DEFAULT_AMOUNT_TOLERANCE,
    interval_tolerance_days: int = DEFAULT_INTERVAL_TOLERANCE_DAYS,
    minimum_occurrences: int = MINIMUM_OCCURRENCES,
) -> list[RecurringSeries]:
    """Run `detect_series` over every group, returning only those that are series.

    Ordered by descending monthly equivalent, so the largest commitment reads first
    wherever the result is displayed or truncated.
    """
    series = [
        detected
        for key, occurrences in groups.items()
        if (
            detected := detect_series(
                key=key,
                occurrences=occurrences,
                amount_tolerance=amount_tolerance,
                interval_tolerance_days=interval_tolerance_days,
                minimum_occurrences=minimum_occurrences,
            )
        )
        is not None
    ]
    return sorted(series, key=lambda s: s.monthly_equivalent, reverse=True)


def next_occurrence_of_day(*, as_of: date, day: int) -> date:
    """The next date on or after `as_of` falling on `day` of the month.

    Clamped to short months: an obligation collected on the 31st is collected on the 30th
    in November and the 28th in a non-leap February, which is what a debit order actually
    does.

    Raises:
        ValueError: if day is outside 1-31.
    """
    if not 1 <= day <= 31:
        raise ValueError(f"day must be between 1 and 31, got {day}")

    year, month = as_of.year, as_of.month
    for _ in range(2):
        first_of_next = (
            date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
        )
        last_day = (first_of_next - date(year, month, 1)).days
        candidate = date(year, month, min(day, last_day))
        if candidate >= as_of:
            return candidate
        year, month = first_of_next.year, first_of_next.month
    raise AssertionError("next_occurrence_of_day failed to converge within two months")


def upcoming_occurrences(
    series: list[RecurringSeries], *, from_date: date, days_ahead: int
) -> list[tuple[RecurringSeries, date]]:
    """Every expected occurrence of every series falling in the next `days_ahead` days.

    A series can recur more than once inside the window (a weekly series inside 30 days),
    so each expected date is returned separately rather than one per series.

    Raises:
        ValueError: if days_ahead < 1.
    """
    if days_ahead < 1:
        raise ValueError(f"days_ahead must be >= 1, got {days_ahead}")

    horizon = from_date + timedelta(days=days_ahead)
    expected: list[tuple[RecurringSeries, date]] = []
    for item in series:
        due = item.next_expected_on
        # A series whose next expected date has already passed (nothing imported since)
        # is rolled forward to the first still-future occurrence rather than reported as
        # overdue — this engine projects a schedule, it does not track payment status.
        while due < from_date:
            due = due + timedelta(days=item.interval_days)
        while due <= horizon:
            expected.append((item, due))
            due = due + timedelta(days=item.interval_days)
    return sorted(expected, key=lambda pair: pair[1])
