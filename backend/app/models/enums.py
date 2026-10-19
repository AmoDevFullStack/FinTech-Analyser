"""Postgres enum types shared by more than one table.

`pg_enum` in app/models/base.py builds a fresh `Enum` object per call, which is right for a
type only one table uses. `payment_method_enum` and `spending_purpose_enum` are used by
both `transactions` and `staged_transactions`, and two `Enum` objects with the same name
each try to emit their own CREATE TYPE. Binding one object per type to `Base.metadata`
makes the type a property of the schema rather than of a column, so it is created once
before any table that references it and dropped once after — the same "emit CREATE TYPE
once per enum" rule the 0005/0007/0009 migrations were fixed to follow.
"""

from __future__ import annotations

from sqlalchemy import Enum as SAEnum

from app.domain.payment_taxonomy import PaymentMethod, SpendingPurpose
from app.models.base import Base
from app.models.schemas import SHARED

PAYMENT_METHOD_ENUM = SAEnum(
    PaymentMethod,
    name="payment_method_enum",
    schema=SHARED,
    metadata=Base.metadata,
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
)

SPENDING_PURPOSE_ENUM = SAEnum(
    SpendingPurpose,
    name="spending_purpose_enum",
    schema=SHARED,
    metadata=Base.metadata,
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
)
