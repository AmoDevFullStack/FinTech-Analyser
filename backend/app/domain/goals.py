"""Goal progress, required contribution, achievability, and competition between goals.

See specs/goals.md. The spec's central demand is honesty: "Indefinite progress bars on
unachievable goals are a way of avoiding telling the user something true." So every
function here returns the gap when there is one, and `None` where a date genuinely does
not exist at the observed rate, rather than a comfortable large number.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

CENTS = Decimal("0.01")
TWELVE = Decimal("12")
MAX_PROJECTION_MONTHS = 1200  # 100 years; beyond this a date is not a plan.


def _quantise(value: Decimal) -> Decimal:
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)


def months_between(*, start: date, end: date) -> int:
    """Whole calendar months from `start` to `end`, floored at zero.

    Day-of-month is deliberately ignored: a goal dated the 1st and one dated the 28th of
    the same month are funded by the same number of monthly contributions.
    """
    months = (end.year - start.year) * 12 + (end.month - start.month)
    return max(0, months)


def add_months(*, start: date, months: int) -> date:
    """`start` advanced by `months`, clamped to the last valid day of the target month.

    Raises:
        ValueError: if months < 0.
    """
    if months < 0:
        raise ValueError(f"months must be >= 0, got {months}")

    total = start.month - 1 + months
    year = start.year + total // 12
    month = total % 12 + 1
    if month == 12:
        last_day = 31
    else:
        last_day = (date(year + (month // 12), month % 12 + 1, 1) - date(year, month, 1)).days
    return date(year, month, min(start.day, last_day))


def required_monthly_contribution(
    *,
    target_amount: Decimal,
    current_amount: Decimal,
    months_remaining: int,
    annual_rate: Decimal = Decimal("0"),
) -> Decimal:
    """The monthly contribution that reaches `target_amount` by the target date.

    Formula:
        i = annual_rate / 12
        i == 0:  PMT = (target - current) / n
        i  > 0:  PMT = (target - current * (1 + i) ** n) * i / ((1 + i) ** n - 1)

        The second form is the standard future-value-of-an-annuity solved for the payment,
        crediting the balance already held with the interest it earns over the term — per
        specs/goals.md, "adjusted for interest where the linked account bears it".

    Assumptions:
        - Contributions are made at period end, monthly, in equal amounts.
        - The rate is nominal annual, compounded monthly, and fixed for the term.
        - A goal already at or beyond its target requires nothing: zero, not a negative
          number, since a negative "contribution" is a withdrawal and not what was asked.

    Rounding:
        Two places, ROUND_HALF_UP — this is a figure shown to a user and paid in cents.

    Raises:
        ValueError: if months_remaining < 1, target_amount <= 0, or annual_rate < 0.
    """
    if months_remaining < 1:
        raise ValueError(f"months_remaining must be >= 1, got {months_remaining}")
    if target_amount <= 0:
        raise ValueError(f"target_amount must be positive, got {target_amount}")
    if annual_rate < 0:
        raise ValueError(f"annual_rate must be >= 0, got {annual_rate}")

    if current_amount >= target_amount:
        return Decimal("0.00")

    monthly_rate = annual_rate / TWELVE
    if monthly_rate == 0:
        return _quantise((target_amount - current_amount) / months_remaining)

    growth = (1 + monthly_rate) ** months_remaining
    future_value_of_current = current_amount * growth
    if future_value_of_current >= target_amount:
        # Interest alone gets there — the user need contribute nothing further.
        return Decimal("0.00")
    return _quantise((target_amount - future_value_of_current) * monthly_rate / (growth - 1))


def months_to_target(
    *,
    target_amount: Decimal,
    current_amount: Decimal,
    monthly_contribution: Decimal,
    annual_rate: Decimal = Decimal("0"),
) -> int | None:
    """Months until the balance reaches the target at a given contribution rate.

    Formula (iterated rather than solved with a logarithm, so every intermediate stays
    `Decimal` and the result matches a month-by-month statement exactly):
        balance_0 = current
        balance_t = balance_{t-1} * (1 + annual_rate / 12) + monthly_contribution
        return the first t where balance_t >= target

    Assumptions:
        - Interest credits before the contribution each month (period-end payment).
        - Returns 0 when the balance already meets the target.
        - Returns None when the target is not reached within 100 years — at the observed
          rate the date does not exist, and inventing one would be the "indefinite
          progress bar" specs/goals.md rejects.

    Raises:
        ValueError: if target_amount <= 0, monthly_contribution < 0, or annual_rate < 0.
    """
    if target_amount <= 0:
        raise ValueError(f"target_amount must be positive, got {target_amount}")
    if monthly_contribution < 0:
        raise ValueError(
            f"monthly_contribution must be >= 0, got {monthly_contribution}"
        )
    if annual_rate < 0:
        raise ValueError(f"annual_rate must be >= 0, got {annual_rate}")

    if current_amount >= target_amount:
        return 0
    if monthly_contribution == 0 and annual_rate == 0:
        return None

    monthly_rate = annual_rate / TWELVE
    balance = current_amount
    for month in range(1, MAX_PROJECTION_MONTHS + 1):
        balance = balance * (1 + monthly_rate) + monthly_contribution
        if balance >= target_amount:
            return month
    return None


@dataclass(frozen=True, slots=True)
class GoalAssessment:
    target_amount: Decimal
    current_amount: Decimal
    months_remaining: int
    required_monthly_contribution: Decimal
    observed_monthly_rate: Decimal
    projected_months: int | None
    projected_achievement_date: date | None
    is_achievable: bool
    monthly_shortfall: Decimal
    date_slippage_months: int | None


def assess_goal(
    *,
    target_amount: Decimal,
    current_amount: Decimal,
    target_date: date,
    as_of: date,
    observed_monthly_rate: Decimal,
    available_cash_flow: Decimal,
    annual_rate: Decimal = Decimal("0"),
) -> GoalAssessment:
    """Assess one goal against observed behaviour rather than stated intent.

    Formula:
        months_remaining = whole months from as_of to target_date
        required         = required_monthly_contribution(...)
        projected_months = months_to_target(... at observed_monthly_rate ...)
        shortfall        = max(0, required - available_cash_flow)
        slippage         = projected_months - months_remaining, when projected_months
                           exists and exceeds months_remaining

    Assumptions:
        - `observed_monthly_rate` is the user's actual recent contribution rate, supplied
          by the caller — specs/goals.md: "Projections use observed behaviour, not intent."
        - Achievability is judged against `available_cash_flow`, not against the observed
          rate: a goal the user could fund but currently isn't is achievable, and the
          slippage figure is what says they are not on track for it.
        - A goal whose target date has passed has zero months remaining and is not
          achievable unless it is already met.

    Rounding:
        Money to two places, ROUND_HALF_UP. Months are whole numbers throughout.

    Raises:
        ValueError: if target_amount <= 0, observed_monthly_rate < 0, or annual_rate < 0.
    """
    if target_amount <= 0:
        raise ValueError(f"target_amount must be positive, got {target_amount}")
    if observed_monthly_rate < 0:
        raise ValueError(
            f"observed_monthly_rate must be >= 0, got {observed_monthly_rate}"
        )
    if annual_rate < 0:
        raise ValueError(f"annual_rate must be >= 0, got {annual_rate}")

    months_remaining = months_between(start=as_of, end=target_date)
    already_met = current_amount >= target_amount

    if months_remaining < 1:
        required = Decimal("0.00") if already_met else _quantise(target_amount - current_amount)
    else:
        required = required_monthly_contribution(
            target_amount=target_amount,
            current_amount=current_amount,
            months_remaining=months_remaining,
            annual_rate=annual_rate,
        )

    projected_months = months_to_target(
        target_amount=target_amount,
        current_amount=current_amount,
        monthly_contribution=observed_monthly_rate,
        annual_rate=annual_rate,
    )
    projected_date = (
        add_months(start=as_of, months=projected_months)
        if projected_months is not None
        else None
    )

    is_achievable = already_met or (months_remaining >= 1 and required <= available_cash_flow)
    shortfall = Decimal("0.00") if is_achievable else _quantise(
        max(Decimal("0"), required - available_cash_flow)
    )
    slippage = (
        projected_months - months_remaining
        if projected_months is not None and projected_months > months_remaining
        else None
    )

    return GoalAssessment(
        target_amount=target_amount,
        current_amount=current_amount,
        months_remaining=months_remaining,
        required_monthly_contribution=required,
        observed_monthly_rate=observed_monthly_rate,
        projected_months=projected_months,
        projected_achievement_date=projected_date,
        is_achievable=is_achievable,
        monthly_shortfall=shortfall,
        date_slippage_months=slippage,
    )


@dataclass(frozen=True, slots=True)
class GoalRequirement:
    key: str
    priority: int
    required_monthly: Decimal
    target_amount: Decimal
    current_amount: Decimal
    months_remaining: int
    annual_rate: Decimal = Decimal("0")


@dataclass(frozen=True, slots=True)
class GoalFunding:
    key: str
    priority: int
    required_monthly: Decimal
    funded_monthly: Decimal
    is_fully_funded: bool
    slippage_months: int | None


@dataclass(frozen=True, slots=True)
class FundingPlan:
    total_required: Decimal
    available_cash_flow: Decimal
    fundings: tuple[GoalFunding, ...]
    is_over_committed: bool


def allocate_across_goals(
    *, goals: list[GoalRequirement], available_cash_flow: Decimal
) -> FundingPlan:
    """Fund goals in priority order from one pool of cash, and quantify what slips.

    Formula:
        Goals sorted by priority ascending (1 funds first). Each takes the lesser of its
        required monthly contribution and whatever remains of `available_cash_flow`. For a
        goal funded below its requirement, slippage is:
            months_to_target(at funded_monthly) - months_remaining
        and is None when the goal is fully funded, and None when no funding at all means
        the target is never reached (there is no date to slip to — `is_fully_funded` is
        False and `funded_monthly` is zero, which is the honest statement).

    Assumptions:
        - "Goals are not modelled in isolation because they are not funded in isolation"
          (specs/goals.md) — hence one shared pool rather than per-goal maths.
        - Ties in priority keep the caller's ordering, so the result is deterministic.
        - A negative `available_cash_flow` funds nothing; it is not an error, it is a user
          whose outgoings already exceed income.

    Rounding:
        Money to two places, ROUND_HALF_UP.

    Raises:
        ValueError: if any goal's required_monthly is negative.
    """
    for goal in goals:
        if goal.required_monthly < 0:
            raise ValueError(
                f"required_monthly must be >= 0 for {goal.key!r}, got {goal.required_monthly}"
            )

    ordered = sorted(enumerate(goals), key=lambda pair: (pair[1].priority, pair[0]))
    remaining = max(Decimal("0"), available_cash_flow)
    total_required = sum((g.required_monthly for g in goals), Decimal("0"))

    fundings: list[GoalFunding] = []
    for _, goal in ordered:
        funded = min(goal.required_monthly, remaining)
        remaining -= funded
        fully_funded = funded >= goal.required_monthly

        slippage: int | None = None
        if not fully_funded and goal.target_amount > goal.current_amount:
            projected = months_to_target(
                target_amount=goal.target_amount,
                current_amount=goal.current_amount,
                monthly_contribution=funded,
                annual_rate=goal.annual_rate,
            )
            if projected is not None and projected > goal.months_remaining:
                slippage = projected - goal.months_remaining

        fundings.append(
            GoalFunding(
                key=goal.key,
                priority=goal.priority,
                required_monthly=_quantise(goal.required_monthly),
                funded_monthly=_quantise(funded),
                is_fully_funded=fully_funded,
                slippage_months=slippage,
            )
        )

    return FundingPlan(
        total_required=_quantise(total_required),
        available_cash_flow=_quantise(available_cash_flow),
        fundings=tuple(fundings),
        is_over_committed=total_required > available_cash_flow,
    )
