"""Recommendation rules. See specs/recommendations.md.

"Recommendations are produced by rules over computed results. The model phrases them; it
does not originate them. A suggestion the system cannot justify with a number is not a
suggestion, it is an opinion."

Every rule here returns a quantified benefit in rand or it returns nothing. As with
app/domain/risk.py, the user-facing sentence is composed in the service layer — these
functions produce figures and a rule identifier, never prose, and never the word "should".
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from app.domain.debt_payoff import DebtInput, avalanche_schedule

CENTS = Decimal("0.01")
RATE_PLACES = Decimal("0.000001")

MAX_ACTIVE = 5  # "A list of twenty recommendations is a list nobody acts on."
EMERGENCY_COVER_TARGET_MONTHS = Decimal("3")
EMERGENCY_COVER_BUILD_MONTHS = 12
UTILISATION_TRIGGER = Decimal("0.70")
UTILISATION_TARGET = Decimal("0.30")
SUBSCRIPTION_SHARE_THRESHOLD = Decimal("0.10")
REFINANCE_RATE_MARGIN = Decimal("0.03")
SURPLUS_PERSISTENCE_MONTHS = 3


class Rule(str, enum.Enum):
    REDIRECT_TO_HIGHEST_RATE_DEBT = "redirect_to_highest_rate_debt"
    BUILD_EMERGENCY_COVER = "build_emergency_cover"
    SUBSCRIPTION_AUDIT = "subscription_audit"
    UTILISATION_REDUCTION = "utilisation_reduction"
    GOAL_CONTRIBUTION_SHORTFALL = "goal_contribution_shortfall"
    REFINANCE_CANDIDATE = "refinance_candidate"
    SURPLUS_NOT_ALLOCATED = "surplus_not_allocated"


@dataclass(frozen=True, slots=True)
class Recommendation:
    rule: Rule
    benefit_amount: Decimal
    benefit_kind: str  # "interest_saved" | "annual_cost" | "monthly_amount" | ...
    computation_reference: str
    details: dict[str, str] = field(default_factory=dict)


def _quantise(value: Decimal) -> Decimal:
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)


def redirect_to_highest_rate_debt(
    *, debts: list[DebtInput], monthly_surplus: Decimal, computation_reference: str
) -> Recommendation | None:
    """Interest and months saved by directing an existing surplus at the highest rate.

    Formula:
        baseline = avalanche(debts, total = sum of minimum payments)
        with_surplus = avalanche(debts, total = sum of minimums + monthly_surplus)
        interest_saved = baseline.total_interest - with_surplus.total_interest
        months_saved   = baseline.months_to_free - with_surplus.months_to_free

    Both runs use the same engine and the same ordering, so the difference is attributable
    to the surplus alone.

    Assumptions:
        - Triggers only with a surplus and more than one debt, per the spec's table: with
          a single debt there is no "highest rate" to redirect toward, and the surplus
          simply pays it faster, which the what-if on that debt already reports.
        - A surplus of zero or less is not a recommendation, it is a different problem.

    Rounding: two places, ROUND_HALF_UP.
    """
    if monthly_surplus <= 0 or len(debts) < 2:
        return None

    minimums = sum((d.minimum_payment for d in debts), Decimal("0"))
    baseline = avalanche_schedule(debts, minimums)
    accelerated = avalanche_schedule(debts, minimums + monthly_surplus)

    interest_saved = baseline.total_interest - accelerated.total_interest
    months_saved = baseline.months_to_free - accelerated.months_to_free
    if interest_saved <= 0:
        return None

    target = max(debts, key=lambda d: d.annual_rate)
    return Recommendation(
        rule=Rule.REDIRECT_TO_HIGHEST_RATE_DEBT,
        benefit_amount=_quantise(interest_saved),
        benefit_kind="interest_saved",
        computation_reference=computation_reference,
        details={
            "monthly_surplus": str(_quantise(monthly_surplus)),
            "months_saved": str(months_saved),
            "target_debt_id": target.id,
            "target_annual_rate": str(target.annual_rate),
            "baseline_total_interest": str(_quantise(baseline.total_interest)),
            "accelerated_total_interest": str(_quantise(accelerated.total_interest)),
        },
    )


def build_emergency_cover(
    *,
    liquid_savings: Decimal,
    monthly_essential: Decimal,
    computation_reference: str,
    target_months: Decimal = EMERGENCY_COVER_TARGET_MONTHS,
    build_months: int = EMERGENCY_COVER_BUILD_MONTHS,
) -> Recommendation | None:
    """The monthly amount that reaches three months of cover within a year.

    Formula:
        required_balance = monthly_essential * target_months
        gap              = required_balance - liquid_savings
        monthly_amount   = gap / build_months

    Assumptions:
        - `build_months` is the horizon over which the gap is closed. Twelve is a choice,
          not a derivation, and it is stated rather than hidden so a user who disagrees
          can see what the figure rests on.
        - A user with no essential spending has no cover requirement to compute.

    Rounding: two places, ROUND_HALF_UP.

    Raises:
        ValueError: if target_months <= 0 or build_months < 1.
    """
    if target_months <= 0:
        raise ValueError(f"target_months must be positive, got {target_months}")
    if build_months < 1:
        raise ValueError(f"build_months must be >= 1, got {build_months}")
    if monthly_essential <= 0:
        return None

    required_balance = monthly_essential * target_months
    gap = required_balance - liquid_savings
    if gap <= 0:
        return None

    current_cover = (liquid_savings / monthly_essential).quantize(
        RATE_PLACES, rounding=ROUND_HALF_UP
    )
    return Recommendation(
        rule=Rule.BUILD_EMERGENCY_COVER,
        benefit_amount=_quantise(gap),
        benefit_kind="cover_gap",
        computation_reference=computation_reference,
        details={
            "monthly_amount": str(_quantise(gap / build_months)),
            "current_cover_months": str(current_cover),
            "target_months": str(target_months),
            "build_months": str(build_months),
            "required_balance": str(_quantise(required_balance)),
        },
    )


@dataclass(frozen=True, slots=True)
class SubscriptionCandidate:
    key: str
    monthly_equivalent: Decimal
    annual_cost: Decimal
    last_charged_on: str


def subscription_audit(
    *,
    candidates: list[SubscriptionCandidate],
    monthly_discretionary: Decimal,
    computation_reference: str,
    share_threshold: Decimal = SUBSCRIPTION_SHARE_THRESHOLD,
) -> Recommendation | None:
    """The recurring discretionary series costing more than a tenth of discretionary spend.

    Formula:
        share_s = monthly_equivalent_s / monthly_discretionary
        flagged where share_s > share_threshold; the largest annual cost is reported

    Assumptions:
        - Candidates are recurring series already detected by app/domain/recurrence.py and
          already filtered to discretionary spending by the caller; this rule decides only
          whether one is large enough to be worth a user's attention.
        - The system reports the cost. It does not cancel anything: "a destructive
          external action requires the user."

    Rounding: two places, ROUND_HALF_UP.

    Raises:
        ValueError: if share_threshold <= 0.
    """
    if share_threshold <= 0:
        raise ValueError(f"share_threshold must be positive, got {share_threshold}")
    if monthly_discretionary <= 0 or not candidates:
        return None

    qualifying = [
        c
        for c in candidates
        if (c.monthly_equivalent / monthly_discretionary) > share_threshold
    ]
    if not qualifying:
        return None

    largest = max(qualifying, key=lambda c: c.annual_cost)
    share = (largest.monthly_equivalent / monthly_discretionary).quantize(
        RATE_PLACES, rounding=ROUND_HALF_UP
    )
    return Recommendation(
        rule=Rule.SUBSCRIPTION_AUDIT,
        benefit_amount=_quantise(largest.annual_cost),
        benefit_kind="annual_cost",
        computation_reference=computation_reference,
        details={
            "series": largest.key,
            "monthly_equivalent": str(_quantise(largest.monthly_equivalent)),
            "share_of_discretionary": str(share),
            "last_charged_on": largest.last_charged_on,
            "candidate_count": str(len(qualifying)),
        },
    )


def utilisation_reduction(
    *,
    revolving_balance: Decimal,
    credit_limit: Decimal,
    computation_reference: str,
    trigger: Decimal = UTILISATION_TRIGGER,
    target: Decimal = UTILISATION_TARGET,
) -> Recommendation | None:
    """The repayment that brings revolving utilisation from above 70% to below 30%.

    Formula:
        utilisation = revolving_balance / credit_limit
        flagged where utilisation > trigger
        amount = revolving_balance - (credit_limit * target)

    Rounding: amount two places, ratio six, both ROUND_HALF_UP.

    Raises:
        ValueError: if credit_limit < 0, revolving_balance < 0, or target >= trigger.
    """
    if revolving_balance < 0:
        raise ValueError(f"revolving_balance must be >= 0, got {revolving_balance}")
    if credit_limit < 0:
        raise ValueError(f"credit_limit must be >= 0, got {credit_limit}")
    if target >= trigger:
        raise ValueError(f"target ({target}) must be below trigger ({trigger})")
    if credit_limit == 0:
        return None

    utilisation = revolving_balance / credit_limit
    if utilisation <= trigger:
        return None

    amount = revolving_balance - (credit_limit * target)
    return Recommendation(
        rule=Rule.UTILISATION_REDUCTION,
        benefit_amount=_quantise(amount),
        benefit_kind="repayment_amount",
        computation_reference=computation_reference,
        details={
            "utilisation": str(utilisation.quantize(RATE_PLACES, rounding=ROUND_HALF_UP)),
            "target": str(target),
            "revolving_balance": str(_quantise(revolving_balance)),
            "credit_limit": str(_quantise(credit_limit)),
        },
    )


@dataclass(frozen=True, slots=True)
class GoalShortfall:
    goal_id: str
    name: str
    required_monthly: Decimal
    observed_monthly: Decimal
    slippage_months: int | None


def goal_contribution_shortfall(
    *, shortfalls: list[GoalShortfall], computation_reference: str
) -> Recommendation | None:
    """The monthly gap between what a goal requires and what it is actually receiving.

    Formula:
        gap_g = required_monthly_g - observed_monthly_g
        the largest positive gap is reported, with that goal's date slippage

    Assumptions:
        - Gaps arrive already computed by app/domain/goals.py; this rule selects and
          quantifies rather than recomputing, so one engine owns goal arithmetic.

    Rounding: two places, ROUND_HALF_UP.
    """
    gaps = [
        (s, s.required_monthly - s.observed_monthly)
        for s in shortfalls
        if s.required_monthly > s.observed_monthly
    ]
    if not gaps:
        return None

    goal, gap = max(gaps, key=lambda pair: pair[1])
    details = {
        "goal_id": goal.goal_id,
        "goal_name": goal.name,
        "required_monthly": str(_quantise(goal.required_monthly)),
        "observed_monthly": str(_quantise(goal.observed_monthly)),
    }
    if goal.slippage_months is not None:
        details["slippage_months"] = str(goal.slippage_months)

    return Recommendation(
        rule=Rule.GOAL_CONTRIBUTION_SHORTFALL,
        benefit_amount=_quantise(gap),
        benefit_kind="monthly_gap",
        computation_reference=computation_reference,
        details=details,
    )


def refinance_candidate(
    *,
    debts: list[DebtInput],
    computation_reference: str,
    margin: Decimal = REFINANCE_RATE_MARGIN,
) -> Recommendation | None:
    """A debt whose rate sits materially above the user's own balance-weighted average.

    Formula:
        weighted_average = sum(balance_d * rate_d) / sum(balance_d)
        candidate        = the debt with the highest rate, where
                           rate_candidate - weighted_average > margin
        alternative_rate = weighted_average
        annual_saving    = balance_candidate * (rate_candidate - weighted_average)

    Assumptions:
        - The alternative rate is the user's own weighted average, not a market rate: the
          system does not know what any lender would offer, and "no recommendation
          suggests a product, provider, or instrument."
        - The saving is stated as the first year's interest difference on the current
          balance, which is an upper bound that decays as the balance amortises. That is
          why it is reported as an annual interest difference rather than a total saving.

    Rounding: money two places, rates six, both ROUND_HALF_UP.

    Raises:
        ValueError: if margin <= 0.
    """
    if margin <= 0:
        raise ValueError(f"margin must be positive, got {margin}")

    active = [d for d in debts if d.current_balance > 0]
    if len(active) < 2:
        return None

    total_balance = sum((d.current_balance for d in active), Decimal("0"))
    if total_balance <= 0:
        return None

    weighted_average = (
        sum((d.current_balance * d.annual_rate for d in active), Decimal("0")) / total_balance
    )
    candidate = max(active, key=lambda d: d.annual_rate)
    excess = candidate.annual_rate - weighted_average
    if excess <= margin:
        return None

    annual_saving = candidate.current_balance * excess
    return Recommendation(
        rule=Rule.REFINANCE_CANDIDATE,
        benefit_amount=_quantise(annual_saving),
        benefit_kind="annual_interest_difference",
        computation_reference=computation_reference,
        details={
            "debt_id": candidate.id,
            "debt_annual_rate": str(
                candidate.annual_rate.quantize(RATE_PLACES, rounding=ROUND_HALF_UP)
            ),
            "weighted_average_rate": str(
                weighted_average.quantize(RATE_PLACES, rounding=ROUND_HALF_UP)
            ),
            "balance": str(_quantise(candidate.current_balance)),
        },
    )


def surplus_not_allocated(
    *,
    monthly_surpluses: list[Decimal],
    computation_reference: str,
    persistence_months: int = SURPLUS_PERSISTENCE_MONTHS,
    annual_rate_if_saved: Decimal = Decimal("0.07"),
) -> Recommendation | None:
    """A surplus that has persisted unallocated for three months or more.

    Formula:
        qualifies when the last `persistence_months` months all show a positive surplus
        amount           = the smallest of those surpluses (the reliably available part)
        annual_if_saved  = amount * 12 * (1 + annual_rate_if_saved / 12 compounded) - ...
                           reported simply as amount * 12 plus one year's interest at
                           annual_rate_if_saved on the average balance held

    The smallest of the recent surpluses is used rather than the average, because the
    figure is meant to be one the user can commit every month without it failing in the
    leanest of them.

    Assumptions:
        - `monthly_surpluses` is chronological, oldest first.
        - `annual_rate_if_saved` is an illustrative rate for the "effect if saved"
          figure the spec asks for, and is stated in the output so it can be argued with.

    Rounding: two places, ROUND_HALF_UP.

    Raises:
        ValueError: if persistence_months < 2 or annual_rate_if_saved < 0.
    """
    if persistence_months < 2:
        raise ValueError(f"persistence_months must be >= 2, got {persistence_months}")
    if annual_rate_if_saved < 0:
        raise ValueError(
            f"annual_rate_if_saved must be >= 0, got {annual_rate_if_saved}"
        )

    if len(monthly_surpluses) < persistence_months:
        return None
    recent = monthly_surpluses[-persistence_months:]
    if any(value <= 0 for value in recent):
        return None

    amount = min(recent)
    annual_contributions = amount * Decimal("12")
    # Interest on the average balance held over the year: contributions accumulate
    # linearly, so the average balance is roughly half the year-end total.
    interest = (annual_contributions / Decimal("2")) * annual_rate_if_saved

    return Recommendation(
        rule=Rule.SURPLUS_NOT_ALLOCATED,
        benefit_amount=_quantise(annual_contributions + interest),
        benefit_kind="annual_amount_if_saved",
        computation_reference=computation_reference,
        details={
            "monthly_amount": str(_quantise(amount)),
            "months_observed": str(len(recent)),
            "annual_contributions": str(_quantise(annual_contributions)),
            "interest_if_saved": str(_quantise(interest)),
            "assumed_annual_rate": str(annual_rate_if_saved),
        },
    )


def rank_and_cap(
    recommendations: list[Recommendation], *, maximum: int = MAX_ACTIVE
) -> list[Recommendation]:
    """Order by quantified benefit, descending, and keep at most `maximum`.

    Raises:
        ValueError: if maximum < 1.
    """
    if maximum < 1:
        raise ValueError(f"maximum must be >= 1, got {maximum}")
    return sorted(recommendations, key=lambda r: r.benefit_amount, reverse=True)[:maximum]
