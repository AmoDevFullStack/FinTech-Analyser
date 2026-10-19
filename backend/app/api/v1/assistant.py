from flask import Blueprint, g, jsonify, request

from app.core.auth import require_auth
from app.core.errors import ValidationError
from app.core.extensions import db
from app.llm.factory import build_interpreter
from app.services.assistant import AssistantService

bp = Blueprint("assistant", __name__, url_prefix="/assistant")


@bp.post("/ask")
@require_auth
def ask():
    """Figures are authoritative; `answer` is narration over them, per ADR-002.

    With no model provider configured the response carries the figures with
    `answer: null` and `narration_available: false`, and the client renders the numbers.
    """
    body = request.get_json(force=True, silent=True) or {}
    question = (body.get("question") or "").strip()
    if not question:
        raise ValidationError("'question' is required.")

    conversation_id = body.get("conversation_id")
    answer = AssistantService(db.session, interpreter=build_interpreter()).ask(
        user_id=g.user_id,
        question=question,
        conversation_id=conversation_id,
    )
    return jsonify(answer.as_dict()), 200


@bp.get("/conversations")
@require_auth
def list_conversations():
    conversations = AssistantService(db.session).list_conversations(user_id=g.user_id)
    return (
        jsonify(
            {
                "data": [
                    {
                        "id": str(c.id),
                        "title": c.title,
                        "started_at": c.started_at.isoformat(),
                    }
                    for c in conversations
                ]
            }
        ),
        200,
    )


@bp.get("/conversations/<uuid:conversation_id>")
@require_auth
def get_conversation(conversation_id):
    conversation, messages = AssistantService(db.session).conversation(
        conversation_id, user_id=g.user_id
    )
    return (
        jsonify(
            {
                "id": str(conversation.id),
                "title": conversation.title,
                "started_at": conversation.started_at.isoformat(),
                "messages": [
                    {
                        "id": str(m.id),
                        "asked_at": m.asked_at.isoformat(),
                        "question": m.question,
                        "answer": m.answer,
                        "capability": m.capability,
                        "supported": m.supported,
                        "narration_available": m.narration_available,
                        "figures": m.figures,
                    }
                    for m in messages
                ],
            }
        ),
        200,
    )


@bp.delete("/conversations/<uuid:conversation_id>")
@require_auth
def delete_conversation(conversation_id):
    """Delete a conversation and its messages.

    204, and 404 for a conversation that is not this user's — the same response as one
    that does not exist, so the endpoint cannot be used to discover that a given
    identifier belongs to somebody.

    A hard delete: a transcript holds a question and narration over figures stored
    elsewhere, so removing it destroys no financial record. See
    `AssistantService.delete_conversation`.
    """
    AssistantService(db.session).delete_conversation(conversation_id, user_id=g.user_id)
    return "", 204
