"""Persist whether an assistant answer was model-written. See app/models/assistant.py.

Capability.SMALL_TALK can write the deterministic fallback line into `answer` when no
provider is configured, so `answer IS NOT NULL` stops being a reliable proxy for "the
model wrote this" the way it was for every other capability. This column makes that
explicit instead of leaving the client to infer it.

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-16
"""

from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "assistant_messages",
        sa.Column("narration_available", sa.Boolean(), nullable=True),
    )
    # Backfill: for every row written before this column existed, `answer` was only ever
    # set when the model actually narrated it, so the two are equivalent for that history.
    op.execute("UPDATE assistant_messages SET narration_available = (answer IS NOT NULL)")
    op.alter_column(
        "assistant_messages",
        "narration_available",
        nullable=False,
        server_default=sa.text("false"),
    )


def downgrade() -> None:
    op.drop_column("assistant_messages", "narration_available")
