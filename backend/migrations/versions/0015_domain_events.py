"""audit.events — the transactional outbox. See app/core/events.py.

A service writes one row here in the same transaction as the work it describes, so a
committed import and the record that it was committed cannot disagree. `dispatch_pending`
then runs the handlers registered for that event name, after the commit, and stamps
`processed_at`.

Rows are never deleted. "Which import recomputed the health score, and when" is a question
worth being able to answer later, and a table that deletes its history cannot answer it.

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-18
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("identity.users.id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema="audit",
    )
    op.create_index("ix_events_user_id", "events", ["user_id"], schema="audit")
    op.create_index("ix_events_name", "events", ["name"], schema="audit")
    # Partial, on the only question the dispatcher asks: what is still outstanding. The
    # processed rows accumulate for the audit trail and are never read by this path, so
    # keeping them out of the index keeps it the size of the backlog rather than the size
    # of the history.
    op.create_index(
        "ix_events_pending",
        "events",
        ["occurred_at"],
        schema="audit",
        postgresql_where=sa.text("processed_at IS NULL"),
    )
    op.execute(
        "CREATE TRIGGER events_set_updated_at BEFORE UPDATE ON audit.events "
        "FOR EACH ROW EXECUTE FUNCTION shared.set_updated_at()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS events_set_updated_at ON audit.events")
    op.drop_index("ix_events_pending", table_name="events", schema="audit")
    op.drop_index("ix_events_name", table_name="events", schema="audit")
    op.drop_index("ix_events_user_id", table_name="events", schema="audit")
    op.drop_table("events", schema="audit")
