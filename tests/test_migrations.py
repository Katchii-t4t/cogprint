"""
Migration integrity.

Tests build their schema with ``create_all`` (fast, isolated), while real
databases are built by Alembic. That split is only safe if the two cannot
drift, so the first test asserts exactly that: applying every migration to an
empty database must produce the schema the models describe, with nothing left
for autogenerate to do.

Without it, a model change with no matching migration passes the whole suite
and then fails in production — which is precisely how the missing
last_rebuild_* columns took the API down locally.
"""

import os
import tempfile

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

import database

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture()
def migrated_engine():
    """An empty database with every migration applied."""
    tmp = tempfile.mkdtemp(prefix="cogprint_migrations_")
    url = f"sqlite:///{os.path.join(tmp, 'migrated.db')}"

    cfg = Config(os.path.join(_ROOT, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(_ROOT, "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")

    engine = create_engine(url)
    try:
        yield engine
    finally:
        engine.dispose()


def test_migrations_match_the_models(migrated_engine):
    """Autogenerate against the migrated schema must find no differences."""
    with migrated_engine.connect() as conn:
        ctx = MigrationContext.configure(
            conn,
            opts={
                "compare_type": True,
                "include_object": lambda obj, name, type_, reflected, compare_to: not (
                    type_ == "table" and name == "alembic_version"
                ),
            },
        )
        diff = compare_metadata(ctx, database.Base.metadata)

    assert diff == [], (
        "models and migrations have drifted — run:\n"
        "    alembic revision --autogenerate -m '<what changed>'\n"
        f"unapplied differences: {diff}"
    )


def test_migrations_create_every_table(migrated_engine):
    tables = set(inspect(migrated_engine).get_table_names())
    expected = set(database.Base.metadata.tables) | {"alembic_version"}
    assert expected <= tables, f"missing after upgrade: {expected - tables}"


def test_recovery_token_hash_is_indexed_and_unique(migrated_engine):
    """The recovery lookup is by hash, so the index is a correctness concern
    (table scan per attempt) as well as a uniqueness guarantee."""
    inspector = inspect(migrated_engine)
    indexed = {
        col
        for idx in inspector.get_indexes("users")
        for col in idx["column_names"]
    }
    unique = {
        col
        for idx in inspector.get_indexes("users")
        if idx["unique"]
        for col in idx["column_names"]
    }
    assert "recovery_token_hash" in indexed
    assert "recovery_token_hash" in unique


def test_init_db_stamps_a_fresh_database(tmp_path, monkeypatch):
    """A database created from the models is stamped, so the next migration
    applies instead of trying to re-create existing tables."""
    url = f"sqlite:///{tmp_path / 'fresh.db'}"
    engine = create_engine(url)
    monkeypatch.setattr(database, "engine", engine)

    database.init_db()

    tables = set(inspect(engine).get_table_names())
    assert "users" in tables
    assert "alembic_version" in tables, "fresh database was not stamped"
    engine.dispose()
