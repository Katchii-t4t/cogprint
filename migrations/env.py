"""Alembic environment.

The URL and metadata come from the application rather than alembic.ini, so
there is one source of truth: set DATABASE_URL and the app, the tests and the
migrations all agree.
"""

from logging.config import fileConfig
import os
import sys

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make the project root importable however alembic was invoked.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import DATABASE_URL, Base  # noqa: E402

config = context.config

# URL resolution, most specific first: a url the caller set on the Config (tests,
# tooling) wins; otherwise the application's DATABASE_URL. alembic.ini ships with
# the url blank so it can never silently shadow either. Escaped because
# ConfigParser reads a bare % as interpolation and Postgres passwords are
# percent-encoded.
_url = config.get_main_option("sqlalchemy.url") or DATABASE_URL
config.set_main_option("sqlalchemy.url", _url.replace("%", "%%"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _include_object(obj, name, type_, reflected, compare_to):
    """Ignore Alembic's own bookkeeping table during autogenerate."""
    return not (type_ == "table" and name == "alembic_version")


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # SQLite cannot ALTER most columns; batch mode rewrites the table
        # instead. A no-op on Postgres, essential for local development.
        render_as_batch=True,
        include_object=_include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def _run(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,
        include_object=_include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # A caller may hand us a live connection (database.init_db does, so the
    # stamp lands on the engine the app is actually using rather than whatever
    # DATABASE_URL happened to be at import time).
    existing = config.attributes.get("connection")
    if existing is not None:
        _run(existing)
        return

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        _run(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
