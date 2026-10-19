"""Deleting a conversation. See AssistantService.delete_conversation.

A hard delete, unlike the financial tables: a transcript holds a question and narration
over figures stored elsewhere, so removing it destroys no financial record. What these
tests hold to is that it removes everything in the thread, removes nothing outside it, and
cannot reach another user's threads at all.
"""

from datetime import datetime, timezone

import pytest

from app.core.auth import hash_password
from app.core.errors import NotFoundError
from app.models.assistant import AssistantConversation, AssistantMessage
from app.models.user import User
from app.repositories.assistant import AssistantRepository
from app.services.assistant import AssistantService


def _make_user(session, email: str) -> User:
    user = User(email=email, password_hash=hash_password("x"), full_name="Test User")
    session.add(user)
    session.flush()
    return user


def _make_conversation(session, user, *, title: str, messages: int = 2):
    conversation = AssistantConversation(
        user_id=user.id, started_at=datetime.now(timezone.utc), title=title
    )
    session.add(conversation)
    session.flush()

    for index in range(messages):
        session.add(
            AssistantMessage(
                conversation_id=conversation.id,
                user_id=user.id,
                asked_at=datetime.now(timezone.utc),
                question=f"Question {index}",
                answer="An answer.",
                capability="position_query",
                supported=True,
                narration_available=True,
                figures=[],
            )
        )
    session.commit()
    return conversation


def test_deleting_a_conversation_removes_its_messages_too(session):
    user = _make_user(session, "delete-thread@example.com")
    conversation = _make_conversation(session, user, title="Net worth check")
    repository = AssistantRepository(session)
    # Read before the delete. Afterwards the row is gone, and asking the instance for its
    # id is a question about a row that no longer exists.
    conversation_id = conversation.id

    AssistantService(session).delete_conversation(conversation_id, user_id=user.id)

    assert repository.get_for_user(conversation_id, user_id=user.id) is None
    assert repository.messages_for(conversation_id, user_id=user.id) == []


def test_deleting_one_conversation_leaves_the_others_alone(session):
    user = _make_user(session, "delete-one@example.com")
    doomed = _make_conversation(session, user, title="Delete me")
    kept = _make_conversation(session, user, title="Keep me")
    doomed_id, kept_id = doomed.id, kept.id

    AssistantService(session).delete_conversation(doomed_id, user_id=user.id)

    repository = AssistantRepository(session)
    assert repository.get_for_user(doomed_id, user_id=user.id) is None
    assert repository.get_for_user(kept_id, user_id=user.id) is not None
    assert len(repository.messages_for(kept_id, user_id=user.id)) == 2


def test_a_conversation_belonging_to_someone_else_is_not_found(session):
    """404, the same answer as one that does not exist — so the endpoint cannot be used to
    discover that an identifier belongs to somebody."""
    owner = _make_user(session, "owner@example.com")
    stranger = _make_user(session, "stranger@example.com")
    conversation = _make_conversation(session, owner, title="Private")
    conversation_id = conversation.id

    with pytest.raises(NotFoundError):
        AssistantService(session).delete_conversation(conversation_id, user_id=stranger.id)

    assert AssistantRepository(session).get_for_user(conversation_id, user_id=owner.id) is not None


def test_deleting_something_that_is_not_there_is_not_found(session):
    from uuid import uuid4

    user = _make_user(session, "missing@example.com")

    with pytest.raises(NotFoundError):
        AssistantService(session).delete_conversation(uuid4(), user_id=user.id)


def test_the_delete_endpoint_returns_204(client, session):
    """Through the route, to prove the blueprint and the auth decorator are wired."""
    from app.core.tokens import issue_token_pair

    user = _make_user(session, "route@example.com")
    conversation = _make_conversation(session, user, title="Via HTTP")
    conversation_id = conversation.id
    tokens = issue_token_pair(user.id)

    response = client.delete(
        f"/api/v1/assistant/conversations/{conversation_id}",
        headers={"Authorization": f"Bearer {tokens.access_token}"},
    )

    assert response.status_code == 204
    assert AssistantRepository(session).get_for_user(conversation_id, user_id=user.id) is None


def test_the_conversation_a_caller_held_stays_readable_after_deletion(session):
    """The service detaches what it loaded instead of leaving it expired against a row
    that no longer exists.

    Without that, the next attribute read on the instance — in a log line, in a response
    saying which conversation was removed — re-queries and raises ObjectDeletedError,
    somewhere unrelated to the delete.
    """
    user = _make_user(session, "detached@example.com")
    conversation = _make_conversation(session, user, title="Net worth check")
    conversation_id = conversation.id

    AssistantService(session).delete_conversation(conversation_id, user_id=user.id)

    assert conversation.title == "Net worth check"
    assert AssistantRepository(session).get_for_user(conversation_id, user_id=user.id) is None
