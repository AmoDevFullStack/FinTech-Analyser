from decimal import Decimal

import pytest

from app.domain.amortisation import amortisation_schedule


def test_amortisation_matches_worked_example() -> None:
    """Reference: R350,000 at 11.75% nominal annual, compounded monthly, over 72 months.

    Source: independently derived by hand from the closed-form annuity formula this
    module's own docstring states — i = 0.1175/12, instalment = P*i/(1-(1+i)**-72) —
    solved to full precision and cross-checked with an independent float computation.

    Note: specs/scenarios.md and the financial-domain-engine skill both cite this same
    R350,000/11.75%/72-month example with a first instalment of R6,843.41. That figure
    does not satisfy the standard reducing-balance formula those same documents specify
    (it implies a nominal rate of ~12.005%, not 11.75%) — it was never independently
    recomputed. R6,843.41 is not used here; flagged for the docs to be corrected instead
    of encoding a wrong number as this engine's reference truth.
    """
    schedule = amortisation_schedule(
        principal=Decimal("350000"),
        annual_rate=Decimal("0.1175"),
        term_months=72,
    )

    assert len(schedule) == 72
    assert schedule[0].instalment == Decimal("6797.15")
    assert schedule[-1].closing_balance == Decimal("0.00")


def test_amortisation_zero_rate_splits_principal_evenly() -> None:
    schedule = amortisation_schedule(
        principal=Decimal("1200.00"),
        annual_rate=Decimal("0"),
        term_months=12,
    )
    assert all(p.instalment == Decimal("100.00") for p in schedule)
    assert schedule[-1].closing_balance == Decimal("0.00")


def test_principal_components_sum_to_original_principal() -> None:
    principal = Decimal("350000")
    schedule = amortisation_schedule(
        principal=principal, annual_rate=Decimal("0.1175"), term_months=72
    )
    assert sum(p.principal for p in schedule) == principal


def test_opening_balance_of_period_n_equals_closing_of_period_n_minus_1() -> None:
    schedule = amortisation_schedule(
        principal=Decimal("350000"), annual_rate=Decimal("0.1175"), term_months=72
    )
    for previous, current in zip(schedule, schedule[1:]):
        assert current.opening_balance == previous.closing_balance


def test_closing_balance_never_negative() -> None:
    schedule = amortisation_schedule(
        principal=Decimal("350000"), annual_rate=Decimal("0.1175"), term_months=72
    )
    assert all(p.closing_balance >= 0 for p in schedule)


def test_extra_payments_shorten_term_and_reduce_total_interest() -> None:
    base = amortisation_schedule(
        principal=Decimal("350000"), annual_rate=Decimal("0.1175"), term_months=72
    )
    accelerated = amortisation_schedule(
        principal=Decimal("350000"),
        annual_rate=Decimal("0.1175"),
        term_months=72,
        extra_monthly=Decimal("1000"),
    )
    assert len(accelerated) < len(base)
    assert sum(p.interest for p in accelerated) < sum(p.interest for p in base)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"principal": Decimal("-1"), "annual_rate": Decimal("0.1"), "term_months": 12},
        {"principal": Decimal("100"), "annual_rate": Decimal("-0.1"), "term_months": 12},
        {"principal": Decimal("100"), "annual_rate": Decimal("0.1"), "term_months": 0},
        {
            "principal": Decimal("100"),
            "annual_rate": Decimal("0.1"),
            "term_months": 12,
            "extra_monthly": Decimal("-1"),
        },
    ],
)
def test_invalid_inputs_raise_value_error(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        amortisation_schedule(**kwargs)
