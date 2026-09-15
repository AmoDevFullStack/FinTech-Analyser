from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TypeVar

from sqlalchemy import DateTime, Enum as SAEnum, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.ids import uuid7


class Base(DeclarativeBase):
    pass


_E = TypeVar("_E", bound=enum.Enum)


def pg_enum(enum_cls: type[_E], *, name: str) -> SAEnum:
    """The column type for every Python str-Enum this schema stores.

    SQLAlchemy's `Enum` stores a Python enum member's NAME by default (`VEHICLE_FINANCE`),
    not its `.value` — even for a `str` subclass enum. The Postgres enum types created in
    migrations/ use the lowercase `.value` strings (matching docs/database.md and
    docs/api.md), so every enum column must set `values_callable` or every insert fails
    with "invalid input value for enum ...". This is the one place that's done, so no
    column definition can forget it.
    """
    return SAEnum(enum_cls, name=name, values_callable=lambda x: [e.value for e in x])


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid7
    )


class TimestampMixin:
    """created_at/updated_at on every table, per docs/database.md §1.

    updated_at is maintained by a database trigger (migrations/versions/0001), not by
    application code, so it cannot be forgotten by a call site.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
