from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, text

from app.core.db import DbSession

from app.models.user import User

_BY_EMAIL = text(
    """
    SELECT *
      FROM users
     WHERE email = :email
    """
)

_BY_ID = text(
    """
    SELECT *
      FROM users
     WHERE id = :user_id
    """
)


class UserRepository:
    def __init__(self, session: DbSession) -> None:
        self._session = session

    def by_email(self, email: str) -> User | None:
        return self._session.scalars(
            select(User).from_statement(_BY_EMAIL), {"email": email}
        ).first()

    def by_id(self, user_id: UUID) -> User | None:
        return self._session.scalars(
            select(User).from_statement(_BY_ID), {"user_id": user_id}
        ).first()

    def add(self, user: User) -> User:
        self._session.add(user)
        self._session.flush()
        return user
