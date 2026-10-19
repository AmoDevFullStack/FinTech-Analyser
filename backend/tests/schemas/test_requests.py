"""Request validation at the boundary. No database — these are pydantic models.

What is being asserted is the promise docs/api.md makes: a malformed request is a 400 with
the offending field named, not a 500 from whatever the ad-hoc coercion happened to raise.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from flask import Flask

from app.core.errors import ValidationError
from app.domain.payment_taxonomy import PaymentMethod, SpendingPurpose
from app.schemas.base import parse_body, parse_query
from app.schemas.requests import (
    CreateDebtRequest,
    ManualTransactionRequest,
    RegisterRequest,
    ResolveImportRequest,
    TransactionQuery,
    UpdateDebtRequest,
    WhatIfQuery,
)

app = Flask(__name__)


def query(model, querystring: str):
    with app.test_request_context(f"/?{querystring}"):
        return parse_query(model)


def body(model, payload):
    with app.test_request_context(
        "/", method="POST", data=json.dumps(payload), content_type="application/json"
    ):
        return parse_body(model)


# --------------------------------------------------------------------------------------
# Query strings
# --------------------------------------------------------------------------------------
def test_query_defaults_are_applied_when_nothing_is_supplied() -> None:
    parsed = query(TransactionQuery, "")

    assert parsed.limit == 50
    assert parsed.fuzzy is True
    assert parsed.min_score == Decimal("0.62")
    assert parsed.q is None


def test_from_and_to_are_aliases_for_the_date_range() -> None:
    """`from` is a Python keyword, so the field is `since` and the wire name is the alias.
    The alias is the contract; the field name is an implementation detail."""
    parsed = query(TransactionQuery, "from=2026-01-01&to=2026-03-31")

    assert parsed.since == date(2026, 1, 1)
    assert parsed.until == date(2026, 3, 31)


def test_a_date_range_that_ends_before_it_starts_is_rejected() -> None:
    with pytest.raises(ValidationError) as exc:
        query(TransactionQuery, "from=2026-03-31&to=2026-01-01")

    assert "to" in str(exc.value).lower() or "from" in str(exc.value).lower()


def test_an_amount_range_that_ends_below_it_starts_is_rejected() -> None:
    with pytest.raises(ValidationError):
        query(TransactionQuery, "min_amount=500&max_amount=100")


def test_limit_is_bounded() -> None:
    """Unbounded, this was `int(args.get("limit", 50))` and a client could ask for a full
    table scan by typo."""
    with pytest.raises(ValidationError) as exc:
        query(TransactionQuery, "limit=10000000")

    assert "limit" in exc.value.details["fields"]


def test_a_non_numeric_limit_is_a_validation_error_not_a_crash() -> None:
    with pytest.raises(ValidationError) as exc:
        query(TransactionQuery, "limit=banana")

    assert exc.value.status_code == 400
    assert "limit" in exc.value.details["fields"]


def test_an_unknown_filter_is_rejected_rather_than_silently_ignored() -> None:
    """A misspelled filter that is quietly dropped returns the wrong rows and looks right."""
    with pytest.raises(ValidationError) as exc:
        query(TransactionQuery, "catgory_id=abc")

    assert "catgory_id" in exc.value.details["fields"]


def test_enum_filters_parse_to_their_members() -> None:
    parsed = query(
        TransactionQuery, "payment_method=debit_order&spending_purpose=rent"
    )

    assert parsed.payment_method is PaymentMethod.DEBIT_ORDER
    assert parsed.spending_purpose is SpendingPurpose.RENT


def test_an_unknown_enum_value_names_the_field() -> None:
    with pytest.raises(ValidationError) as exc:
        query(TransactionQuery, "spending_purpose=yacht")

    assert "spending_purpose" in exc.value.details["fields"]


def test_min_score_must_be_a_ratio() -> None:
    with pytest.raises(ValidationError):
        query(TransactionQuery, "min_score=1.5")


def test_what_if_increments_accept_the_documented_comma_separated_form() -> None:
    parsed = query(WhatIfQuery, "increments=100,500,1000")

    assert parsed.increments == [Decimal("100"), Decimal("500"), Decimal("1000")]


def test_a_non_positive_what_if_increment_is_rejected() -> None:
    with pytest.raises(ValidationError):
        query(WhatIfQuery, "increments=100,0")


# --------------------------------------------------------------------------------------
# Bodies
# --------------------------------------------------------------------------------------
def test_a_missing_required_body_field_is_named() -> None:
    with pytest.raises(ValidationError) as exc:
        body(RegisterRequest, {"email": "nadia@example.com"})

    assert "password" in exc.value.details["fields"]
    assert "full_name" in exc.value.details["fields"]


def test_an_invalid_email_is_rejected() -> None:
    with pytest.raises(ValidationError) as exc:
        body(
            RegisterRequest,
            {"email": "not-an-email", "password": "a" * 12, "full_name": "Nadia"},
        )

    assert "email" in exc.value.details["fields"]


def test_a_short_password_is_rejected_at_registration() -> None:
    with pytest.raises(ValidationError) as exc:
        body(
            RegisterRequest,
            {"email": "nadia@example.com", "password": "short", "full_name": "Nadia"},
        )

    assert "password" in exc.value.details["fields"]


def test_money_is_parsed_from_its_string_form() -> None:
    """ADR-001: money crosses the wire as a string, and must not become a float on the way
    in. `Decimal("14500.55")` is exact; `Decimal(14500.55)` is not."""
    parsed = body(
        ManualTransactionRequest,
        {
            "account_id": str(uuid4()),
            "occurred_on": "2026-09-01",
            "amount": "-14500.55",
            "description": "DEBIT ORDER RENT",
        },
    )

    assert parsed.amount == Decimal("-14500.55")


def test_a_zero_amount_transaction_is_rejected() -> None:
    with pytest.raises(ValidationError) as exc:
        body(
            ManualTransactionRequest,
            {
                "account_id": str(uuid4()),
                "occurred_on": "2026-09-01",
                "amount": "0",
                "description": "nothing",
            },
        )

    assert "amount" in exc.value.details["fields"]


def test_a_blank_term_months_means_a_revolving_facility_not_a_zero_term() -> None:
    """docs/frontend.md §4 forbids the client narrowing strings to numbers, so a cleared
    "term in months" input arrives as "". Rejecting it would make a credit card impossible
    to record from the form that exists."""
    parsed = body(
        CreateDebtRequest,
        {
            "debt_type": "credit_card",
            "original_principal": "20000.00",
            "current_balance": "20000.00",
            "annual_rate": "0.24",
            "minimum_payment": "600.00",
            "started_on": "2026-01-01",
            "term_months": "",
        },
    )

    assert parsed.term_months is None


def test_a_negative_minimum_payment_is_rejected() -> None:
    with pytest.raises(ValidationError) as exc:
        body(
            CreateDebtRequest,
            {
                "debt_type": "credit_card",
                "original_principal": "20000.00",
                "current_balance": "20000.00",
                "annual_rate": "0.24",
                "minimum_payment": "-600.00",
                "started_on": "2026-01-01",
            },
        )

    assert "minimum_payment" in exc.value.details["fields"]


def test_an_empty_debt_update_is_rejected() -> None:
    """A PATCH that changes nothing is a client bug, and answering 200 hides it."""
    with pytest.raises(ValidationError):
        body(UpdateDebtRequest, {})


def test_a_conflict_resolution_must_be_one_of_the_three_documented_actions() -> None:
    with pytest.raises(ValidationError):
        body(
            ResolveImportRequest,
            {"resolutions": [{"candidate_id": str(uuid4()), "action": "delete"}]},
        )


def test_a_valid_conflict_resolution_parses() -> None:
    candidate = uuid4()
    parsed = body(
        ResolveImportRequest,
        {"resolutions": [{"candidate_id": str(candidate), "action": "merge"}]},
    )

    assert parsed.resolutions[0].candidate_id == candidate
    assert parsed.resolutions[0].action == "merge"


def test_a_non_object_body_is_rejected_with_a_readable_message() -> None:
    with app.test_request_context(
        "/", method="POST", data="[1, 2, 3]", content_type="application/json"
    ):
        with pytest.raises(ValidationError, match="JSON object"):
            parse_body(RegisterRequest)
