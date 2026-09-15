"""Financial health scoring. See specs/financial-health.md and requirements.md §10.

Six weighted components, each mapped from a ratio to a 0-100 score through a documented,
piecewise-linear band table (never a straight line — see the objective in the spec: "Three
months of emergency cover is materially better than two; eight is not materially better
than seven"). The band tables below ARE the specification for this scoring system — there
is no external authority to check them against, so the tests assert code matches table,
and boundary cases sit exactly on band edges per the spec's acceptance criteria.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

RATE_PLACES = Decimal("0.000001")
SCORE_PLACES = Decimal("0.01")

WEIGHTS_VERSION = "1.0.0"

# (ratio, score) points, ascending by ratio, linearly interpolated between consecutive
# points and clamped beyond the first/last. Direction (higher-is-better vs lower-is-better)
# falls out of whether score rises or falls across the table — the interpolation itself
# doesn't need to know which.
_EMERGENCY_COVER_BANDS = (
    (Decimal("0.0"), Decimal("0")),
    (Decimal("1.0"), Decimal("25")),
    (Decimal("2.0"), Decimal("45")),
    (Decimal("3.0"), Decimal("65")),
    (Decimal("6.0"), Decimal("90")),
    (Decimal("9.0"), Decimal("100")),
)
_DEBT_BURDEN_BANDS = (
    (Decimal("0.00"), Decimal("100")),
    (Decimal("0.10"), Decimal("90")),
    (Decimal("0.20"), Decimal("75")),
    (Decimal("0.36"), Decimal("50")),
    (Decimal("0.50"), Decimal("20")),
    (Decimal("1.00"), Decimal("0")),
)
_CASH_FLOW_MARGIN_BANDS = (
    (Decimal("0.00"), Decimal("0")),
    (Decimal("0.05"), Decimal("30")),
    (Decimal("0.10"), Decimal("50")),
    (Decimal("0.20"), Decimal("75")),
    (Decimal("0.30"), Decimal("90")),
    (Decimal("0.40"), Decimal("100")),
)
_SAVINGS_RATE_BANDS = (
    (Decimal("0.00"), Decimal("0")),
    (Decimal("0.05"), Decimal("30")),
    (Decimal("0.10"), Decimal("55")),
    (Decimal("0.15"), Decimal("75")),
    (Decimal("0.20"), Decimal("90")),
    (Decimal("0.30"), Decimal("100")),
)
_CREDIT_UTILISATION_BANDS = (
    (Decimal("0.00"), Decimal("100")),
    (Decimal("0.10"), Decimal("95")),
    (Decimal("0.30"), Decimal("75")),
    (Decimal("0.50"), Decimal("50")),
    (Decimal("0.75"), Decimal("25")),
    (Decimal("1.00"), Decimal("0")),
)
_CASH_FLOW_STABILITY_BANDS = (
    (Decimal("0.00"), Decimal("100")),
    (Decimal("0.05"), Decimal("85")),
    (Decimal("0.10"), Decimal("65")),
    (Decimal("0.20"), Decimal("40")),
    (Decimal("0.35"), Decimal("15")),
    (Decimal("0.50"), Decimal("0")),
)

_WEIGHTS = {
    "emergency_cover": Decimal("0.25"),
    "debt_burden": Decimal("0.20"),
    "cash_flow_margin": Decimal("0.20"),
    "savings_rate": Decimal("0.15"),
    "credit_utilisation": Decimal("0.10"),
    "cash_flow_stability": Decimal("0.10"),
}


def _piecewise_score(ratio: Decimal, bands: tuple[tuple[Decimal, Decimal], ...]) -> Decimal:
    """Map a ratio to a 0-100 score via linear interpolation between band points.

    Clamped to the first point's score below its ratio, and the last point's score above
    it. `ratio` and every band boundary must be finite; a ratio exactly on a boundary
    returns that boundary's score exactly (the acceptance criterion this exists to satisfy).
    """
    if ratio <= bands[0][0]:
        return bands[0][1]
    if ratio >= bands[-1][0]:
        return bands[-1][1]

    for (r0, s0), (r1, s1) in zip(bands, bands[1:]):
        if r0 <= ratio <= r1:
            fraction = (ratio - r0) / (r1 - r0)
            return s0 + fraction * (s1 - s0)

    raise AssertionError(f"ratio {ratio} fell between no band in {bands}")


@dataclass(frozen=True, slots=True)
class ComponentScore:
    name: str
    ratio: Decimal
    score: Decimal
    weight: Decimal
    contribution: Decimal


@dataclass(frozen=True, slots=True)
class HealthAssessmentResult:
    overall_score: int
    components: tuple[ComponentScore, ...]
    weights_version: str
    largest_positive_contributor: str
    largest_negative_contributor: str


def _component(name: str, ratio: Decimal, bands: tuple[tuple[Decimal, Decimal], ...]) -> ComponentScore:
    score = _piecewise_score(ratio, bands).quantize(SCORE_PLACES, rounding=ROUND_HALF_UP)
    weight = _WEIGHTS[name]
    contribution = (score * weight).quantize(SCORE_PLACES, rounding=ROUND_HALF_UP)
    return ComponentScore(
        name=name, ratio=ratio.quantize(RATE_PLACES, rounding=ROUND_HALF_UP),
        score=score, weight=weight, contribution=contribution,
    )


def compute_health_score(
    *,
    emergency_cover_months: Decimal,
    debt_to_income: Decimal,
    cash_flow_margin: Decimal,
    savings_rate: Decimal,
    credit_utilisation: Decimal,
    cash_flow_variability: Decimal,
) -> HealthAssessmentResult:
    """Combine the six components into an overall 0-100 score.

    Formula:
        overall = round(sum(component.score * component.weight for component in components))

    Assumptions:
        - Every ratio arrives pre-computed by the caller (this engine has no notion of
          accounts, transactions, or dates — see the financial-domain-engine skill, rule 1).
        - Weights: emergency cover 25%, debt burden 20%, cash-flow margin 20%, savings
          rate 15%, credit utilisation 10%, cash-flow stability 10% — sum to 100%,
          per specs/financial-health.md. `WEIGHTS_VERSION` changes if these ever do.
        - "Largest positive contributor" is the component contributing the most points
          toward the overall score (weight * score); "largest negative contributor" is
          the component costing the most points against a perfect 100
          (weight * (100 - score)) — the dashboard's "largest drag on the score".

    Rounding:
        Each component's ratio to six places, score and contribution to two places,
        the overall score to the nearest whole point — all ROUND_HALF_UP.

    Raises:
        ValueError: if any ratio is negative.
    """
    ratios = {
        "emergency_cover": (emergency_cover_months, _EMERGENCY_COVER_BANDS),
        "debt_burden": (debt_to_income, _DEBT_BURDEN_BANDS),
        "cash_flow_margin": (cash_flow_margin, _CASH_FLOW_MARGIN_BANDS),
        "savings_rate": (savings_rate, _SAVINGS_RATE_BANDS),
        "credit_utilisation": (credit_utilisation, _CREDIT_UTILISATION_BANDS),
        "cash_flow_stability": (cash_flow_variability, _CASH_FLOW_STABILITY_BANDS),
    }
    for name, (ratio, _) in ratios.items():
        if ratio < 0:
            raise ValueError(f"{name} ratio must be >= 0, got {ratio}")

    components = tuple(_component(name, ratio, bands) for name, (ratio, bands) in ratios.items())

    overall = sum((c.contribution for c in components), Decimal("0")).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )

    positive = max(components, key=lambda c: c.contribution)
    negative = max(components, key=lambda c: c.weight * (Decimal("100") - c.score))

    return HealthAssessmentResult(
        overall_score=int(overall),
        components=components,
        weights_version=WEIGHTS_VERSION,
        largest_positive_contributor=positive.name,
        largest_negative_contributor=negative.name,
    )
