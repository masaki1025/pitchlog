"""Manifest の不変列マトリクス 5 行を実 PostgreSQL と横断照合する。

この 5 表は本計画が拾う範囲であり、正本が不変性を要求している列の全数ではない。
全数性は `N3` の受入証跡(ステップ 28)で閉じる。

既存の個別 migration テストは各 revision 固有の制約と往復を検査する。本モジュールは
確定済みの DDL 期待値を再利用し、manifest の 5 行を同じ検査水準で横断照合する。
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from psycopg import sql
from psycopg.types.json import Jsonb

from .conftest import DisposablePostgres
from .test_alembic_migrations import (
    _ADMIN_OPERATION_LOG_FUNCTION_DEFINITION,
    _ADMIN_OPERATION_LOG_TRIGGER_DEFINITION,
    _ADMIN_OPERATION_LOG_TRIGGER_NAME,
    _FUNCTION_DEFINITION,
    _LEDGER_FUNCTION_DEFINITION,
    _LEDGER_TRIGGER_DEFINITION,
    _LEDGER_TRIGGER_NAME,
    _RECORDING_GENERATION_FUNCTION_DEFINITION,
    _RECORDING_GENERATION_TRIGGER_DEFINITION,
    _RECORDING_GENERATION_TRIGGER_NAME,
    _SYSTEM_VOCABULARY_FUNCTION_DEFINITION,
    _SYSTEM_VOCABULARY_TRIGGER_DEFINITION,
    _SYSTEM_VOCABULARY_TRIGGER_NAME,
    _TRIGGER_DEFINITION,
    _TRIGGER_NAME,
    _alembic_config,
    _normalize_sql,
    _sqlalchemy_url,
    _sync_trigger_catalog_contract,
)

pytestmark = pytest.mark.requires_db

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_MANIFEST_PATH = _BACKEND_ROOT.parent / "contracts" / "db" / "schema-manifest.json"
_TARGET_TABLES = (
    "recording_generations",
    "idempotency_ledger",
    "team_records",
    "admin_operation_logs",
    "system_vocabularies",
)


@dataclass(frozen=True)
class _TriggerExpectation:
    """既存個別テストから再利用するトリガの確定済み期待値。"""

    name: str
    definition: str
    function_definition: str
    conditional_columns: tuple[str, ...] = ()


_TRIGGER_EXPECTATIONS = {
    "recording_generations": _TriggerExpectation(
        _RECORDING_GENERATION_TRIGGER_NAME,
        _RECORDING_GENERATION_TRIGGER_DEFINITION,
        _RECORDING_GENERATION_FUNCTION_DEFINITION,
        ("confirmed_watermark",),
    ),
    "idempotency_ledger": _TriggerExpectation(
        _LEDGER_TRIGGER_NAME,
        _LEDGER_TRIGGER_DEFINITION,
        _LEDGER_FUNCTION_DEFINITION,
    ),
    "team_records": _TriggerExpectation(
        _TRIGGER_NAME,
        _TRIGGER_DEFINITION,
        _FUNCTION_DEFINITION,
    ),
    "admin_operation_logs": _TriggerExpectation(
        _ADMIN_OPERATION_LOG_TRIGGER_NAME,
        _ADMIN_OPERATION_LOG_TRIGGER_DEFINITION,
        _ADMIN_OPERATION_LOG_FUNCTION_DEFINITION,
    ),
    "system_vocabularies": _TriggerExpectation(
        _SYSTEM_VOCABULARY_TRIGGER_NAME,
        _SYSTEM_VOCABULARY_TRIGGER_DEFINITION,
        _SYSTEM_VOCABULARY_FUNCTION_DEFINITION,
    ),
}

_PROTECTED_UPDATE_ERRORS = {
    "recording_generations": "recording generation identity is immutable",
    "idempotency_ledger": "idempotency ledger result is immutable",
    "team_records": "team_records.kind is immutable",
    "admin_operation_logs": "admin operation logs are append-only",
    "system_vocabularies": "system vocabulary is immutable",
}


@dataclass(frozen=True)
class _MatrixRow:
    """Manifest から読み出した不変列マトリクスの 1 行。"""

    protected_columns: tuple[str, ...]
    allowed_update_columns: tuple[str, ...]
    append_only: bool


@dataclass(frozen=True)
class _BehaviorProbe:
    """不変列と許可列を実更新するための行と差分値。"""

    key: Mapping[str, object]
    protected_values: Mapping[str, object]
    allowed_values: Mapping[str, object]


def _load_matrix() -> dict[str, _MatrixRow]:
    """Manifest から対象 5 表の不変列と追記専用性だけを読み出す。"""
    manifest: dict[str, Any] = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    tables = {
        table["name"]: table
        for table in manifest["tables"]
        if table["name"] in _TARGET_TABLES
    }
    if set(tables) != set(_TARGET_TABLES):
        raise AssertionError("manifest の不変列マトリクス対象 5 表を解決できない")
    return {
        name: _MatrixRow(
            tuple(table["immutability"]["protected_columns"]),
            tuple(table["immutability"]["allowed_update_columns"]),
            table["lifecycle"]["append_mode"] == "追記専用",
        )
        for name, table in tables.items()
    }


def _trigger_pairs(
    connection: psycopg.Connection[Any],
) -> set[tuple[str, str]]:
    """対象 5 表の非内部トリガを public schema のカタログから返す。"""
    rows = connection.execute(
        """
        SELECT relation.relname, trigger_row.tgname
        FROM pg_trigger AS trigger_row
        JOIN pg_class AS relation ON relation.oid = trigger_row.tgrelid
        JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
        WHERE namespace.nspname = 'public'
          AND relation.relname = ANY(%s)
          AND NOT trigger_row.tgisinternal
        ORDER BY relation.relname, trigger_row.tgname
        """,
        (list(_TARGET_TABLES),),
    ).fetchall()
    return {(str(table), str(name)) for table, name in rows}


def _structure_violations(
    connection: psycopg.Connection[Any], matrix: Mapping[str, _MatrixRow]
) -> list[str]:
    """5 表のトリガ全文・対象・有効状態・関数全文の差分を返す。"""
    violations: list[str] = []
    expected_pairs = {
        (table, expectation.name)
        for table, expectation in _TRIGGER_EXPECTATIONS.items()
    }
    actual_pairs = _trigger_pairs(connection)
    if actual_pairs != expected_pairs:
        violations.append(
            f"対象 5 表のトリガ集合が不一致: 期待={sorted(expected_pairs)!r}, "
            f"実際={sorted(actual_pairs)!r}"
        )

    for table in _TARGET_TABLES:
        expectation = _TRIGGER_EXPECTATIONS[table]
        if (table, expectation.name) not in actual_pairs:
            continue
        trigger = _sync_trigger_catalog_contract(connection, expectation.name)
        if _normalize_sql(trigger[0]) != _normalize_sql(expectation.definition):
            violations.append(f"{table}: pg_get_triggerdef 全文が不一致")
        if trigger[1] != table:
            violations.append(f"{table}: トリガの対象表が {trigger[1]} になっている")
        expected_columns = (
            []
            if matrix[table].append_only
            else [
                *matrix[table].protected_columns,
                *expectation.conditional_columns,
            ]
        )
        if trigger[2] != expected_columns:
            violations.append(
                f"{table}: 対象列が manifest と不一致: "
                f"期待={expected_columns!r}, 実際={trigger[2]!r}"
            )
        if trigger[3] != "O":
            violations.append(f"{table}: トリガが有効ではない: tgenabled={trigger[3]}")
        if _normalize_sql(trigger[4]) != _normalize_sql(
            expectation.function_definition
        ):
            violations.append(f"{table}: pg_get_functiondef 全文が不一致")
    return violations


def _seed_behavior_rows(
    connection: psycopg.Connection[Any],
) -> dict[str, _BehaviorProbe]:
    """5 表の更新挙動を独立に観測できる参照行を作る。"""
    tenant_id = uuid4()
    self_team_id = uuid4()
    opponent_team_id = uuid4()
    game_id = uuid4()
    ledger_d5 = uuid4()
    admin_log_id = uuid4()
    connection.execute(
        "INSERT INTO tenants (id, name) VALUES (%s, %s)",
        (tenant_id, "不変列マトリクステナント"),
    )
    with connection.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO system_vocabularies (key, category, display_name)
            VALUES (%s, %s, %s)
            """,
            [
                ("official", "game_type", "公式戦"),
                ("immutability-probe", "roster_status", "固定語彙"),
            ],
        )
    connection.execute(
        """
        INSERT INTO tenant_vocabularies (
            tenant_id, key, category, display_name
        ) VALUES (%s, 'autumn', 'tournament', '秋季大会')
        """,
        (tenant_id,),
    )
    with connection.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO team_records (tenant_id, id, kind, name)
            VALUES (%s, %s, %s, %s)
            """,
            [
                (tenant_id, self_team_id, "self", "自チーム"),
                (tenant_id, opponent_team_id, "opponent", "対戦相手"),
            ],
        )
    connection.execute(
        """
        INSERT INTO games (
            tenant_id,
            id,
            scheduled_at,
            game_type_key,
            tournament_key,
            away_team_record_id,
            home_team_record_id,
            applied_rules
        ) VALUES (%s, %s, %s, 'official', 'autumn', %s, %s, %s)
        """,
        (
            tenant_id,
            game_id,
            datetime(2026, 9, 11, 10, tzinfo=UTC),
            opponent_team_id,
            self_team_id,
            Jsonb({}),
        ),
    )
    connection.execute(
        """
        INSERT INTO recording_generations (
            tenant_id,
            game_id,
            generation,
            kind,
            issuance_order,
            holder_device,
            confirmed_watermark
        ) VALUES (%s, %s, 1, 'normal', 1, 'device-a', 5)
        """,
        (tenant_id, game_id),
    )
    connection.execute(
        """
        INSERT INTO idempotency_ledger (
            tenant_id, d5, kind, source_fingerprint, result
        ) VALUES (%s, %s, 'accepted', 'first-source', %s)
        """,
        (tenant_id, ledger_d5, Jsonb({"accepted": True})),
    )
    connection.execute(
        """
        INSERT INTO admin_operation_logs (id, operation_kind, target)
        VALUES (%s, 'matrix_probe', %s)
        """,
        (admin_log_id, Jsonb({"kind": "matrix"})),
    )

    return {
        "recording_generations": _BehaviorProbe(
            {"tenant_id": tenant_id, "game_id": game_id, "generation": 1},
            {
                "generation": 2,
                "kind": "migration",
                "issuance_order": 2,
                "holder_device": "device-b",
                "granted_at": datetime(2026, 9, 12, tzinfo=UTC),
            },
            {
                "confirmed_watermark": 6,
                "applied_prefix": 1,
                "revoked_at": datetime(2026, 9, 13, tzinfo=UTC),
                "retired_at": datetime(2026, 9, 14, tzinfo=UTC),
            },
        ),
        "idempotency_ledger": _BehaviorProbe(
            {"tenant_id": tenant_id, "d5": ledger_d5},
            {
                "kind": "rejected",
                "source_fingerprint": "changed-source",
                "result": Jsonb({"changed": True}),
                "reason": "changed-reason",
            },
            {"retired_at": datetime(2026, 9, 14, tzinfo=UTC)},
        ),
        "team_records": _BehaviorProbe(
            {"tenant_id": tenant_id, "id": opponent_team_id},
            {"kind": "self"},
            {
                "name": "名称変更後",
                "hidden_at": datetime(2026, 9, 14, tzinfo=UTC),
            },
        ),
        "admin_operation_logs": _BehaviorProbe(
            {"id": admin_log_id},
            {
                "id": uuid4(),
                "occurred_at": datetime(2026, 9, 12, tzinfo=UTC),
                "operation_kind": "changed",
                "target": Jsonb({"changed": True}),
                "tenant_id": tenant_id,
                "group_id": uuid4(),
            },
            {},
        ),
        "system_vocabularies": _BehaviorProbe(
            {"key": "immutability-probe"},
            {
                "key": "changed-key",
                "category": "game_type",
                "display_name": "変更後",
                "disabled": True,
            },
            {},
        ),
    }


def _update_column(
    connection: psycopg.Connection[Any],
    table: str,
    key: Mapping[str, object],
    column: str,
    value: object,
) -> tuple[Any, ...] | None:
    """識別子を安全に構成して対象 1 列を更新する。"""
    where = sql.SQL(" AND ").join(
        sql.SQL("{} = %s").format(sql.Identifier(key_column)) for key_column in key
    )
    statement = sql.SQL("UPDATE {} SET {} = %s WHERE {} RETURNING {}").format(
        sql.Identifier(table),
        sql.Identifier(column),
        where,
        sql.Identifier(column),
    )
    with connection.cursor() as cursor:
        cursor.execute(statement, (value, *key.values()))
        return cursor.fetchone()


def _assert_update_behavior(
    connection: psycopg.Connection[Any],
    matrix: Mapping[str, _MatrixRow],
    probes: Mapping[str, _BehaviorProbe],
) -> None:
    """Manifest の全保護列を拒否し全許可列を通すことを横断検査する。"""
    for table in _TARGET_TABLES:
        row = matrix[table]
        probe = probes[table]
        assert set(probe.protected_values) == set(row.protected_columns)
        assert set(probe.allowed_values) == set(row.allowed_update_columns)
        for column, value in probe.protected_values.items():
            with pytest.raises(
                psycopg.errors.CheckViolation,
                match=re.escape(_PROTECTED_UPDATE_ERRORS[table]),
            ):
                _update_column(connection, table, probe.key, column, value)

    generation = probes["recording_generations"]
    with pytest.raises(
        psycopg.errors.CheckViolation,
        match="recording generation D3 cannot move backward",
    ):
        _update_column(
            connection,
            "recording_generations",
            generation.key,
            "confirmed_watermark",
            4,
        )
    assert _update_column(
        connection,
        "recording_generations",
        generation.key,
        "confirmed_watermark",
        5,
    ) == (5,)
    assert _update_column(
        connection,
        "recording_generations",
        generation.key,
        "confirmed_watermark",
        6,
    ) == (6,)

    for table in _TARGET_TABLES:
        probe = probes[table]
        for column, value in probe.allowed_values.items():
            if table == "recording_generations" and column == "confirmed_watermark":
                continue
            assert (
                _update_column(connection, table, probe.key, column, value) is not None
            )


def _assert_append_and_mutable_delete_behavior(
    connection: psycopg.Connection[Any], probes: Mapping[str, _BehaviorProbe]
) -> None:
    """管理者ログだけを追記専用とし、固定語彙の DELETE は通す。"""
    inserted_id = uuid4()
    row = connection.execute(
        """
        INSERT INTO admin_operation_logs (id, operation_kind, target)
        VALUES (%s, 'second_matrix_probe', %s)
        RETURNING id
        """,
        (inserted_id, Jsonb({"kind": "matrix"})),
    ).fetchone()
    assert row == (inserted_id,)
    with pytest.raises(
        psycopg.errors.CheckViolation,
        match=re.escape(_PROTECTED_UPDATE_ERRORS["admin_operation_logs"]),
    ):
        connection.execute(
            "DELETE FROM admin_operation_logs WHERE id = %s",
            (probes["admin_operation_logs"].key["id"],),
        )

    deleted = connection.execute(
        """
        DELETE FROM system_vocabularies
        WHERE key = 'immutability-probe'
        RETURNING key
        """
    ).fetchone()
    assert deleted == ("immutability-probe",)


def _function_signature(definition: str) -> str:
    """既存の関数全文から downgrade 後の解決確認用署名を得る。"""
    match = re.search(
        r"CREATE OR REPLACE FUNCTION public\.([a-z0-9_]+)\(\)", definition
    )
    if match is None:
        raise AssertionError("トリガ関数の署名を期待値から解決できない")
    return f"public.{match.group(1)}()"


def _downgraded_asset_violations(
    connection: psycopg.Connection[Any],
) -> list[str]:
    """Downgrade 後に 5 トリガと関数が残っていれば違反を返す。"""
    violations = [
        f"downgrade 後もトリガが残る: {table}.{name}"
        for table, name in sorted(_trigger_pairs(connection))
    ]
    signatures = [
        _function_signature(expectation.function_definition)
        for expectation in _TRIGGER_EXPECTATIONS.values()
    ]
    rows = connection.execute(
        """
        SELECT signature, to_regprocedure(signature)
        FROM unnest(%s::text[]) AS signature
        ORDER BY signature
        """,
        (signatures,),
    ).fetchall()
    violations.extend(
        f"downgrade 後も関数が残る: {signature}"
        for signature, procedure in rows
        if procedure is not None
    )
    return violations


def test_manifest_immutability_matrix_matches_database_guards(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """5 表の構造・全列挙動・追記専用性・downgrade を一度に照合する。"""
    matrix = _load_matrix()
    assert set(_TRIGGER_EXPECTATIONS) == set(matrix) == set(_TARGET_TABLES)
    assert set(_PROTECTED_UPDATE_ERRORS) == set(matrix)
    assert {table for table, row in matrix.items() if row.append_only} == {
        "admin_operation_logs"
    }

    with disposable_postgres_cluster() as cluster:
        monkeypatch.setenv(
            "PITCHLOG_MIGRATION_DATABASE_URL", _sqlalchemy_url(cluster.admin_dsn)
        )
        config = _alembic_config()
        command.upgrade(config, "head")
        with psycopg.connect(cluster.admin_dsn, autocommit=True) as connection:
            assert _structure_violations(connection, matrix) == []
            probes = _seed_behavior_rows(connection)
            _assert_update_behavior(connection, matrix, probes)
            _assert_append_and_mutable_delete_behavior(connection, probes)

        command.downgrade(config, "0001_initialize_schema")
        with psycopg.connect(cluster.admin_dsn, autocommit=True) as connection:
            assert _downgraded_asset_violations(connection) == []
