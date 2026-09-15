from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.core.db import DbSession
from app.models.assistant import AssistantConversation, AssistantMessage


class AssistantRepository:
    """Every method takes `user_id` and filters on it — see docs/architecture.md §3.4."""

    def __init__(self, session: DbSession) -> None:
        self._session = session

    def list_for_user(self, *, user_id: UUID) -> list[AssistantConversation]:
        stmt = (
            select(AssistantConversation)
            .where(AssistantConversation.user_id == user_id)
            .order_by(AssistantConversation.started_at.desc())
        )
        return list(self._session.scalars(stmt))

    def get_for_user(
        self, conversation_id: UUID, *, user_id: UUID
    ) -> AssistantConversation | None:
        stmt = select(AssistantConversation).where(
            AssistantConversation.id == conversation_id,
            AssistantConversation.user_id == user_id,
        )
        return self._session.scalars(stmt).first()

    def messages_for(self, conversation_id: UUID, *, user_id: UUID) -> list[AssistantMessage]:
        stmt = (
            select(AssistantMessage)
            .where(
                AssistantMessage.conversation_id == conversation_id,
                AssistantMessage.user_id == user_id,
            )
            .order_by(AssistantMessage.asked_at)
        )
        return list(self._session.scalars(stmt))

    def add_conversation(self, conversation: AssistantConversation) -> AssistantConversation:
        self._session.add(conversation)
        self._session.flush()
        return conversation

    def add_message(self, message: AssistantMessage) -> AssistantMessage:
        self._session.add(message)
        self._session.flush()
        return message
