"""Move every table out of `public` into a per-subsystem schema.

One flat namespace stopped carrying information at about twenty tables: `risk_flags` and
`transactions` sat beside each other although one is a computed opinion and the other is
banking fact. After this revision a query names the subsystem it reads —
`ledger.transactions`, `assistant.conversations`, `analytics.forecasts` — and a new
subsystem arrives as a new schema rather than as more tables in the same pile. The schema
each table belongs to, and the rules that go with it, are in app/models/schemas.py.

Three table names lose a prefix that only existed because the namespace was flat:

    account_column_mappings -> ledger.column_mappings
    assistant_conversations -> assistant.conversations
    assistant_messages      -> assistant.messages
    audit_logs              -> audit.logs

`ALTER TABLE ... SET SCHEMA` moves the table with its indexes, constraints, triggers, and
data; nothing is copied and no row is rewritten, so this is fast on a populated database
and loses nothing. Foreign keys follow their tables automatically, because a constraint
references a table by identity rather than by name.

Enum types move too, into `shared`. A type left in `public` would resolve only through
`search_path`, which is not the same in psql, in the application connection, and in
Alembic — and relying on it is how the same object gets created twice. `set_updated_at()`
moves for the same reason. Existing triggers keep working across the move: a trigger
records the function it calls by identity, not by name.

`citext` stays in `public`, deliberately. An extension is database-wide rather than owned
by any subsystem, and `public` is where every tool expects to find one.

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-18
"""

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

SCHEMAS = ("identity", "ledger", "obligations", "analytics", "assistant", "audit", "shared")

# (current table name, schema it moves to, name it takes there)
TABLES = (
    ("users", "identity", "users"),
    ("accounts", "ledger", "accounts"),
    ("categories", "ledger", "categories"),
    ("transactions", "ledger", "transactions"),
    ("import_batches", "ledger", "import_batches"),
    ("staged_transactions", "ledger", "staged_transactions"),
    ("account_column_mappings", "ledger", "column_mappings"),
    ("debts", "obligations", "debts"),
    ("goals", "obligations", "goals"),
    ("goal_contributions", "obligations", "goal_contributions"),
    ("position_snapshots", "analytics", "position_snapshots"),
    ("health_assessments", "analytics", "health_assessments"),
    ("forecasts", "analytics", "forecasts"),
    ("forecast_periods", "analytics", "forecast_periods"),
    ("forecast_accuracy", "analytics", "forecast_accuracy"),
    ("risk_flags", "analytics", "risk_flags"),
    ("recommendations", "analytics", "recommendations"),
    ("scenarios", "analytics", "scenarios"),
    ("scenario_assumptions", "analytics", "scenario_assumptions"),
    ("scenario_results", "analytics", "scenario_results"),
    ("assistant_conversations", "assistant", "conversations"),
    ("assistant_messages", "assistant", "messages"),
    ("audit_logs", "audit", "logs"),
)

ENUM_TYPES = (
    "account_type_enum",
    "actor_enum",
    "balance_source_enum",
    "category_kind_enum",
    "debt_type_enum",
    "direction_enum",
    "import_status_enum",
    "payment_method_enum",
    "recommendation_status_enum",
    "risk_status_enum",
    "scenario_status_enum",
    "scenario_type_enum",
    "spending_purpose_enum",
)


def upgrade() -> None:
    for schema in SCHEMAS:
        op.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')

    for enum_name in ENUM_TYPES:
        op.execute(f'ALTER TYPE public."{enum_name}" SET SCHEMA "shared"')

    op.execute('ALTER FUNCTION public.set_updated_at() SET SCHEMA "shared"')

    for table, schema, new_name in TABLES:
        op.execute(f'ALTER TABLE public."{table}" SET SCHEMA "{schema}"')
        if new_name != table:
            op.execute(f'ALTER TABLE "{schema}"."{table}" RENAME TO "{new_name}"')


def downgrade() -> None:
    for table, schema, new_name in TABLES:
        if new_name != table:
            op.execute(f'ALTER TABLE "{schema}"."{new_name}" RENAME TO "{table}"')
        op.execute(f'ALTER TABLE "{schema}"."{table}" SET SCHEMA public')

    op.execute('ALTER FUNCTION shared.set_updated_at() SET SCHEMA public')

    for enum_name in ENUM_TYPES:
        op.execute(f'ALTER TYPE shared."{enum_name}" SET SCHEMA public')

    # The schemas themselves are left in place: dropping one would take anything created
    # in it since this revision ran with it, which is not what reversing a move means.
