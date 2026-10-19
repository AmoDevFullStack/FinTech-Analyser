"""Every table names the subsystem it belongs to. See app/models/schemas.py.

These run against `Base.metadata` alone, with no database, so they fail in seconds on a
new model that forgot its schema rather than at whatever point the first query against it
happens to run.
"""

from __future__ import annotations

import pathlib
import re

import pytest

import app.models  # noqa: F401  registers every model on Base.metadata
from app.models.base import Base
from app.models.schemas import ALL_SCHEMAS, SHARED

TABLE_SCHEMAS = frozenset(ALL_SCHEMAS) - {SHARED}

REPOSITORY_DIR = pathlib.Path(__file__).resolve().parents[2] / "app" / "repositories"

# Table name in raw SQL, unqualified: `FROM transactions` rather than
# `FROM ledger.transactions`. An unqualified name resolves through search_path, which
# differs between psql, the application connection, and Alembic.
UNQUALIFIED_SQL = re.compile(r"\b(FROM|JOIN|UPDATE|INSERT INTO)\s+(?!\()([a-z_]+)(?!\.)\b")

# `CAST(:status AS risk_status_enum)` — an enum type named without its schema. Types moved
# into `shared` in revision 0014, and a cast that omits it either resolves through
# search_path or fails outright with `type "risk_status_enum" does not exist`.
UNQUALIFIED_ENUM_CAST = re.compile(r"\bAS\s+(?!shared\.)([a-z_]+_enum)\b")


def test_every_table_declares_a_schema():
    missing = sorted(name for name, table in Base.metadata.tables.items() if table.schema is None)
    assert missing == [], (
        f"These tables have no schema: {missing}. Give each one "
        f'__table_args__ = {{"schema": ...}} from app/models/schemas.py.'
    )


def test_every_table_schema_is_one_this_application_owns():
    unknown = sorted(
        {
            table.schema
            for table in Base.metadata.tables.values()
            if table.schema not in TABLE_SCHEMAS
        }
    )
    assert unknown == [], (
        f"Tables declare schemas that are not in app/models/schemas.py: {unknown}. Add the "
        f"schema there — including it in ALL_SCHEMAS is what creates it — or use an "
        f"existing one."
    )


def test_no_table_sits_in_the_enum_schema():
    """`shared` holds Postgres enum types only, so dropping a subsystem never has to
    reason about whether a table went along with its type."""
    in_shared = sorted(
        name for name, table in Base.metadata.tables.items() if table.schema == SHARED
    )
    assert in_shared == []


@pytest.mark.parametrize(
    "path", sorted(REPOSITORY_DIR.glob("*.py")), ids=lambda path: path.name
)
def test_raw_sql_names_tables_with_their_schema(path):
    source = path.read_text(encoding="utf-8")
    unqualified = [
        f"{keyword} {table}" for keyword, table in UNQUALIFIED_SQL.findall(source)
    ]
    assert unqualified == [], (
        f"{path.name} refers to {unqualified} without a schema. Write the schema out "
        f"(`FROM ledger.transactions`) — search_path is not the same in psql, in the "
        f"application, and in Alembic."
    )


@pytest.mark.parametrize(
    "path", sorted(REPOSITORY_DIR.glob("*.py")), ids=lambda path: path.name
)
def test_raw_sql_names_enum_types_with_their_schema(path):
    source = path.read_text(encoding="utf-8")
    unqualified = UNQUALIFIED_ENUM_CAST.findall(source)
    assert unqualified == [], (
        f"{path.name} casts to {unqualified} without a schema. Enum types live in "
        f"`shared` since revision 0014: write `CAST(:status AS shared.risk_status_enum)`."
    )
