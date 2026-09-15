from datetime import date
from decimal import Decimal

import pytest

from app.domain.goals import (
    GoalRequirement,
    add_months,
    allocate_across_goals,
    assess_goal,
    months_between,
    months_to_target,
    required_monthly_contribution,
)


def test_required_contribution_without_interest_is_the_gap_divided_by_months() -> None:
    """Reference: R60,000 target, R12,000 held, 24 months, 0%.

    Source: hand calculation — (60000 - 12000) / 24 = 2000 exactly.
    """
    assert required_monthly_contribution(
        target_amount=Decimal("60000"),
        current_amount=Decimal("12000"),
        months_remaining=24,
    ) == Decimal("2000.00")


def test_required_contribution_with_interest_matches_the_annuity_formula() -> None:
    """Reference: R100,000 target, R20,000 held, 36 months, 7.2% nominal annual.

    Source: computed independently of this engine at 40 significant digits and
    cross-checked in IEEE-754 float, both giving 1877.4897742877...:
        i = 0.072/12 = 0.006
        (1+i)^36     = 1.2403016056345817894983978366543197583
        FV of held   = 20000 * 1.2403016... = 24806.0321126916...
        PMT          = (100000 - 24806.0321126916...) * 0.006 / (1.2403016... - 1)
                     = 1877.4897742877...
    Two independent arithmetic paths agreeing to 15 digits is the independence this
    figure rests on; the engine is not consulted for it.
    """
    assert required_monthly_contribution(
        target_amount=Decimal("100000"),
        current_amount=Decimal("20000"),
        months_remaining=36,
        annual_rate=Decimal("0.072"),
    ) == Decimal("1877.49")


def test_required_contribution_is_zero_when_the_goal_is_already_met() -> None:
    assert required_monthly_contribution(
        target_amount=Decimal("50000"),
        current_amount=Decimal("50000"),
        months_remaining=12,
    ) == Decimal("0.00")


def test_required_contribution_rejects_a_non_positive_horizon() -> None:
    with pytest.raises(ValueError, match="months_remaining"):
        required_monthly_contribution(
            target_amount=Decimal("1000"), current_amount=Decimal("0"), months_remaining=0
        )


def test_months_to_target_without_interest_is_the_gap_over_the_rate() -> None:
    assert (
        months_to_target(
            target_amount=Decimal("10000"),
            current_amount=Decimal("0"),
            monthly_contribution=Decimal("1000"),
        )
        == 10
    )


def test_months_to_target_returns_none_when_nothing_is_contributed() -> None:
    assert (
        months_to_target(
            target_amount=Decimal("10000"),
            current_amount=Decimal("0"),
            monthly_contribution=Decimal("0"),
        )
        is None
    )


def test_months_to_target_is_zero_when_already_met() -> None:
    assert (
        months_to_target(
            target_amount=Decimal("10000"),
            current_amount=Decimal("10000"),
            monthly_contribution=Decimal("500"),
        )
        == 0
    )


def test_interest_reaches_the_target_sooner_than_no_interest() -> None:
    without = months_to_target(
        target_amount=Decimal("100000"),
        current_amount=Decimal("50000"),
        monthly_contribution=Decimal("1000"),
    )
    with_interest = months_to_target(
        target_amount=Decimal("100000"),
        current_amount=Decimal("50000"),
        monthly_contribution=Decimal("1000"),
        annual_rate=Decimal("0.08"),
    )
    assert without is not None and with_interest is not None
    assert with_interest < without


def test_months_between_ignores_day_of_month() -> None:
    assert months_between(start=date(2026, 1, 31), end=date(2026, 4, 1)) == 3
    assert months_between(start=date(2026, 4, 1), end=date(2026, 1, 1)) == 0


def test_add_months_clamps_to_the_last_valid_day() -> None:
    assert add_months(start=date(2026, 1, 31), months=1) == date(2026, 2, 28)
    assert add_months(start=date(2026, 11, 30), months=1) == date(2026, 12, 30)
    assert add_months(start=date(2026, 12, 15), months=1) == date(2027, 1, 15)


def test_assess_goal_labels_an_unfundable_goal_with_its_shortfall() -> None:
    """specs/goals.md: an unachievable goal is stated as unachievable, with the gap."""
    assessment = assess_goal(
        target_amount=Decimal("120000"),
        current_amount=Decimal("0"),
        target_date=date(2027, 1, 1),
        as_of=date(2026, 1, 1),
        observed_monthly_rate=Decimal("2000"),
        available_cash_flow=Decimal("3000"),
    )

    assert assessment.required_monthly_contribution == Decimal("10000.00")
    assert assessment.is_achievable is False
    assert assessment.monthly_shortfall == Decimal("7000.00")
    assert assessment.date_slippage_months == 48  # 60 months at R2,000 against 12 allowed


def test_assess_goal_uses_observed_rate_not_the_required_rate_for_the_date() -> None:
    assessment = assess_goal(
        target_amount=Decimal("24000"),
        current_amount=Decimal("0"),
        target_date=date(2027, 1, 1),
        as_of=date(2026, 1, 1),
        observed_monthly_rate=Decimal("1000"),
        available_cash_flow=Decimal("5000"),
    )

    assert assessment.is_achievable is True  # R2,000/month is affordable
    assert assessment.projected_months == 24  # but at R1,000 observed it takes 24
    assert assessment.projected_achievement_date == date(2028, 1, 1)
    assert assessment.date_slippage_months == 12


def test_assess_goal_with_no_contributions_has_no_projected_date() -> None:
    assessment = assess_goal(
        target_amount=Decimal("24000"),
        current_amount=Decimal("0"),
        target_date=date(2027, 1, 1),
        as_of=date(2026, 1, 1),
        observed_monthly_rate=Decimal("0"),
        available_cash_flow=Decimal("0"),
    )

    assert assessment.projected_months is None
    assert assessment.projected_achievement_date is None
    assert assessment.is_achievable is False


def test_allocate_funds_goals_in_priority_order_and_reports_slippage() -> None:
    goals = [
        GoalRequirement(
            key="emergency",
            priority=1,
            required_monthly=Decimal("3000"),
            target_amount=Decimal("36000"),
            current_amount=Decimal("0"),
            months_remaining=12,
        ),
        GoalRequirement(
            key="holiday",
            priority=2,
            required_monthly=Decimal("2000"),
            target_amount=Decimal("24000"),
            current_amount=Decimal("0"),
            months_remaining=12,
        ),
    ]

    plan = allocate_across_goals(goals=goals, available_cash_flow=Decimal("4000"))

    assert plan.is_over_committed is True
    assert plan.total_required == Decimal("5000.00")
    emergency, holiday = plan.fundings
    assert emergency.funded_monthly == Decimal("3000.00")
    assert emergency.is_fully_funded is True
    assert emergency.slippage_months is None
    assert holiday.funded_monthly == Decimal("1000.00")
    assert holiday.is_fully_funded is False
    assert holiday.slippage_months == 12  # 24 months at R1,000 against 12 allowed


def test_allocate_with_ample_cash_flow_funds_everything() -> None:
    goals = [
        GoalRequirement(
            key="a",
            priority=1,
            required_monthly=Decimal("1000"),
            target_amount=Decimal("12000"),
            current_amount=Decimal("0"),
            months_remaining=12,
        ),
        GoalRequirement(
            key="b",
            priority=2,
            required_monthly=Decimal("500"),
            target_amount=Decimal("6000"),
            current_amount=Decimal("0"),
            months_remaining=12,
        ),
    ]

    plan = allocate_across_goals(goals=goals, available_cash_flow=Decimal("5000"))

    assert plan.is_over_committed is False
    assert all(f.is_fully_funded for f in plan.fundings)
    assert all(f.slippage_months is None for f in plan.fundings)


def test_allocate_with_negative_cash_flow_funds_nothing() -> None:
    goals = [
        GoalRequirement(
            key="a",
            priority=1,
            required_monthly=Decimal("1000"),
            target_amount=Decimal("12000"),
            current_amount=Decimal("0"),
            months_remaining=12,
        )
    ]

    plan = allocate_across_goals(goals=goals, available_cash_flow=Decimal("-2500"))

    assert plan.fundings[0].funded_monthly == Decimal("0.00")
    assert plan.fundings[0].is_fully_funded is False
    assert plan.fundings[0].slippage_months is None  # never reached: no date to slip to
