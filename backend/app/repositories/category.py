from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, text

from app.core.db import DbSession

from app.models.category import Category

_LIST_FOR_USER = text(
    """
    SELECT *
      FROM ledger.categories
     WHERE user_id = :user_id
        OR user_id IS NULL
    """
)

_GET = text(
    """
    SELECT *
      FROM ledger.categories
     WHERE id = :category_id
    """
)

_LIST_SYSTEM = text(
    """
    SELECT *
      FROM ledger.categories
     WHERE user_id IS NULL
     ORDER BY name
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

    def list_system(self) -> list[Category]:
        """The shared chart of accounts — categories with no owner.

        Separate from `list_for_user` because the seeder needs to know what already exists
        globally without a user to scope by, and calling `list_for_user` with an arbitrary
        user to get at the system rows would be a lie about what the query means.
        """
        return list(self._session.scalars(select(Category).from_statement(_LIST_SYSTEM)))

    def get(self, category_id: UUID) -> Category | None:
        return self._session.scalars(
            select(Category).from_statement(_GET), {"category_id": category_id}
        ).first()
