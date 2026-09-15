from __future__ import annotations

import enum
from uuid import UUID

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, pg_enum


class CategoryKind(str, enum.Enum):
    INCOME = "income"
    ESSENTIAL = "essential"
    DISCRETIONARY = "discretionary"
    DEBT = "debt"
    SAVING = "saving"
    TRANSFER = "transfer"


class Category(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "categories"

    user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    parent_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("categories.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[CategoryKind] = mapped_column(
        pg_enum(CategoryKind, name="category_kind_enum"), nullable=False
    )
