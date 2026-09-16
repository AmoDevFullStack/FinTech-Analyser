from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, text

from app.core.db import DbSession

from app.models.category import Category

_LIST_FOR_USER = text(
    """
    SELECT *
      FROM categories
     WHERE user_id = :user_id
        OR user_id IS NULL
    """
)

_GET = text(
    """
    SELECT *
      FROM categories
     WHERE id = :category_id
    """
)


class CategoryRepository:
    def __init__(self, session: DbSession) -> None:
        self._session = session

    def list_for_user(self, *, user_id: UUID) -> list[Category]:
        return list(
            self._session.scalars(
                select(Category).from_statement(_LIST_FOR_USER), {"user_id": user_id}
            )
        )

    def get(self, category_id: UUID) -> Category | None:
        return self._session.scalars(
            select(Category).from_statement(_GET), {"category_id": category_id}
        ).first()
