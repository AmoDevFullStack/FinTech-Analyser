from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import load_config
from app.models.base import Base
from app.models.schemas import ALL_SCHEMAS, ensure_schemas
import app.models  # noqa: F401  ensures every model is registered on Base.metadata

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", load_config().SQLALCHEMY_DATABASE_URI)
target_metadata = Base.metadata

# Alembic's own bookkeeping table. Left in `public` deliberately: it belongs to the
# migration tool, not to any subsystem, and pinning it to a subsystem schema would make
# that subsystem undroppable.
VERSION_TABLE_SCHEMA = "public"

_KNOWN_SCHEMAS = frozenset(ALL_SCHEMAS) | {VERSION_TABLE_SCHEMA, None}


def include_object(obj, name, type_, reflected, compare_to) -> bool:
    """Keep autogenerate inside the schemas this application owns.

    `include_schemas=True` makes Alembic reflect every schema the connection can see, and
    without this filter it reads anything else living in the database — an extension's
    tables, another application sharing the instance — as tables missing from the metadata
    and writes DROP TABLE for them.
    """
    if type_ in {"table", "column", "index", "unique_constraint", "foreign_key_constraint"}:
        return getattr(obj, "schema", None) in _KNOWN_SCHEMAS
    return True


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        include_schemas=True,
        include_object=include_object,
        version_table_schema=VERSION_TABLE_SCHEMA,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        # Before configure(), not inside a migration: revision 0014 moves tables into
        # these schemas and needs them to exist, and every later revision creates tables
        # directly in them. A schema that only appears when one particular revision runs
        # cannot be relied on by the revisions after it.
        ensure_schemas(connection)
        connection.commit()

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            include_object=include_object,
            version_table_schema=VERSION_TABLE_SCHEMA,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
