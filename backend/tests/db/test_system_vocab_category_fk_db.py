"""システム固定語彙の区分付き FK と migration 往復を実 DB で検査する。"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from alembic import command
from product_authz_tenant_owned_cases import SeedRow, insert_statement
from psycopg import sql
from psycopg.types.json import Jsonb
from sqlalchemy.exc import DBAPIError

from .conftest import DisposablePostgres, ProvisionedProductCatalog
from .test_alembic_migrations import (
    _alembic_config,
    _insert_test_vocabularies,
    _sqlalchemy_url,
    _table_column_catalog,
)
from .test_product_authz_catalog import _inspect as _inspect_product_catalog
from .test_roster_status_seed_db import _insert_player_references
from .test_schema_audit import _foreign_key_catalog

pytestmark = pytest.mark.requires_db

_PARENT_REVISION = "0028_tenant_login_identity"
_REVISION = "0029_system_vocab_category_fk"
_FORCE_TABLES = frozenset(
    {"players", "games", "game_type_rule_defaults", "system_vocabularies"}
)
_OMITTED = object()


@dataclass(frozen=True, slots=True)
class _ReferenceCase:
    """1 本の区分付き FK の試験値を保持する。"""

    table: str
    key_column: str
    category_column: str
    fk_name: str
    expected_category: str
    valid_key: str
    invalid_key: str


_CASES = (
    _ReferenceCase(
        "players",
        "roster_status_key",
        "roster_status_category",
        "fk_players_roster_status",
        "roster_status",
        "active",
        "official",
    ),
    _ReferenceCase(
        "games",
        "game_type_key",
        "game_type_category",
        "fk_games_game_type",
        "game_type",
        "official",
        "active",
    ),
    _ReferenceCase(
        "game_type_rule_defaults",
        "game_type_key",
        "game_type_category",
        "fk_game_type_rule_defaults_type",
        "game_type",
        "official",
        "active",
    ),
)


@dataclass(frozen=True, slots=True)
class _Targets:
    """参照元の行が必要とする既存の参照先 ID を保持する。"""

    tenant_id: UUID
    home_team_id: UUID
    away_team_id: UUID
    rule_set_id: UUID


def _seed_targets(cursor: psycopg.Cursor[Any]) -> _Targets:
    """既存 helper で語彙・選手の参照先を作り、試合と規則の参照先を足す。"""
    tenant_id, home_team_id = _insert_player_references(cursor)
    _insert_test_vocabularies(cursor, tenant_id)
    away_team_id = uuid4()
    rule_set_id = uuid4()
    cursor.execute(
        "INSERT INTO public.team_records (tenant_id, id, kind, name) "
        "VALUES (%s, %s, 'opponent', %s)",
        (tenant_id, away_team_id, "区分 FK テスト対戦相手"),
    )
    cursor.execute(
        "INSERT INTO public.rule_sets "
        "(id, regulation_innings, called_game_conditions) "
        "VALUES (%s, 9, %s)",
        (rule_set_id, Jsonb([])),
    )
    return _Targets(tenant_id, home_team_id, away_team_id, rule_set_id)


def _insert_reference(
    cursor: psycopg.Cursor[Any],
    case: _ReferenceCase,
    targets: _Targets,
    key: str,
    *,
    category: object = _OMITTED,
) -> UUID | str:
    """指定した参照元に、定数列の省略または明示値で 1 行を投入する。"""
    values: dict[str, object]
    if case.table == "players":
        identity: UUID | str = uuid4()
        values = {
            "tenant_id": targets.tenant_id,
            "id": identity,
            "team_record_id": targets.home_team_id,
            "name": "区分 FK テスト選手",
            "roster_status_key": key,
            "roster_label_key": "roster-test-label",
        }
    elif case.table == "games":
        identity = uuid4()
        values = {
            "tenant_id": targets.tenant_id,
            "id": identity,
            "scheduled_at": datetime(2026, 10, 7, tzinfo=UTC),
            "game_type_key": key,
            "tournament_key": "autumn",
            "away_team_record_id": targets.away_team_id,
            "home_team_record_id": targets.home_team_id,
            "applied_rules": {},
        }
    else:
        assert case.table == "game_type_rule_defaults"
        identity = key
        values = {"game_type_key": key, "rule_set_id": targets.rule_set_id}
    if category is not _OMITTED:
        values[case.category_column] = category
    statement, params = insert_statement(SeedRow(case.table, values))
    cursor.execute(statement, params)
    return identity


def _row_exists(
    cursor: psycopg.Cursor[Any], case: _ReferenceCase, identity: UUID | str
) -> bool:
    """参照元の試験行が現在の接続から見えるかを返す。"""
    identity_column = (
        "game_type_key" if case.table == "game_type_rule_defaults" else "id"
    )
    cursor.execute(
        sql.SQL("SELECT 1 FROM {} WHERE {} = %s").format(
            sql.Identifier("public", case.table), sql.Identifier(identity_column)
        ),
        (identity,),
    )
    return cursor.fetchone() == (1,)


def _force_states(connection: psycopg.Connection[Any]) -> dict[str, bool]:
    """事前検査の対象 4 表の FORCE RLS 状態を実カタログから返す。"""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT relation.relname, relation.relforcerowsecurity
            FROM pg_catalog.pg_class AS relation
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = 'public'
              AND relation.relname = ANY(%s)
            """,
            (list(_FORCE_TABLES),),
        )
        states = dict(cursor.fetchall())
    assert set(states) == _FORCE_TABLES
    return states


def _assert_fk_shape(connection: psycopg.Connection[Any], *, composite: bool) -> None:
    """3 本の FK の両端列順・MATCH・定数列と UNIQUE の有無を照合する。"""
    foreign_keys = {row.name: row for row in _foreign_key_catalog(connection)}
    columns = _table_column_catalog(connection)
    for case in _CASES:
        foreign_key = foreign_keys[case.fk_name]
        assert foreign_key.table == case.table
        assert foreign_key.target_table == "system_vocabularies"
        assert foreign_key.columns == (
            (case.key_column, case.category_column) if composite else (case.key_column,)
        )
        assert foreign_key.target_columns == (
            ("key", "category") if composite else ("key",)
        )
        assert foreign_key.match == ("FULL" if composite else "SIMPLE")
        assert foreign_key.on_delete == "NO ACTION"
        assert (case.category_column in columns[case.table]) is composite
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT contype FROM pg_catalog.pg_constraint
            WHERE conrelid = 'public.system_vocabularies'::pg_catalog.regclass
              AND conname = 'uq_system_vocabularies_key_category'
            """
        )
        assert cursor.fetchone() == (("u",) if composite else None)


@pytest.mark.parametrize("case", _CASES, ids=lambda case: case.table)
def test_head_rejects_cross_category_foreign_keys(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
    monkeypatch: pytest.MonkeyPatch,
    case: _ReferenceCase,
) -> None:
    """① head で区分違いを 3 本それぞれの FK 名で拒否する。"""
    with disposable_postgres_cluster() as cluster:
        monkeypatch.setenv(
            "PITCHLOG_MIGRATION_DATABASE_URL", _sqlalchemy_url(cluster.admin_dsn)
        )
        command.upgrade(_alembic_config(), "head")
        with psycopg.connect(cluster.admin_dsn, autocommit=True) as connection:
            with connection.cursor() as cursor:
                targets = _seed_targets(cursor)
                with pytest.raises(psycopg.errors.ForeignKeyViolation) as raised:
                    _insert_reference(cursor, case, targets, case.invalid_key)
                assert raised.value.diag.constraint_name == case.fk_name


@pytest.mark.parametrize("case", _CASES, ids=lambda case: case.table)
def test_category_columns_reject_wrong_values_and_null(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
    monkeypatch: pytest.MonkeyPatch,
    case: _ReferenceCase,
) -> None:
    """② 定数列への区分違いと明示 NULL を 3 表それぞれで拒否する。"""
    with disposable_postgres_cluster() as cluster:
        monkeypatch.setenv(
            "PITCHLOG_MIGRATION_DATABASE_URL", _sqlalchemy_url(cluster.admin_dsn)
        )
        command.upgrade(_alembic_config(), "head")
        with psycopg.connect(cluster.admin_dsn, autocommit=True) as connection:
            with connection.cursor() as cursor:
                targets = _seed_targets(cursor)
                with pytest.raises(psycopg.errors.CheckViolation):
                    _insert_reference(
                        cursor, case, targets, case.valid_key, category="wrong_category"
                    )
                with pytest.raises(psycopg.errors.NotNullViolation) as raised:
                    _insert_reference(
                        cursor, case, targets, case.valid_key, category=None
                    )
                assert raised.value.diag.column_name == case.category_column


def test_matching_categories_use_column_defaults(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """③ 定数列を省いた正しい参照の投入と既定値の読み戻しを確かめる。"""
    with disposable_postgres_cluster() as cluster:
        monkeypatch.setenv(
            "PITCHLOG_MIGRATION_DATABASE_URL", _sqlalchemy_url(cluster.admin_dsn)
        )
        command.upgrade(_alembic_config(), "head")
        with psycopg.connect(cluster.admin_dsn, autocommit=True) as connection:
            with connection.cursor() as cursor:
                targets = _seed_targets(cursor)
                for case in _CASES:
                    identity = _insert_reference(cursor, case, targets, case.valid_key)
                    cursor.execute(
                        sql.SQL("SELECT {} FROM {} WHERE {} = %s").format(
                            sql.Identifier(case.category_column),
                            sql.Identifier("public", case.table),
                            sql.Identifier(
                                "game_type_key"
                                if case.table == "game_type_rule_defaults"
                                else "id"
                            ),
                        ),
                        (identity,),
                    )
                    assert cursor.fetchone() == (case.expected_category,)


@pytest.mark.parametrize("case", _CASES, ids=lambda case: case.table)
def test_preflight_rejects_force_hidden_mismatch(
    provisioned_product_catalog: ProvisionedProductCatalog,
    monkeypatch: pytest.MonkeyPatch,
    case: _ReferenceCase,
) -> None:
    """④ FORCE で所有者から隠れた区分違いを表名つきで拒否し、状態を残す。"""
    catalog = provisioned_product_catalog
    monkeypatch.setenv(
        "PITCHLOG_MIGRATION_DATABASE_URL", _sqlalchemy_url(catalog.owner_dsn)
    )
    config = _alembic_config()
    command.downgrade(config, _PARENT_REVISION)
    force_before = _force_states(catalog.observer)
    assert all(force_before.values())
    catalog.observer.rollback()
    with catalog.applicator.cursor() as cursor:
        targets = _seed_targets(cursor)
        identity = _insert_reference(cursor, case, targets, case.invalid_key)
        assert _row_exists(cursor, case, identity)
    catalog.applicator.commit()
    with psycopg.connect(catalog.owner_dsn) as owner, owner.cursor() as cursor:
        assert not _row_exists(cursor, case, identity)

    expected_message = f"0029 の事前検査に失敗: {case.table} に区分の合わない参照"
    with pytest.raises(DBAPIError) as raised:
        command.upgrade(config, _REVISION)
    assert isinstance(raised.value.orig, psycopg.errors.RaiseException)
    assert str(raised.value.orig).splitlines()[0] == expected_message

    with catalog.observer.cursor() as cursor:
        assert _row_exists(cursor, case, identity)
        cursor.execute("SELECT version_num FROM public.alembic_version")
        assert cursor.fetchone() == (_PARENT_REVISION,)
    assert _force_states(catalog.observer) == force_before
    catalog.observer.rollback()


def test_force_rls_upgrade_preserves_catalog_and_states(
    provisioned_product_catalog: ProvisionedProductCatalog,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """⑤ FORCE 下の整合行は upgrade でき、FORCE と製品認可を保つ。"""
    catalog = provisioned_product_catalog
    monkeypatch.setenv(
        "PITCHLOG_MIGRATION_DATABASE_URL", _sqlalchemy_url(catalog.owner_dsn)
    )
    config = _alembic_config()
    command.downgrade(config, _PARENT_REVISION)
    force_before = _force_states(catalog.observer)
    assert all(force_before.values())
    catalog.observer.rollback()
    with catalog.applicator.cursor() as cursor:
        targets = _seed_targets(cursor)
        identities = [
            _insert_reference(cursor, case, targets, case.valid_key) for case in _CASES
        ]
    catalog.applicator.commit()
    with psycopg.connect(catalog.owner_dsn) as owner, owner.cursor() as cursor:
        assert all(
            not _row_exists(cursor, case, identity)
            for case, identity in zip(_CASES, identities, strict=True)
        )

    command.upgrade(config, _REVISION)
    assert _force_states(catalog.observer) == force_before
    with catalog.observer.cursor() as cursor:
        assert all(
            _row_exists(cursor, case, identity)
            for case, identity in zip(_CASES, identities, strict=True)
        )
    catalog.observer.rollback()
    report = _inspect_product_catalog(catalog)
    assert report.ok, report.violations


def test_category_foreign_keys_round_trip(
    provisioned_product_catalog: ProvisionedProductCatalog,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """⑥ 複合 FULL と単列 SIMPLE の往復、列・UNIQUE・認可を確認する。"""
    catalog = provisioned_product_catalog
    monkeypatch.setenv(
        "PITCHLOG_MIGRATION_DATABASE_URL", _sqlalchemy_url(catalog.owner_dsn)
    )
    config = _alembic_config()
    _assert_fk_shape(catalog.observer, composite=True)
    catalog.observer.rollback()
    report = _inspect_product_catalog(catalog)
    assert report.ok, report.violations

    command.downgrade(config, _PARENT_REVISION)
    _assert_fk_shape(catalog.observer, composite=False)
    catalog.observer.rollback()
    report = _inspect_product_catalog(catalog)
    assert report.ok, report.violations

    command.upgrade(config, _REVISION)
    _assert_fk_shape(catalog.observer, composite=True)
    catalog.observer.rollback()
    command.current(config, check_heads=True)
    command.check(config)
    report = _inspect_product_catalog(catalog)
    assert report.ok, report.violations
