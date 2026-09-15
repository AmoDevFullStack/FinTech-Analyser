from datetime import date
from decimal import Decimal

import pytest

from app.domain.risk import (
    CategorySpend,
    Obligation,
    ProjectedPeriod,
    RiskType,
    Severity,
    detect_anomalous_spending,
    detect_cash_flow_shortfall,
    detect_credit_utilisation,
    detect_debt_burden,
    detect_emergency_reserve_depletion,
    detect_obligation_coverage_gap,
    materiality_threshold,
    severity_rank,
)

FORECAST = "f-1"


def _period(
    month: str,
    *,
    inflows: str,
    outflows: str,
    liquid: str,
    cover: str = "6",
) -> ProjectedPeriod:
    year, mm = month.split("-")
    return ProjectedPeriod(
        month=month,
        starts_on=date(int(year), int(mm), 1),
        inflows=Decimal(inflows),
        outflows=Decimal(outflows),
        liquid_funds=Decimal(liquid),
        emergency_fund_months=Decimal(cover),
    )


def test_materiality_threshold_scales_with_income() -> None:
    assert materiality_threshold(monthly_income=Decimal("20000")) == Decimal("400.00")
    assert materiality_threshold(monthly_income=Decimal("80000")) == Decimal("1600.00")


def test_materiality_threshold_rejects_negative_income() -> None:
    with pytest.raises(ValueError, match="monthly_income"):
        materiality_threshold(monthly_income=Decimal("-1"))


def test_cash_flow_shortfall_is_detected_with_month_and_amount() -> None:
    periods = [
        _period("2026-10", inflows="20000", outflows="18000", liquid="12000"),
        # Opening funds 12,000 + inflows 20,000 = 32,000 against 40,000 out: 8,000 short.
        _period("2026-11", inflows="20000", outflows="40000", liquid="-8000"),
    ]

    finding = detect_cash_flow_shortfall(
        periods=periods, monthly_income=Decimal("20000"), forecast_id=FORECAST
    )

    assert finding is not None
    assert finding.risk_type is RiskType.CASH_FLOW_SHORTFALL
    assert finding.projected_date == date(2026, 11, 1)
    assert finding.quantified_amount == Decimal("8000.00")
    assert finding.computation_reference == "forecast:f-1:period:2026-11"


def test_cash_flow_shortfall_below_materiality_is_not_flagged() -> None:
    """R100 short at R20,000 income is under the R400 threshold — no flag."""
    periods = [
        _period("2026-10", inflows="20000", outflows="20100", liquid="-100"),
    ]
    assert (
        detect_cash_flow_shortfall(
            periods=periods, monthly_income=Decimal("20000"), forecast_id=FORECAST
        )
        is None
    )


def test_cash_flow_shortfall_returns_the_earliest_not_the_largest() -> None:
    periods = [
        _period("2026-10", inflows="20000", outflows="18000", liquid="10000"),
        _period("2026-11", inflows="20000", outflows="35000", liquid="-5000"),
        _period("2026-12", inflows="20000", outflows="80000", liquid="-65000"),
    ]

    finding = detect_cash_flow_shortfall(
        periods=periods, monthly_income=Decimal("20000"), forecast_id=FORECAST
    )

    assert finding is not None
    assert finding.projected_date == date(2026, 11, 1)


def test_obligation_coverage_gap_names_the_obligation_date_and_amount() -> None:
    periods = [
        _period("2026-10", inflows="5000", outflows="4000", liquid="1200"),
    ]
    obligations = [
        Obligation(label="vehicle instalment", amount=Decimal("6843"), due_on=date(2026, 10, 25))
    ]

    finding = detect_obligation_coverage_gap(
        obligations=obligations,
        periods=periods,
        monthly_income=Decimal("5000"),
        forecast_id=FORECAST,
    )

    assert finding is not None
    assert finding.risk_type is RiskType.OBLIGATION_COVERAGE_GAP
    assert finding.projected_date == date(2026, 10, 25)
    # Opening funds 1,200 - (5,000 - 4,000) = 200; 200 + 5,000 = 5,200 available.
    assert finding.quantified_amount == Decimal("1643.00")
    assert finding.details["obligation"] == "vehicle instalment"


def test_obligation_outside_the_horizon_is_skipped_not_assumed_uncovered() -> None:
    periods = [_period("2026-10", inflows="5000", outflows="4000", liquid="1200")]
    obligations = [
        Obligation(label="rates", amount=Decimal("90000"), due_on=date(2029, 4, 1))
    ]

    assert (
        detect_obligation_coverage_gap(
            obligations=obligations,
            periods=periods,
            monthly_income=Decimal("5000"),
            forecast_id=FORECAST,
        )
        is None
    )


def test_emergency_reserve_depletion_quantifies_the_rand_shortfall() -> None:
    periods = [
        _period("2026-10", inflows="20000", outflows="19000", liquid="12000", cover="2"),
        _period("2026-11", inflows="20000", outflows="24000", liquid="8000", cover="0.5"),
    ]

    finding = detect_emergency_reserve_depletion(
        periods=periods, monthly_essential=Decimal("12000"), forecast_id=FORECAST
    )

    assert finding is not None
    assert finding.risk_type is RiskType.EMERGENCY_RESERVE_DEPLETION
    assert finding.projected_date == date(2026, 11, 1)
    assert finding.quantified_amount == Decimal("6000.00")  # 0.5 months * R12,000


def test_emergency_reserve_with_no_essential_spending_is_not_flagged() -> None:
    periods = [_period("2026-10", inflows="0", outflows="0", liquid="0", cover="0")]
    assert (
        detect_emergency_reserve_depletion(
            periods=periods, monthly_essential=Decimal("0"), forecast_id=FORECAST
        )
        is None
    )


def test_debt_burden_above_forty_percent_is_flagged_with_the_excess() -> None:
    finding = detect_debt_burden(
        monthly_debt_service=Decimal("10000"),
        monthly_income=Decimal("20000"),
        assessment_reference="health:a-1",
        as_of=date(2026, 9, 15),
    )

    assert finding is not None
    assert finding.risk_type is RiskType.DEBT_BURDEN_THRESHOLD
    # 50% against a 40% threshold: R10,000 - R8,000 = R2,000 over.
    assert finding.quantified_amount == Decimal("2000.00")
    assert finding.details["debt_to_income"] == "0.500000"


def test_debt_burden_at_exactly_the_threshold_is_not_flagged() -> None:
    assert (
        detect_debt_burden(
            monthly_debt_service=Decimal("8000"),
            monthly_income=Decimal("20000"),
            assessment_reference="health:a-1",
            as_of=date(2026, 9, 15),
        )
        is None
    )


def test_debt_burden_with_no_income_is_not_flagged() -> None:
    assert (
        detect_debt_burden(
            monthly_debt_service=Decimal("8000"),
            monthly_income=Decimal("0"),
            assessment_reference="health:a-1",
            as_of=date(2026, 9, 15),
        )
        is None
    )


def test_anomalous_spending_is_measured_against_income_not_the_category() -> None:
    """The spec's own example: R2,000 over means different things at different incomes."""
    categories = [
        CategorySpend(
            category="groceries",
            baseline_monthly=Decimal("4000"),
            current_monthly=Decimal("6000"),
        )
    ]

    at_low_income = detect_anomalous_spending(
        categories=categories,
        monthly_income=Decimal("20000"),
        as_of=date(2026, 9, 15),
        position_reference="position:p-1",
    )
    at_high_income = detect_anomalous_spending(
        categories=categories,
        monthly_income=Decimal("80000"),
        as_of=date(2026, 9, 15),
        position_reference="position:p-1",
    )

    # R2,000 over is 10% of a R20,000 income (flagged) but 2.5% of R80,000 (not).
    assert at_low_income is not None
    assert at_low_income.quantified_amount == Decimal("2000.00")
    assert at_high_income is None


def test_anomalous_spending_ignores_a_category_with_no_baseline() -> None:
    categories = [
        CategorySpend(
            category="new category",
            baseline_monthly=Decimal("0"),
            current_monthly=Decimal("9000"),
        )
    ]
    assert (
        detect_anomalous_spending(
            categories=categories,
            monthly_income=Decimal("20000"),
            as_of=date(2026, 9, 15),
            position_reference="position:p-1",
        )
        is None
    )


def test_anomalous_spending_returns_the_largest_excess() -> None:
    categories = [
        CategorySpend("groceries", Decimal("4000"), Decimal("6000")),
        CategorySpend("dining", Decimal("2000"), Decimal("9000")),
    ]

    finding = detect_anomalous_spending(
        categories=categories,
        monthly_income=Decimal("20000"),
        as_of=date(2026, 9, 15),
        position_reference="position:p-1",
    )

    assert finding is not None
    assert finding.details["category"] == "dining"
    assert finding.quantified_amount == Decimal("7000.00")


def test_credit_utilisation_above_seventy_percent_quantifies_the_repayment() -> None:
    finding = detect_credit_utilisation(
        revolving_balance=Decimal("9000"),
        credit_limit=Decimal("10000"),
        as_of=date(2026, 9, 15),
        position_reference="position:p-1",
    )

    assert finding is not None
    assert finding.risk_type is RiskType.CREDIT_UTILISATION
    # 90% against a 70% threshold: R9,000 - R7,000 = R2,000 to repay.
    assert finding.quantified_amount == Decimal("2000.00")
    assert finding.details["utilisation"] == "0.900000"


def test_credit_utilisation_with_no_facility_is_not_flagged() -> None:
    assert (
        detect_credit_utilisation(
            revolving_balance=Decimal("0"),
            credit_limit=Decimal("0"),
            as_of=date(2026, 9, 15),
            position_reference="position:p-1",
        )
        is None
    )


def test_severity_escalates_with_the_size_of_the_overshoot() -> None:
    mild = detect_credit_utilisation(
        revolving_balance=Decimal("7500"),
        credit_limit=Decimal("10000"),
        as_of=date(2026, 9, 15),
        position_reference="position:p-1",
    )
    severe = detect_credit_utilisation(
        revolving_balance=Decimal("10000"),
        credit_limit=Decimal("10000"),
        as_of=date(2026, 9, 15),
        position_reference="position:p-1",
    )

    assert mild is not None and severe is not None
    assert severity_rank(severe.severity) > severity_rank(mild.severity)
    assert mild.severity is Severity.LOW


def test_every_finding_carries_a_computation_reference() -> None:
    """specs/risk-detection.md: a flag without one must not be created."""
    findings = [
        detect_cash_flow_shortfall(
            periods=[_period("2026-11", inflows="1000", outflows="9000", liquid="-8000")],
            monthly_income=Decimal("20000"),
            forecast_id=FORECAST,
        ),
        detect_debt_burden(
            monthly_debt_service=Decimal("10000"),
            monthly_income=Decimal("20000"),
            assessment_reference="health:a-1",
            as_of=date(2026, 9, 15),
        ),
        detect_credit_utilisation(
            revolving_balance=Decimal("9000"),
            credit_limit=Decimal("10000"),
            as_of=date(2026, 9, 15),
            position_reference="position:p-1",
        ),
    ]

    assert all(f is not None and f.computation_reference for f in findings)
