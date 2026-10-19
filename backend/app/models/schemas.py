"""The Postgres schema every table belongs to.

One flat `public` namespace stops telling you anything once a product has twenty tables:
`risk_flags` and `transactions` sit side by side although one is a computed opinion and
the other is banking fact. Each subsystem here owns a schema, so a query says which
subsystem it reads — `ledger.transactions`, `assistant.conversations` — and a new
subsystem is added without crowding the tables that already exist.

Rules that go with this file, stated in docs/database.md §1:

- Every table declares its schema in `__table_args__`. A table without one is a design
  error, and tests/models/test_schema_namespaces.py fails the build for it.
- Every `ForeignKey` is written schema-qualified (`identity.users.id`), and so is every
  table name in raw SQL. Nothing relies on `search_path`, because search_path differs
  between psql, the application connection, and Alembic — and that difference is how the
  same table gets created twice.
- Postgres enum *types* all live in SHARED rather than in the schema of whichever table
  first needed them: `payment_method_enum` is used by both `ledger.transactions` and
  `ledger.staged_transactions` today, and a type that moves schema when its second user
  appears is a migration nobody expects to write.
"""

from __future__ import annotations

from sqlalchemy.schema import CreateSchema

#: Who the user is. Authentication state, nothing financial.
IDENTITY = "identity"

#: Banking fact: what the bank said happened, and what it happened to.
LEDGER = "ledger"

#: What the user owes and what they are saving towards.
OBLIGATIONS = "obligations"

#: Computed output — projections, scores, flags, advice. Every table here is derivable
#: from LEDGER and OBLIGATIONS, and none of it is a source of truth.
ANALYTICS = "analytics"

#: The question-and-answer transcript. Kept apart from ANALYTICS on purpose: ADR-002 puts
#: a boundary between figures a model narrated and figures an engine computed, and a
#: schema boundary is the cheapest place to see that one is being honoured.
ASSISTANT = "assistant"

#: Append-only record of what happened, for reading after the fact.
AUDIT = "audit"

#: Postgres enum types only. No tables.
SHARED = "shared"

ALL_SCHEMAS: tuple[str, ...] = (
    IDENTITY,
    LEDGER,
    OBLIGATIONS,
    ANALYTICS,
    ASSISTANT,
    AUDIT,
    SHARED,
)


def ensure_schemas(connection) -> None:
    """Create every schema this metadata expects, if it is not already there.

    `Base.metadata.create_all()` creates tables, never the schemas that hold them, so a
    fresh database fails with `InvalidSchemaName` before the first table is built. Both
    the test fixtures and the Alembic environment call this first for that reason.
    """
    for name in ALL_SCHEMAS:
        connection.execute(CreateSchema(name, if_not_exists=True))
