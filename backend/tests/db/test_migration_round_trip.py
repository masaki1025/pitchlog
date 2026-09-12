"""全 Alembic revision を base まで往復する統合検査。"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any

import psycopg
import pytest
from alembic import command
from alembic.script import ScriptDirectory

from .conftest import DisposablePostgres
from .test_alembic_migrations import _alembic_config, _sqlalchemy_url

pytestmark = pytest.mark.requires_db

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_VERSIONS_ROOT = _BACKEND_ROOT / "migrations" / "versions"


def _public_application_tables(
    connection: psycopg.Connection[Any],
) -> set[str]:
    """Public schema の Alembic 管理表以外の通常表を返す。"""
    rows = connection.execute(
        """
        SELECT relation.relname
        FROM pg_class AS relation
        JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
        WHERE namespace.nspname = 'public'
          AND relation.relkind IN ('r', 'p')
          AND relation.relname <> 'alembic_version'
        ORDER BY relation.relname
        """
    ).fetchall()
    return {str(row[0]) for row in rows}


def _applied_revisions(connection: psycopg.Connection[Any]) -> set[str]:
    """Alembic 管理表が持つ適用済み revision を返す。"""
    version_table = connection.execute(
        "SELECT to_regclass('public.alembic_version')"
    ).fetchone()
    if version_table is None or version_table[0] is None:
        return set()
    rows = connection.execute("SELECT version_num FROM alembic_version").fetchall()
    return {str(row[0]) for row in rows}


def test_all_migrations_round_trip_through_base(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """空 DB で全 revision を upgrade・base downgrade・再 upgrade する。"""
    with disposable_postgres_cluster() as cluster:
        monkeypatch.setenv(
            "PITCHLOG_MIGRATION_DATABASE_URL", _sqlalchemy_url(cluster.admin_dsn)
        )
        config = _alembic_config()
        script = ScriptDirectory.from_config(config)
        revision_files = {path.stem for path in _VERSIONS_ROOT.rglob("[0-9]*.py")}
        revision_ids = {
            revision.revision for revision in script.walk_revisions(base="base")
        }
        heads = script.get_heads()
        assert revision_ids == revision_files
        assert len(heads) == 1

        with psycopg.connect(cluster.admin_dsn, autocommit=True) as connection:
            assert _public_application_tables(connection) == set()
            assert _applied_revisions(connection) == set()

        command.upgrade(config, "head")
        command.current(config, check_heads=True)
        command.check(config)
        with psycopg.connect(cluster.admin_dsn, autocommit=True) as connection:
            assert _applied_revisions(connection) == set(heads)

        command.downgrade(config, "base")
        with psycopg.connect(cluster.admin_dsn, autocommit=True) as connection:
            assert _public_application_tables(connection) == set()
            assert _applied_revisions(connection) == set()

        command.upgrade(config, "head")
        command.current(config, check_heads=True)
        command.check(config)
        with psycopg.connect(cluster.admin_dsn, autocommit=True) as connection:
            assert _applied_revisions(connection) == set(heads)
