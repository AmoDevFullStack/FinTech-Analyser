from datetime import date
from decimal import Decimal

import pytest

from app.domain.accuracy import (
    BIAS_MONTHS,
    Metric,
    MonthAccuracy,
    compare_month,
    summarise,
)
from app.domain.forecast import (
    BehaviouralBaseline,
    ForecastAssumptions,
    MonthlyObservation,
    derive_baselines,
    project_forecast,
)


def _observation(month: str, income: str, essential: str, discretionary: str) -> MonthlyObservation:
    return MonthlyObservation(
        month=month,
        income=Decimal(income),
        essential=Decimal(essential),
        discretionary=Decimal(discretionary),
    )


def test_baselines_use_medians_so_one_bonus_month_does_not_move_them() -> None:
    """specs/forecasting.md acceptance criterion: "Baseline statistics use medians,
    asserted by test against a history containing outliers."
    """
    history = [
        _observation("2026-01", "30000", "12000", "5000"),
        _observation("2026-02", "30000", "12000", "5000"),
        _observation("2026-03", "120000", "12000", "5000"),  # bonus month
        _observation("2026-04", "30000", "12000", "5000"),
        _observation("2026-05", "30000", "12000", "5000"),
    ]

    baseline = derive_baselines(observations=history)

    assert baseline.median_income == Decimal("30000.00")
    # The mean would have been R48,000 — R18,000 of salary the user does not earn.
    assert baseline.median_income != sum(o.income for o in history) / len(history)


def test_thin_history_is_labelled_low_confidence() -> None:
    baseline = derive_baselines(
        observations=[
            _observation("2026-01", "30000", "12000", "5000"),
            _observation("2026-02", "30000", "12000", "5000"),
        ]
    )
    assert baseline.is_low_confidence is True
    assert baseline.months_observed == 2


def test_three_months_is_confident_enough() -> None:
    baseline = derive_baselines(
        observations=[
            _observation("2026-01", "30000", "12000", "5000"),
            _observation("2026-02", "30000", "12000", "5000"),
            _observation("2026-03", "30000", "12000", "5000"),
        ]
    )
    assert baseline.is_low_confidence is False


def test_empty_history_is_zeroed_and_low_confidence_rather_than_an_error() -> None:
    baseline = derive_baselines(observations=[])
    assert baseline.median_income == Decimal("0.00")
    assert baseline.is_low_confidence is True


def test_discretionary_variability_is_a_median_absolute_deviation() -> None:
    history = [
        _observation("2026-01", "30000", "12000", "4000"),
        _observation("2026-02", "30000", "12000", "5000"),
        _observation("2026-03", "30000", "12000", "6000"),
    ]
    baseline = derive_baselines(observations=history)

    # Median discretionary 5,000; deviations 1,000/0/1,000 with median 1,000: 0.2.
    assert baseline.median_discretionary == Decimal("5000.00")
    assert baseline.discretionary_variability == Decimal("0.200000")


def _flat_baseline() -> BehaviouralBaseline:
    return BehaviouralBaseline(
        median_income=Decimal("30000.00"),
        median_essential=Decimal("12000.00"),
        median_discretionary=Decimal("5000.00"),
        discretionary_variability=Decimal("0.100000"),
        months_observed=12,
        is_low_confidence=False,
    )


def test_projection_without_growth_is_flat() -> None:
    """The invariant from the financial-domain-engine skill: zero change in, flat out."""
    periods = project_forecast(
        baseline=_flat_baseline(),
        opening_savings=Decimal("10000.00"),
        opening_debt=Decimal("0.00"),
        opening_net_worth=Decimal("10000.00"),
        as_of=date(2026, 1, 31),
        assumptions=ForecastAssumptions(
            inflation_annual=Decimal("0"),
            salary_growth_annual=Decimal("0"),
            horizon_months=24,
        ),
    )

    assert all(p.cash_flow == Decimal("13000.00") for p in periods)
    assert periods[0].savings_balance == Decimal("23000.00")
    assert periods[1].savings_balance == Decimal("36000.00")


def test_salary_growth_steps_on_the_anniversary_not_monthly() -> None:
    periods = project_forecast(
        baseline=_flat_baseline(),
        opening_savings=Decimal("0.00"),
        opening_debt=Decimal("0.00"),
        opening_net_worth=Decimal("0.00"),
        as_of=date(2026, 1, 31),
        assumptions=ForecastAssumptions(
            inflation_annual=Decimal("0"),
            salary_growth_annual=Decimal("0.05"),
            horizon_months=26,
        ),
    )

    assert periods[0].projected_income == Decimal("30000.00")
    assert periods[11].projected_income == Decimal("30000.00")  # still year one
    assert periods[12].projected_income == Decimal("31500.00")  # first anniversary
    assert periods[24].projected_income == Decimal("33075.00")  # second, compounding


def test_inflation_applies_to_discretionary_too_so_it_stays_flat_in_real_terms() -> None:
    periods = project_forecast(
        baseline=_flat_baseline(),
        opening_savings=Decimal("0.00"),
        opening_debt=Decimal("0.00"),
        opening_net_worth=Decimal("0.00"),
        as_of=date(2026, 1, 31),
        assumptions=ForecastAssumptions(
            inflation_annual=Decimal("0.05"),
            salary_growth_annual=Decimal("0"),
            horizon_months=14,
        ),
    )

    # Year two: essential 12,000 * 1.05 = 12,600; discretionary 5,000 * 1.05 = 5,250.
    assert periods[12].projected_expenses == Decimal("17850.00")


def test_a_debt_schedule_reduces_cash_flow_and_runs_the_balance_down() -> None:
    from app.domain.amortisation import amortisation_schedule

    schedule = tuple(
        amortisation_schedule(
            principal=Decimal("60000"), annual_rate=Decimal("0.12"), term_months=12
        )
    )
    periods = project_forecast(
        baseline=_flat_baseline(),
        opening_savings=Decimal("0.00"),
        opening_debt=Decimal("60000.00"),
        opening_net_worth=Decimal("-60000.00"),
        as_of=date(2026, 1, 31),
        assumptions=ForecastAssumptions(
            inflation_annual=Decimal("0"),
            salary_growth_annual=Decimal("0"),
            horizon_months=14,
        ),
        existing_debt_schedule=schedule,
    )

    assert periods[0].cash_flow == Decimal("13000.00") - schedule[0].instalment
    assert periods[11].debt_balance == Decimal("0.00")
    assert periods[12].cash_flow == Decimal("13000.00")  # instalment stops


def test_emergency_cover_is_zero_rather_than_negative_on_a_negative_balance() -> None:
    baseline = BehaviouralBaseline(
        median_income=Decimal("10000.00"),
        median_essential=Decimal("12000.00"),
        median_discretionary=Decimal("5000.00"),
        discretionary_variability=Decimal("0"),
        months_observed=6,
        is_low_confidence=False,
    )
    periods = project_forecast(
        baseline=baseline,
        opening_savings=Decimal("0.00"),
        opening_debt=Decimal("0.00"),
        opening_net_worth=Decimal("0.00"),
        as_of=date(2026, 1, 31),
        assumptions=ForecastAssumptions(horizon_months=3),
    )

    assert periods[0].savings_balance < 0
    assert all(p.emergency_fund_months == Decimal("0.000000") for p in periods)


def test_projection_rejects_a_non_positive_horizon() -> None:
    with pytest.raises(ValueError, match="horizon_months"):
        project_forecast(
            baseline=_flat_baseline(),
            opening_savings=Decimal("0"),
            opening_debt=Decimal("0"),
            opening_net_worth=Decimal("0"),
            as_of=date(2026, 1, 31),
            assumptions=ForecastAssumptions(horizon_months=0),
        )


def test_compare_month_reports_signed_and_absolute_error() -> None:
    accuracy = compare_month(
        month="2026-02",
        projected={Metric.CASH_FLOW: Decimal("13000"), Metric.INCOME: Decimal("30000")},
        actual={Metric.CASH_FLOW: Decimal("11000"), Metric.INCOME: Decimal("30000")},
    )

    cash_flow = accuracy.for_metric(Metric.CASH_FLOW)
    assert cash_flow is not None
    assert cash_flow.signed_error == Decimal("-2000.00")
    assert cash_flow.absolute_error == Decimal("2000.00")
    assert cash_flow.percentage_error == Decimal("-0.153846")

    income = accuracy.for_metric(Metric.INCOME)
    assert income is not None
    assert income.absolute_error == Decimal("0.00")


def test_percentage_error_is_none_against_a_zero_projection() -> None:
    accuracy = compare_month(
        month="2026-02",
        projected={Metric.CASH_FLOW: Decimal("0")},
        actual={Metric.CASH_FLOW: Decimal("500")},
    )
    comparison = accuracy.for_metric(Metric.CASH_FLOW)
    assert comparison is not None
    assert comparison.percentage_error is None
    assert comparison.absolute_error == Decimal("500.00")


def _history(errors: list[str]) -> list[MonthAccuracy]:
    return [
        compare_month(
            month=f"2026-{index + 1:02d}",
            projected={Metric.EXPENSES: Decimal("10000")},
            actual={Metric.EXPENSES: Decimal("10000") + Decimal(error)},
        )
        for index, error in enumerate(errors)
    ]


def test_persistent_one_directional_error_is_reported_as_bias() -> None:
    summary = summarise(metric=Metric.EXPENSES, history=_history(["1000", "1200", "1100"]))

    assert summary.has_persistent_bias is True
    assert summary.bias_direction == "under_projected"
    assert summary.suggested_adjustment == Decimal("1100.00")


def test_alternating_error_is_not_bias() -> None:
    summary = summarise(metric=Metric.EXPENSES, history=_history(["1000", "-1200", "1100"]))

    assert summary.has_persistent_bias is False
    assert summary.suggested_adjustment == Decimal("0.00")


def test_small_consistent_error_is_below_materiality() -> None:
    """Consistently 2% out is a rounding artefact of month-end timing, not a bias."""
    summary = summarise(metric=Metric.EXPENSES, history=_history(["200", "210", "190"]))

    assert summary.has_persistent_bias is False


def test_too_few_months_is_never_called_bias() -> None:
    summary = summarise(metric=Metric.EXPENSES, history=_history(["1000", "1200"]))

    assert summary.months_measured == 2
    assert summary.months_measured < BIAS_MONTHS
    assert summary.has_persistent_bias is False


def test_over_projection_is_reported_with_a_negative_adjustment() -> None:
    summary = summarise(metric=Metric.EXPENSES, history=_history(["-1000", "-1200", "-1100"]))

    assert summary.bias_direction == "over_projected"
    assert summary.suggested_adjustment == Decimal("-1100.00")


def test_summarise_with_no_history_returns_zeros() -> None:
    summary = summarise(metric=Metric.EXPENSES, history=[])

    assert summary.months_measured == 0
    assert summary.mean_percentage_error is None
    assert summary.has_persistent_bias is False
