"""導出した製品ランタイム契約を実 PostgreSQL カタログと照合する。"""

from __future__ import annotations

import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, LiteralString, cast

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

from pitchlog.authz.runtime_contract_state import (
    RUNTIME_CONTRACT_ASSET,
    derive_runtime_contract_fields,
    read_json_object,
)
from pitchlog.db import engine

from .conftest import ProvisionedProductCatalog

pytestmark = pytest.mark.requires_db

_ROOT = Path(__file__).resolve().parents[3]


class _RecordingCursor:
    """実カーソルを通した所有者照会の返却件数を記録する。"""

    def __init__(self, inner: psycopg.Cursor[Any], counts: list[int]) -> None:
        """委譲先と記録先を設定する。"""
        self.inner = inner
        self.counts = counts
        self.owner_query = False

    def execute(self, query: LiteralString, params: Any = None) -> None:
        """SQL をそのまま委譲し、所有者照会かだけを記録する。"""
        self.owner_query = "SELECT owner.rolname" in query
        self.inner.execute(query, params)

    def fetchone(self) -> Any:
        """1 行取得を実カーソルへ委譲する。"""
        return self.inner.fetchone()

    def fetchall(self) -> list[Any]:
        """全行取得を実カーソルへ委譲し、所有者照会の件数を記録する。"""
        rows = self.inner.fetchall()
        if self.owner_query:
            self.counts.append(len(rows))
        return rows


class _RecordingConnection:
    """真正性検査の接続を包み、SQL は元の DB 接続で実行する。"""

    def __init__(self, inner: psycopg.Connection[Any], counts: list[int]) -> None:
        """委譲先と記録先を設定する。"""
        self.inner = inner
        self.counts = counts

    @contextmanager
    def cursor(self) -> Iterator[_RecordingCursor]:
        """実カーソルの寿命を保持したまま計測用ラッパーを供給する。"""
        with self.inner.cursor() as cursor:
            yield _RecordingCursor(cursor, self.counts)

    def rollback(self) -> None:
        """実接続の検査トランザクションを終了する。"""
        self.inner.rollback()

    @property
    def info(self) -> Any:
        """実接続のトランザクション状態を返す。"""
        return self.inner.info


def test_derived_product_runtime_contract_exists_and_authenticates(
    provisioned_product_catalog: ProvisionedProductCatalog,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """導出した全対象が実在し、所有者照会とアプリ接続が成立する。"""
    catalog = provisioned_product_catalog
    runtime_asset = read_json_object(_ROOT / RUNTIME_CONTRACT_ASSET)
    derived = derive_runtime_contract_fields(catalog.asset, runtime_asset)
    objects = derived["protected_objects"]
    schemas = objects["schemas"]
    tables = [tuple(row) for row in objects["tables"]]
    functions = [tuple(row) for row in objects["functions"]]
    declared_functions = catalog.asset["functions"]
    assert isinstance(declared_functions, list)
    assert (len(schemas), len(tables), len(functions)) == (
        2,
        45,
        len(declared_functions),
    )
    assert (
        "authz_private",
        "tenant_has_effective_membership",
        "uuid, boolean",
    ) in functions

    with catalog.observer.cursor() as cursor:
        cursor.execute(
            "SELECT nspname FROM pg_catalog.pg_namespace WHERE nspname = ANY(%s)",
            (schemas,),
        )
        assert {str(row[0]) for row in cursor.fetchall()} == set(schemas)
        cursor.execute(
            """
            SELECT namespace.nspname, relation.relname
            FROM pg_catalog.pg_class AS relation
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = relation.relnamespace
            WHERE relation.relkind IN ('r', 'p', 'v', 'm', 'f')
              AND (namespace.nspname, relation.relname) IN (
                  SELECT * FROM unnest(%s::text[], %s::text[])
              )
            """,
            ([schema for schema, _ in tables], [table for _, table in tables]),
        )
        assert {(str(row[0]), str(row[1])) for row in cursor.fetchall()} == set(tables)
        cursor.execute(
            """
            SELECT namespace.nspname, routine.proname,
                   pg_catalog.oidvectortypes(routine.proargtypes)
            FROM pg_catalog.pg_proc AS routine
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = routine.pronamespace
            WHERE (
                namespace.nspname,
                routine.proname,
                pg_catalog.oidvectortypes(routine.proargtypes)
            ) IN (
                SELECT * FROM unnest(%s::text[], %s::text[], %s::text[])
            )
            """,
            (
                [schema for schema, _, _ in functions],
                [name for _, name, _ in functions],
                [arguments for _, _, arguments in functions],
            ),
        )
        assert {
            (str(row[0]), str(row[1]), str(row[2])) for row in cursor.fetchall()
        } == set(functions)
    catalog.observer.rollback()

    monkeypatch.setattr(engine, "APPLICATION_ROLE_NAME", "pitchlog_app")
    monkeypatch.setattr(
        engine,
        "APPLICATION_ROLE_ATTRIBUTES",
        engine.ApplicationRoleAttributes(**derived["application_role"]["attributes"]),
    )
    monkeypatch.setattr(engine, "PROTECTED_SCHEMAS", tuple(schemas))
    monkeypatch.setattr(engine, "PROTECTED_TABLES", tuple(tables))
    monkeypatch.setattr(engine, "PROTECTED_FUNCTIONS", tuple(functions))

    observation: list[engine._ConnectionObservation] = []
    original_observation = engine._ConnectionObservation

    def record_observation(**values: Any) -> engine._ConnectionObservation:
        """真正性検査が実際に観測した危険ロール集合を保持する。"""
        result = original_observation(**values)
        observation.append(result)
        return result

    monkeypatch.setattr(engine, "_ConnectionObservation", record_observation)
    password = secrets.token_urlsafe(24)
    with catalog.applicator.cursor() as cursor:
        cursor.execute(
            sql.SQL("ALTER ROLE pitchlog_app PASSWORD {}").format(sql.Literal(password))
        )
    catalog.applicator.commit()
    dsn = make_conninfo(catalog.owner_dsn, user="pitchlog_app", password=password)
    owner_counts: list[int] = []
    with psycopg.connect(dsn) as connection:
        engine._verify_application_role_connection(
            cast(
                psycopg.Connection[Any], _RecordingConnection(connection, owner_counts)
            )
        )
    # 名前付き引数の補助関数も含め、宣言された保護関数すべての所有者が返る。
    assert owner_counts == [len(schemas), len(tables), len(functions)]
    assert len(observation) == 1
    assert "pitchlog_shared_fn_owner" in observation[0].dangerous_roles
