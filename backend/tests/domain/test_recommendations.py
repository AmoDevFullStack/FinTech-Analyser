from decimal import Decimal

import pytest

from app.domain.debt_payoff import DebtInput
from app.domain.recommendations import (
    GoalShortfall,
    Rule,
    SubscriptionCandidate,
    build_emergency_cover,
    goal_contribution_shortfall,
    rank_and_cap,
    redirect_to_highest_rate_debt,
    refinance_candidate,
    subscription_audit,
    surplus_not_allocated,
    utilisation_reduction,
)

REF = "forecast:f-1"


def _debts() -> list[DebtInput]:
    return [
        DebtInput(
            id="card",
            current_balance=Decimal("20000"),
            annual_rate=Decimal("0.24"),
            minimum_payment=Decimal("600"),
        ),
        DebtInput(
            id="personal",
            current_balance=Decimal("60000"),
            annual_rate=Decimal("0.18"),
            minimum_payment=Decimal("1800"),
        ),
    ]


def test_redirect_to_highest_rate_debt_quantifies_interest_and_months_saved() -> None:
    recommendation = redirect_to_highest_rate_debt(
        debts=_debts(), monthly_surplus=Decimal("1500"), computation_reference=REF
    )

    assert recommendation is not None
    assert recommendation.rule is Rule.REDIRECT_TO_HIGHEST_RATE_DEBT
    assert recommendation.benefit_amount > 0
    assert int(recommendation.details["months_saved"]) > 0
    assert recommendation.details["target_debt_id"] == "card"  # the 24% debt


def test_redirect_needs_both_a_surplus_and_more_than_one_debt() -> None:
    assert (
        redirect_to_highest_rate_debt(
            debts=_debts(), monthly_surplus=Decimal("0"), computation_reference=REF
        )
        is None
    )
    assert (
        redirect_to_highest_rate_debt(
            debts=_debts()[:1], monthly_surplus=Decimal("1500"), computation_reference=REF
        )
        is None
    )


def test_build_emergency_cover_reports_the_monthly_amount_to_reach_three_months() -> None:
    recommendation = build_emergency_cover(
        liquid_savings=Decimal("12000"),
        monthly_essential=Decimal("12000"),
        computation_reference=REF,
    )

    assert recommendation is not None
    # Needs R36,000, holds R12,000: a R24,000 gap, R2,000 a month over twelve months.
    assert recommendation.benefit_amount == Decimal("24000.00")
    assert recommendation.details["monthly_amount"] == Decimal("2000.00").to_eng_string()
    assert recommendation.details["current_cover_months"] == "1.000000"


def test_build_emergency_cover_is_silent_when_cover_is_sufficient() -> None:
    assert (
        build_emergency_cover(
            liquid_savings=Decimal("40000"),
            monthly_essential=Decimal("12000"),
            computation_reference=REF,
        )
        is None
    )


def test_subscription_audit_reports_the_largest_qualifying_series_annual_cost() -> None:
    candidates = [
        SubscriptionCandidate(
            key="streaming",
            monthly_equivalent=Decimal("199"),
            annual_cost=Decimal("2388"),
            last_charged_on="2026-09-03",
        ),
        SubscriptionCandidate(
            key="gym",
            monthly_equivalent=Decimal("900"),
            annual_cost=Decimal("10800"),
            last_charged_on="2026-09-01",
        ),
    ]

    recommendation = subscription_audit(
        candidates=candidates,
        monthly_discretionary=Decimal("5000"),
        computation_reference=REF,
    )

    assert recommendation is not None
    assert recommendation.details["series"] == "gym"
    assert recommendation.benefit_amount == Decimal("10800.00")
    assert recommendation.details["share_of_discretionary"] == "0.180000"


def test_subscription_audit_ignores_series_below_the_share_threshold() -> None:
    candidates = [
        SubscriptionCandidate(
            key="streaming",
            monthly_equivalent=Decimal("199"),
            annual_cost=Decimal("2388"),
            last_charged_on="2026-09-03",
        )
    ]
    assert (
        subscription_audit(
            candidates=candidates,
            monthly_discretionary=Decimal("5000"),
            computation_reference=REF,
        )
        is None
    )


def test_utilisation_reduction_quantifies_the_repayment_to_reach_thirty_percent() -> None:
    recommendation = utilisation_reduction(
        revolving_balance=Decimal("9000"),
        credit_limit=Decimal("10000"),
        computation_reference=REF,
    )

    assert recommendation is not None
    # 90% utilisation; reaching 30% of a R10,000 limit means repaying R6,000.
    assert recommendation.benefit_amount == Decimal("6000.00")


def test_utilisation_reduction_is_silent_below_the_trigger() -> None:
    assert (
        utilisation_reduction(
            revolving_balance=Decimal("5000"),
            credit_limit=Decimal("10000"),
            computation_reference=REF,
        )
        is None
    )


def test_goal_shortfall_reports_the_largest_gap_with_its_slippage() -> None:
    shortfalls = [
        GoalShortfall(
            goal_id="g1",
            name="Emergency fund",
            required_monthly=Decimal("3000"),
            observed_monthly=Decimal("2500"),
            slippage_months=4,
        ),
        GoalShortfall(
            goal_id="g2",
            name="Deposit",
            required_monthly=Decimal("8000"),
            observed_monthly=Decimal("2000"),
            slippage_months=30,
        ),
    ]

    recommendation = goal_contribution_shortfall(
        shortfalls=shortfalls, computation_reference=REF
    )

    assert recommendation is not None
    assert recommendation.details["goal_id"] == "g2"
    assert recommendation.benefit_amount == Decimal("6000.00")
    assert recommendation.details["slippage_months"] == "30"


def test_goal_shortfall_is_silent_when_every_goal_is_on_track() -> None:
    shortfalls = [
        GoalShortfall(
            goal_id="g1",
            name="Emergency fund",
            required_monthly=Decimal("3000"),
            observed_monthly=Decimal("3200"),
            slippage_months=None,
        )
    ]
    assert goal_contribution_shortfall(shortfalls=shortfalls, computation_reference=REF) is None


def test_refinance_candidate_uses_the_users_own_weighted_average_as_the_alternative() -> None:
    """"No recommendation suggests a product, provider, or instrument" — so the
    alternative rate can only be one the user already demonstrably has.
    """
    recommendation = refinance_candidate(debts=_debts(), computation_reference=REF)

    assert recommendation is not None
    # Weighted average = (20000*0.24 + 60000*0.18) / 80000 = 0.195.
    assert recommendation.details["weighted_average_rate"] == "0.195000"
    assert recommendation.details["debt_id"] == "card"
    # 20,000 * (0.24 - 0.195) = R900 a year.
    assert recommendation.benefit_amount == Decimal("900.00")


def test_refinance_candidate_is_silent_when_rates_are_close() -> None:
    debts = [
        DebtInput("a", Decimal("20000"), Decimal("0.19"), Decimal("600")),
        DebtInput("b", Decimal("60000"), Decimal("0.18"), Decimal("1800")),
    ]
    assert refinance_candidate(debts=debts, computation_reference=REF) is None


def test_surplus_not_allocated_uses_the_leanest_recent_month() -> None:
    recommendation = surplus_not_allocated(
        monthly_surpluses=[Decimal("5000"), Decimal("3000"), Decimal("4000")],
        computation_reference=REF,
    )

    assert recommendation is not None
    assert recommendation.details["monthly_amount"] == Decimal("3000.00").to_eng_string()
    assert recommendation.details["annual_contributions"] == Decimal("36000.00").to_eng_string()


def test_surplus_not_allocated_needs_every_recent_month_positive() -> None:
    assert (
        surplus_not_allocated(
            monthly_surpluses=[Decimal("5000"), Decimal("-100"), Decimal("4000")],
            computation_reference=REF,
        )
        is None
    )


def test_surplus_not_allocated_needs_enough_history() -> None:
    assert (
        surplus_not_allocated(
            monthly_surpluses=[Decimal("5000"), Decimal("4000")],
            computation_reference=REF,
        )
        is None
    )


def test_ranking_is_by_benefit_and_capped_at_five() -> None:
    recommendations = [
        build_emergency_cover(
            liquid_savings=Decimal("0"),
            monthly_essential=Decimal("12000"),
            computation_reference=REF,
        ),
        utilisation_reduction(
            revolving_balance=Decimal("9000"),
            credit_limit=Decimal("10000"),
            computation_reference=REF,
        ),
        goal_contribution_shortfall(
            shortfalls=[
                GoalShortfall("g1", "Deposit", Decimal("8000"), Decimal("2000"), 30)
            ],
            computation_reference=REF,
        ),
    ]
    ranked = rank_and_cap([r for r in recommendations if r is not None], maximum=2)

    assert len(ranked) == 2
    assert ranked[0].benefit_amount >= ranked[1].benefit_amount
    assert ranked[0].rule is Rule.BUILD_EMERGENCY_COVER  # R36,000 gap is the largest


def test_rank_and_cap_rejects_a_zero_cap() -> None:
    with pytest.raises(ValueError, match="maximum"):
        rank_and_cap([], maximum=0)


def test_every_recommendation_carries_a_computation_reference_and_a_benefit() -> None:
    """specs/recommendations.md: every recommendation carries a quantified benefit and
    its computation reference — there is no path that produces one without both.
    """
    produced = [
        redirect_to_highest_rate_debt(
            debts=_debts(), monthly_surplus=Decimal("1500"), computation_reference=REF
        ),
        build_emergency_cover(
            liquid_savings=Decimal("0"),
            monthly_essential=Decimal("12000"),
            computation_reference=REF,
        ),
        utilisation_reduction(
            revolving_balance=Decimal("9000"),
            credit_limit=Decimal("10000"),
            computation_reference=REF,
        ),
        refinance_candidate(debts=_debts(), computation_reference=REF),
        surplus_not_allocated(
            monthly_surpluses=[Decimal("5000")] * 3, computation_reference=REF
        ),
    ]

    for recommendation in produced:
        assert recommendation is not None
        assert recommendation.computation_reference == REF
        assert recommendation.benefit_amount > 0
        assert recommendation.benefit_kind
