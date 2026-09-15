"""Decimal helpers for the money boundary. See ADR-001.

This module is the only place quantisation policy is defined. Domain engines quantise
their own period results per their own documented rounding policy (financial-domain-engine
skill) — this module is for the serialisation and repository boundary: turning a Decimal
into the exact string that crosses the API, and back.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CENTS = Decimal("0.01")
RATE_PLACES = Decimal("0.000001")


def to_cents(value: Decimal) -> Decimal:
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)


def to_rate_precision(value: Decimal) -> Decimal:
    return value.quantize(RATE_PLACES, rounding=ROUND_HALF_UP)


def money_to_wire(value: Decimal) -> str:
    """Render a Decimal as the fixed two-place string the API contract requires."""
    return str(to_cents(value))


def money_from_wire(value: str) -> Decimal:
    """Parse a money string from a request body. Never accepts a JSON number — the
    caller's schema layer is responsible for rejecting non-string input before this runs.
    """
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"not a valid decimal string: {value!r}") from exc
