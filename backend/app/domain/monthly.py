"""Month-by-month arithmetic: what a month was, and how it differs from the one before.

Every other engine in this package answers a question about a projection. This one answers
a question about the past — "what did July actually look like next to June" — which the
product could not answer at all: transactions were listed and totalled over a window, never
compared across calendar months.

Two separate views of a month, deliberately kept apart:

- `MonthTotals` is the *analysis* view: income, essential, discretionary, saving and debt
  service, with internal transfers excluded. Moving R5,000 from a cheque account to a
  savings account is not income and not spending, and counting it as both is the corruption
  specs/transactions.md step 4 exists to prevent.
- `MonthMovement` is the *cash* view: everything that moved through the account, transfers
  included, because a balance does not care why money left. This is the one that reconciles
  to a bank statement, and mixing the two is how a month's figures stop tying out.

Sign convention follows docs/database.md §3 and `SpendingInsightService`: income keeps its
sign so a salary reversal reduces income, while every spending kind is the positive
magnitude that left the account.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

CENTS = Decimal("0.01")

#: Rates and ratios are six places, per docs/database.md §1.
RATE = Decimal("0.000001")


def _quantise(value: Decimal) -> Decimal:
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)


def _quantise_rate(value: Decimal) -> Decimal:
    return value.quantize(RATE, rounding=ROUND_HALF_UP)


def _validate_month(month: str) -> None:
    if len(month) != 7 or month[4] != "-" or not (month[:4] + month[5:]).isdigit():
        raise ValueError(f"month must be a YYYY-MM string, got {month!r}")


@dataclass(frozen=True, slots=True)
class MonthTotals:
    """One calendar month's flows, transfers excluded.

    `net` is what the month left over: income less everything that went out of it. It is
    negative in a month that spent more than it earned, and that is a real figure, never
    clamped.
    """

    month: str
    income: Decimal
    essential: Decimal
    discretionary: Decimal
    saving: Decimal
    debt_service: Decimal

    @property
    def spending(self) -> Decimal:
        """Everything that left, whatever it was for.

        Saving is included: a month that put R3,000 away had R3,000 less available, and a
        spending figure that hides it overstates what was free.
        """
        return _quantise(
            self.essential + self.discretionary + self.saving + self.debt_service
        )

    @property
    def net(self) -> Decimal:
        return _quantise(self.income - self.spending)


@dataclass(frozen=True, slots=True)
class MonthMovement:
    """One calendar month of cash across an account, transfers included.

    `inflow` and `outflow` are both positive magnitudes: what arrived, and what left.
    """

    month: str
    inflow: Decimal
    outflow: Decimal

    @property
    def net(self) -> Decimal:
        return _quantise(self.inflow - self.outflow)


@dataclass(frozen=True, slots=True)
class MonthBalance:
    """What the account was worth at each end of one month."""

    month: str
    opening: Decimal
    inflow: Decimal
    outflow: Decimal
    closing: Decimal


@dataclass(frozen=True, slots=True)
class MetricChange:
    """One figure, this month against last."""

    metric: str
    previous: Decimal
    current: Decimal
    change: Decimal
    #: `None` when the previous month was zero. The change from nothing to something has no
    #: percentage, and reporting one — or a 0% that reads as "no change" — would be a figure
    #: the data does not support.
    percentage_change: Decimal | None


@dataclass(frozen=True, slots=True)
class MonthComparison:
    month: str
    previous_month: str | None
    totals: MonthTotals
    changes: tuple[MetricChange, ...]


def month_totals(
    *,
    month: str,
    income: Decimal,
    essential: Decimal,
    discretionary: Decimal,
    saving: Decimal,
    debt_service: Decimal,
) -> MonthTotals:
    """Build one month's totals.

    Formula:
        spending = essential + discretionary + saving + debt_service
        net      = income - spending

    Assumptions:
        - The caller has already excluded internal transfers and soft-deleted rows.
        - Spending kinds arrive as positive magnitudes; income keeps its sign, so a month
          whose only salary line was reversed reports negative income rather than zero.

    Rounding:
        Each field quantised to two places with ROUND_HALF_UP. `spending` and `net` are
        derived from the quantised fields, so the parts always sum to the whole.

    Raises:
        ValueError: if `month` is not a YYYY-MM string, or a spending kind is negative. A
            negative spending kind means the sign convention was applied twice upstream,
            which is a bug rather than a number to pass along.
    """
    _validate_month(month)
    for name, value in (
        ("essential", essential),
        ("discretionary", discretionary),
        ("saving", saving),
        ("debt_service", debt_service),
    ):
        if value < 0:
            raise ValueError(f"{name} must be >= 0, got {value}")

    return MonthTotals(
        month=month,
        income=_quantise(income),
        essential=_quantise(essential),
        discretionary=_quantise(discretionary),
        saving=_quantise(saving),
        debt_service=_quantise(debt_service),
    )


def compare_months(
    *, current: MonthTotals, previous: MonthTotals | None
) -> MonthComparison:
    """Every figure of `current` against the same figure of `previous`.

    Formula:
        change            = current - previous
        percentage_change = change / |previous|, where previous != 0

    Assumptions:
        - `previous` is normally the immediately preceding calendar month, but any other
          month is allowed: comparing July against last July is a real question, and the
          months reported are whichever were passed.
        - With no previous month, `changes` is empty rather than a list of changes from
          zero. A first month did not grow infinitely; it has nothing to compare to.

    Rounding:
        Changes quantised to two places, percentages to six, per docs/database.md §1.

    Raises:
        ValueError: if `current` and `previous` are the same month.
    """
    if previous is not None and previous.month == current.month:
        raise ValueError(f"cannot compare month {current.month} against itself")

    if previous is None:
        return MonthComparison(
            month=current.month, previous_month=None, totals=current, changes=()
        )

    changes = tuple(
        _change(metric, getattr(previous, metric), getattr(current, metric))
        for metric in ("income", "essential", "discretionary", "saving", "debt_service")
    ) + (
        _change("spending", previous.spending, current.spending),
        _change("net", previous.net, current.net),
    )

    return MonthComparison(
        month=current.month,
        previous_month=previous.month,
        totals=current,
        changes=changes,
    )


def _change(metric: str, previous: Decimal, current: Decimal) -> MetricChange:
    change = current - previous
    percentage = None if previous == 0 else _quantise_rate(change / abs(previous))
    return MetricChange(
        metric=metric,
        previous=_quantise(previous),
        current=_quantise(current),
        change=_quantise(change),
        percentage_change=percentage,
    )


def balance_history(
    *, closing_balance: Decimal, movements: Sequence[MonthMovement]
) -> tuple[MonthBalance, ...]:
    """Walk a known balance backwards to say what the account held at each month end.

    An account stores one figure: what it is worth now. A statement covering March to July
    says what moved in between, and the two together are enough to say what it was worth at
    the end of each of those months. Backwards from the known present is the only direction
    available — an opening balance for the first month is precisely what is not known.

    Formula, over consecutive months in ascending order, starting from the last:
        closing(last)  = closing_balance
        opening(m)     = closing(m) - (inflow(m) - outflow(m))
        closing(m - 1) = opening(m)

    Assumptions:
        - `movements` are consecutive calendar months in ascending order and include every
          transaction that touched the account, transfers among them. A month with no
          transactions still belongs in the sequence as a zero movement; leaving it out
          would silently join two non-adjacent months.
        - `closing_balance` is the balance at the end of the final month given. Passing
          today's balance with a window that ends earlier dates the whole series by
          whatever has happened since, which is why the caller chooses the window.

    Rounding:
        Each opening and closing quantised to two places with ROUND_HALF_UP.

    Raises:
        ValueError: if a month is not YYYY-MM, the months are not ascending, or one repeats.
    """
    months = [movement.month for movement in movements]
    for month in months:
        _validate_month(month)
    if months != sorted(months):
        raise ValueError(f"movements must be in ascending month order, got {months}")
    if len(set(months)) != len(months):
        raise ValueError(f"movements repeats a month: {months}")

    balances: list[MonthBalance] = []
    closing = closing_balance
    for movement in reversed(movements):
        opening = closing - movement.net
        balances.append(
            MonthBalance(
                month=movement.month,
                opening=_quantise(opening),
                inflow=_quantise(movement.inflow),
                outflow=_quantise(movement.outflow),
                closing=_quantise(closing),
            )
        )
        closing = opening

    return tuple(reversed(balances))
