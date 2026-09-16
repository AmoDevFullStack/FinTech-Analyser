from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, text

from app.core.db import DbSession
from app.models.assistant import AssistantConversation, AssistantMessage

_LIST_FOR_USER = text(
    """
    SELECT *
      FROM assistant_conversations
     WHERE user_id = :user_id
     ORDER BY started_at DESC
    """
)

_GET_FOR_USER = text(
    """
    SELECT *
      FROM assistant_conversations
     WHERE id = :conversation_id
       AND user_id = :user_id
    """
)

_MESSAGES_FOR = text(
    """
    SELECT *
      FROM assistant_messages
     WHERE conversation_id = :conversation_id
       AND user_id = :user_id
     ORDER BY asked_at
    """
)


class AssistantRepository:
    """Every method takes `user_id` and filters on it — see docs/architecture.md §3.4."""

    def __init__(self, session: DbSession) -> None:
        self._session = session

    def list_for_user(self, *, user_id: UUID) -> list[AssistantConversation]:
        return list(
            self._session.scalars(
                select(AssistantConversation).from_statement(_LIST_FOR_USER),
                {"user_id": user_id},
            )
        )

    def get_for_user(
        self, conversation_id: UUID, *, user_id: UUID
    ) -> AssistantConversation | None:
        return self._session.scalars(
            select(AssistantConversation).from_statement(_GET_FOR_USER),
            {"conversation_id": conversation_id, "user_id": user_id},
        ).first()

    def messages_for(self, conversation_id: UUID, *, user_id: UUID) -> list[AssistantMessage]:
        return list(
            self._session.scalars(
                select(AssistantMessage).from_statement(_MESSAGES_FOR),
                {"conversation_id": conversation_id, "user_id": user_id},
            )
        )

    def add_conversation(self, conversation: AssistantConversation) -> AssistantConversation:
        self._session.add(conversation)
        self._session.flush()
        return conversation

    def add_message(self, message: AssistantMessage) -> AssistantMessage:
        self._session.add(message)
        self._session.flush()
        return message
