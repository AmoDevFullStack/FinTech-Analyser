"""Assistant conversations and messages. See specs/ai-cfo.md.

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-15
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assistant_conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_assistant_conversations_user_id", "assistant_conversations", ["user_id"])
    op.execute(
        "CREATE TRIGGER assistant_conversations_set_updated_at BEFORE UPDATE ON assistant_conversations "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )

    op.create_table(
        "assistant_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("assistant_conversations.id"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("asked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("question", sa.String(), nullable=False),
        # Model-generated prose lives here and nowhere else. No financial column in this
        # schema is ever populated from model output -- ADR-002.
        sa.Column("answer", sa.String(), nullable=True),
        sa.Column("capability", sa.String(), nullable=False),
        sa.Column("supported", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("figures", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_assistant_messages_conversation_id", "assistant_messages", ["conversation_id"])
    op.create_index("ix_assistant_messages_user_id", "assistant_messages", ["user_id"])
    op.execute(
        "CREATE TRIGGER assistant_messages_set_updated_at BEFORE UPDATE ON assistant_messages "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS assistant_messages_set_updated_at ON assistant_messages")
    op.drop_index("ix_assistant_messages_user_id", table_name="assistant_messages")
    op.drop_index("ix_assistant_messages_conversation_id", table_name="assistant_messages")
    op.drop_table("assistant_messages")
    op.execute("DROP TRIGGER IF EXISTS assistant_conversations_set_updated_at ON assistant_conversations")
    op.drop_index("ix_assistant_conversations_user_id", table_name="assistant_conversations")
    op.drop_table("assistant_conversations")
