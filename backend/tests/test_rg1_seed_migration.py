"""RG1初期行のmigration候補を隔離PostgreSQLで確認する。"""

from __future__ import annotations

import importlib.util
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from typing import TYPE_CHECKING

import psycopg
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from psycopg.conninfo import conninfo_to_dict
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.exc import ProgrammingError

if TYPE_CHECKING:
    from db_fixtures import DisposablePostgres

pytest_plugins = ("db_fixtures",)
_MIGRATION_PATH = (
    Path(__file__).resolve().parents[1] / "migrations/versions/0032_rg1_restore_gate.py"
)


def _apply_rg1_migration(admin_dsn: str) -> None:
    """製品候補のupgradeをAlembic操作として実行する。"""
    parts = conninfo_to_dict(admin_dsn)
    username = parts.get("user")
    password = parts.get("password")
    host = parts.get("host")
    port = parts.get("port")
    database = parts.get("dbname")
    assert isinstance(username, str)
    assert isinstance(password, str)
    assert isinstance(host, str)
    assert isinstance(port, (str, int))
    assert isinstance(database, str)
    url = URL.create(
        "postgresql+psycopg",
        username=username,
        password=password,
        host=host,
        port=int(port),
        database=database,
    )
    module_spec = importlib.util.spec_from_file_location(
        "rg1_seed_migration_candidate", _MIGRATION_PATH
    )
    assert module_spec is not None and module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            setattr(module, "op", Operations(MigrationContext.configure(connection)))
            module.upgrade()
    finally:
        engine.dispose()


def test_rg1_seed_creates_only_closed_singleton(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
) -> None:
    """実upgradeの結果はclosedの1行に限り、別IDと不明状態を拒む。"""
    with disposable_postgres_cluster() as cluster:
        _apply_rg1_migration(cluster.admin_dsn)
        with psycopg.connect(cluster.admin_dsn, autocommit=True) as admin:
            rows = admin.execute(
                "SELECT singleton_id, state FROM public.rg1_restore_gate"
            ).fetchall()
            assert rows == [(1, "closed")]
            assert admin.execute(
                "SELECT data_type, column_default FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'rg1_restore_gate' "
                "AND column_name = 'singleton_id'"
            ).fetchone() == ("smallint", None)
            with pytest.raises(psycopg.errors.CheckViolation):
                admin.execute(
                    "INSERT INTO public.rg1_restore_gate VALUES (2, 'closed')"
                )
            with pytest.raises(psycopg.errors.CheckViolation):
                admin.execute(
                    "INSERT INTO public.rg1_restore_gate VALUES (1, 'unknown')"
                )
            with pytest.raises(psycopg.errors.UniqueViolation):
                admin.execute(
                    "INSERT INTO public.rg1_restore_gate VALUES (1, 'closed')"
                )
            assert admin.execute(
                "SELECT singleton_id, state FROM public.rg1_restore_gate"
            ).fetchall() == [(1, "closed")]


def test_rg1_seed_does_not_overwrite_existing_table(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
) -> None:
    """既存表があればupgradeは失敗し、その行を変更しない。"""
    with disposable_postgres_cluster() as cluster:
        _apply_rg1_migration(cluster.admin_dsn)
        with psycopg.connect(cluster.admin_dsn, autocommit=True) as admin:
            admin.execute(
                "UPDATE public.rg1_restore_gate SET state = 'open' "
                "WHERE singleton_id = 1"
            )
        with pytest.raises(ProgrammingError) as error:
            _apply_rg1_migration(cluster.admin_dsn)
        assert isinstance(error.value.orig, psycopg.errors.DuplicateTable)
        with psycopg.connect(cluster.admin_dsn, autocommit=True) as admin:
            assert admin.execute(
                "SELECT singleton_id, state FROM public.rg1_restore_gate"
            ).fetchall() == [(1, "open")]
