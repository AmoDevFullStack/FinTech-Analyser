from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from app.core.db import DbSession

from app.models.user import User


class UserRepository:
    def __init__(self, session: DbSession) -> None:
        self._session = session

    def by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email)
        return self._session.scalars(stmt).first()

    def by_id(self, user_id: UUID) -> User | None:
        return self._session.get(User, user_id)

    def add(self, user: User) -> User:
        self._session.add(user)
        self._session.flush()
        return user
