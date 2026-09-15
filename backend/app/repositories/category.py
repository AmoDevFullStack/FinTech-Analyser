from __future__ import annotations

from uuid import UUID

from sqlalchemy import or_, select
from app.core.db import DbSession

from app.models.category import Category


class CategoryRepository:
    def __init__(self, session: DbSession) -> None:
        self._session = session

    def list_for_user(self, *, user_id: UUID) -> list[Category]:
        stmt = select(Category).where(or_(Category.user_id == user_id, Category.user_id.is_(None)))
        return list(self._session.scalars(stmt))

    def get(self, category_id: UUID) -> Category | None:
        return self._session.get(Category, category_id)
