from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.core.db import DbSession

from app.core.auth import current_user_id, hash_password, log_in_user, log_out_user, verify_password
from app.core.errors import ConflictError, UnauthenticatedError
from app.models.user import User
from app.repositories.user import UserRepository


@dataclass(frozen=True, slots=True)
class RegisterInput:
    email: str
    password: str
    full_name: str


class AuthService:
    def __init__(self, session: DbSession) -> None:
        self._session = session
        self._users = UserRepository(session)

    def register(self, data: RegisterInput) -> User:
        if self._users.by_email(data.email) is not None:
            raise ConflictError("An account with that email already exists.")

        user = User(
            email=data.email,
            password_hash=hash_password(data.password),
            full_name=data.full_name,
        )
        self._users.add(user)
        self._session.commit()
        log_in_user(user.id)
        return user

    def login(self, *, email: str, password: str) -> User:
        user = self._users.by_email(email)
        if user is None or not verify_password(password, user.password_hash):
            raise UnauthenticatedError("Incorrect email or password.")

        user.last_login_at = datetime.now(UTC)
        self._session.commit()
        log_in_user(user.id)
        return user

    def logout(self) -> None:
        log_out_user()

    def current_user(self) -> User | None:
        user_id = current_user_id()
        if user_id is None:
            return None
        return self._users.by_id(user_id)
