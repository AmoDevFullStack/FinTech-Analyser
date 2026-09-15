from decimal import Decimal

import pytest

from app.domain.financial_health import (
    _CASH_FLOW_MARGIN_BANDS,
    _CASH_FLOW_STABILITY_BANDS,
    _CREDIT_UTILISATION_BANDS,
    _DEBT_BURDEN_BANDS,
    _EMERGENCY_COVER_BANDS,
    _SAVINGS_RATE_BANDS,
    _piecewise_score,
    compute_health_score,
)

BAND_TABLES = [
    _EMERGENCY_COVER_BANDS,
    _DEBT_BURDEN_BANDS,
    _CASH_FLOW_MARGIN_BANDS,
    _SAVINGS_RATE_BANDS,
    _CREDIT_UTILISATION_BANDS,
    _CASH_FLOW_STABILITY_BANDS,
]


@pytest.mark.parametrize("bands", BAND_TABLES)
def test_every_band_edge_returns_its_table_value_exactly(bands) -> None:
    """Acceptance criterion: "Domain tests cover boundary cases at each band edge."""
    for ratio, expected_score in bands:
        assert _piecewise_score(ratio, bands) == expected_score


@pytest.mark.parametrize("bands", BAND_TABLES)
def test_ratio_below_first_band_clamps_to_first_score(bands) -> None:
    assert _piecewise_score(Decimal("-1"), bands) == bands[0][1]


@pytest.mark.parametrize("bands", BAND_TABLES)
def test_ratio_above_last_band_clamps_to_last_score(bands) -> None:
    assert _piecewise_score(bands[-1][0] + Decimal("1000"), bands) == bands[-1][1]


def test_midpoint_interpolates_linearly() -> None:
    """Reference: emergency cover 1.5 months sits halfway between the 1.0->25 and
    2.0->45 band points, hand-computed: 25 + 0.5 * (45 - 25) = 35.
    """
    assert _piecewise_score(Decimal("1.5"), _EMERGENCY_COVER_BANDS) == Decimal("35")


def test_three_months_is_materially_better_than_two_eight_barely_better_than_seven() -> None:
    """The spec's own worked claim about non-linearity, asserted directly."""
    score_2 = _piecewise_score(Decimal("2"), _EMERGENCY_COVER_BANDS)
    score_3 = _piecewise_score(Decimal("3"), _EMERGENCY_COVER_BANDS)
    score_7 = _piecewise_score(Decimal("7"), _EMERGENCY_COVER_BANDS)
    score_8 = _piecewise_score(Decimal("8"), _EMERGENCY_COVER_BANDS)

    two_to_three_gain = score_3 - score_2
    seven_to_eight_gain = score_8 - score_7
    assert two_to_three_gain > seven_to_eight_gain


def test_compute_health_score_matches_dashboard_worked_example() -> None:
    """Reference: the published dashboard mock's position — emergency cover 1.53 months
    (0 debt burden and credit utilisation not modelled in that mock; zeroed here) should
    land in the weak range the mock's "62/100, largest drag: emergency fund" copy implies.
    This is a smoke test on the combination logic, not a claim the mock's "62" is exact —
    that number was illustrative sample copy, per the note in test_emergency_fund.py.
    """
    result = compute_health_score(
        emergency_cover_months=Decimal("1.53"),
        debt_to_income=Decimal("0.283931"),
        cash_flow_margin=Decimal("0.207692"),  # 10800/52000
        savings_rate=Decimal("0"),
        credit_utilisation=Decimal("0"),
        cash_flow_variability=Decimal("0"),
    )
    assert 0 <= result.overall_score <= 100
    assert result.largest_negative_contributor == "emergency_cover"


def test_weighted_sum_matches_hand_calculation_at_known_ratios() -> None:
    """All six ratios placed exactly on a band point each, so the expected contribution
    of each component is exact and the overall score is a plain weighted sum, hand-added:
        emergency_cover:      score 65, weight .25 -> 16.25
        debt_burden:          score 50, weight .20 -> 10.00
        cash_flow_margin:     score 75, weight .20 -> 15.00
        savings_rate:         score 55, weight .15 ->  8.25
        credit_utilisation:   score 95, weight .10 ->  9.50
        cash_flow_stability:  score 85, weight .10 ->  8.50
        total = 16.25+10+15+8.25+9.5+8.5 = 67.50 -> rounds to 68 (ROUND_HALF_UP)
    """
    result = compute_health_score(
        emergency_cover_months=Decimal("3.0"),
        debt_to_income=Decimal("0.36"),
        cash_flow_margin=Decimal("0.20"),
        savings_rate=Decimal("0.10"),
        credit_utilisation=Decimal("0.10"),
        cash_flow_variability=Decimal("0.05"),
    )
    assert result.overall_score == 68
    assert result.weights_version == "1.0.0"


def test_negative_ratio_rejected() -> None:
    with pytest.raises(ValueError):
        compute_health_score(
            emergency_cover_months=Decimal("-1"),
            debt_to_income=Decimal("0"),
            cash_flow_margin=Decimal("0"),
            savings_rate=Decimal("0"),
            credit_utilisation=Decimal("0"),
            cash_flow_variability=Decimal("0"),
        )
