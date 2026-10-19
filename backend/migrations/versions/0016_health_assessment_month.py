"""Give every health assessment the month it is about.

`computed_at` says when the assessment ran; it never said what period it described. History
was therefore a log of runs — two assessments on one afternoon read as two data points, and
a fortnight with no activity read as none — which is not a series anyone can ask "is this
improving?" of.

Existing rows are backfilled from `computed_at`'s own month, which is what they in fact
measured: the service has always scored the current calendar month.

Where two old rows fall in the same month, the most recently computed one is kept and the
others are deleted before the unique constraint goes on. They are re-runs of the same claim
about the same period, and the newest is the one that stood.

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-18
"""

from alembic import op
import sqlalchemy as sa

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "health_assessments",
        sa.Column("month", sa.String(), nullable=True),
        schema="analytics",
    )
    op.execute(
        """
        UPDATE analytics.health_assessments
           SET month = to_char(computed_at, 'YYYY-MM')
         WHERE month IS NULL
        """
    )

    # Keep the newest assessment per (user, month); the rest are superseded re-runs.
    op.execute(
        """
        DELETE FROM analytics.health_assessments a
         USING analytics.health_assessments b
         WHERE a.user_id = b.user_id
           AND a.month = b.month
           AND (a.computed_at, a.id) < (b.computed_at, b.id)
        """
    )

    op.alter_column("health_assessments", "month", nullable=False, schema="analytics")
    op.create_index(
        "ix_health_assessments_month", "health_assessments", ["month"], schema="analytics"
    )
    op.create_unique_constraint(
        "uq_health_assessment_month",
        "health_assessments",
        ["user_id", "month"],
        schema="analytics",
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_health_assessment_month", "health_assessments", schema="analytics", type_="unique"
    )
    op.drop_index("ix_health_assessments_month", table_name="health_assessments", schema="analytics")
    op.drop_column("health_assessments", "month", schema="analytics")
