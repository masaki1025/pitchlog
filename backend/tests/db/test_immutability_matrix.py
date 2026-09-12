"""選定した 7 表の不変列を実 UPDATE・DELETE で挙動検査する。

構造の全表突合は test_immutability_enforcement.py が担う。本モジュールの行 fixture は
既存 5 表に operation_events と players を加えた 7 表だけを対象とする。実更新挙動の
全表化は受け取り先 C の宿題であり、ここでは暗黙に全表被覆を主張しない。
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
    _alembic_config,
    _sqlalchemy_url,
)

pytestmark = pytest.mark.requires_db

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_MANIFEST_PATH = _BACKEND_ROOT.parent / "contracts" / "db" / "schema-manifest.json"
_BEHAVIOR_TABLES = (
    "recording_generations",
    "idempotency_ledger",
    "team_records",
    "admin_operation_logs",
    "system_vocabularies",
    "operation_events",
    "players",
)

_PROTECTED_UPDATE_ERRORS = {
    "recording_generations": "recording generation identity is immutable",
    "idempotency_ledger": "idempotency ledger result is immutable",
    "team_records": "team_records.kind is immutable",
    "admin_operation_logs": "admin operation logs are append-only",
    "system_vocabularies": "system vocabulary is immutable",
    "operation_events": "operation_events confirmed content is immutable",
    "players": "players.id is immutable",
}


@dataclass(frozen=True)
class _MatrixRow:
    """Manifest から読み出した不変列マトリクスの 1 行。"""

    protected_columns: tuple[str, ...]
    allowed_update_columns: tuple[str, ...]
    conditional_update_columns: tuple[str, ...]
    append_only: bool


@dataclass(frozen=True)
class _BehaviorProbe:
    """不変列と許可列を実更新するための行と差分値。"""

    key: Mapping[str, object]
    protected_values: Mapping[str, object]
    allowed_values: Mapping[str, object]


def _load_behavior_matrix() -> dict[str, _MatrixRow]:
    """Manifest から行 fixture を持つ 7 表の不変列宣言を読み出す。

    実更新挙動は既存 5 表と operation_events・players の 7 表を対象とする。
    全表の実更新挙動は受け取り先 C で追加する。
    """
    manifest: dict[str, Any] = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    tables = {
        table["name"]: table
        for table in manifest["tables"]
        if table["name"] in _BEHAVIOR_TABLES
    }
    if set(tables) != set(_BEHAVIOR_TABLES):
        raise AssertionError("manifest の実更新挙動対象 7 表を解決できない")
    return {
        name: _MatrixRow(
            tuple(table["immutability"]["protected_columns"]),
            tuple(table["immutability"]["allowed_update_columns"]),
            tuple(table["immutability"]["conditional_update_columns"]),
            table["lifecycle"]["append_mode"] == "追記専用",
        )
        for name, table in tables.items()
    }


def _seed_behavior_rows(
    connection: psycopg.Connection[Any],
) -> dict[str, _BehaviorProbe]:
    """7 表の更新挙動を独立に観測できる参照行を作る。"""
    tenant_id = uuid4()
    self_team_id = uuid4()
    opponent_team_id = uuid4()
    player_id = uuid4()
    game_id = uuid4()
    ledger_d5 = uuid4()
    operation_d5 = uuid4()
    operation_id = uuid4()
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
                ("roster-active", "roster_status", "在籍"),
                ("roster-inactive", "roster_status", "退団"),
            ],
        )
    with connection.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO tenant_vocabularies (
                tenant_id, key, category, display_name
            ) VALUES (%s, %s, %s, %s)
            """,
            [
                (tenant_id, "autumn", "tournament", "秋季大会"),
                (tenant_id, "roster-primary", "roster_label", "一軍"),
                (tenant_id, "roster-reserve", "roster_label", "控え"),
            ],
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
        INSERT INTO players (
            tenant_id,
            id,
            team_record_id,
            name,
            throws,
            bats,
            uniform_number,
            roster_status_key,
            roster_label_key
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            tenant_id,
            player_id,
            self_team_id,
            "選手名",
            "right",
            "right",
            "1",
            "roster-active",
            "roster-primary",
        ),
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
        INSERT INTO event_slots (tenant_id, game_id, generation, d1)
        VALUES (%s, %s, 1, 1)
        """,
        (tenant_id, game_id),
    )
    with connection.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO idempotency_ledger (
                tenant_id, d5, kind, source_fingerprint, result
            ) VALUES (%s, %s, 'accepted', %s, %s)
            """,
            [
                (
                    tenant_id,
                    ledger_d5,
                    "first-source",
                    Jsonb({"accepted": True}),
                ),
                (tenant_id, operation_d5, "operation-source", Jsonb({})),
            ],
        )
    connection.execute(
        """
        INSERT INTO operation_events (
            tenant_id,
            id,
            game_id,
            generation,
            d1,
            d5,
            event_kind,
            payload,
            state_diff
        ) VALUES (%s, %s, %s, 1, 1, %s, 'play_input', %s, %s)
        """,
        (
            tenant_id,
            operation_id,
            game_id,
            operation_d5,
            Jsonb({"result": "strike"}),
            Jsonb({"outs": 0}),
        ),
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
        "operation_events": _BehaviorProbe(
            {"tenant_id": tenant_id, "id": operation_id},
            {
                "tenant_id": uuid4(),
                "id": uuid4(),
                "game_id": uuid4(),
                "generation": 2,
                "d1": 2,
                "d5": uuid4(),
                "event_kind": "undo",
                "payload": Jsonb({"changed": True}),
                "state_diff": Jsonb({"outs": 1}),
            },
            {
                "d2": 1,
                "replaced_at": datetime(2026, 9, 15, tzinfo=UTC),
                "retired_at": datetime(2026, 9, 16, tzinfo=UTC),
            },
        ),
        "players": _BehaviorProbe(
            {"tenant_id": tenant_id, "id": player_id},
            {"id": uuid4()},
            {
                "name": "選手名変更後",
                "throws": "left",
                "bats": "left",
                "uniform_number": "42",
                "roster_status_key": "roster-inactive",
                "roster_label_key": "roster-reserve",
                "hidden_at": datetime(2026, 9, 17, tzinfo=UTC),
            },
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
    """行 fixture を持つ 7 表で全保護列を拒否し全許可列を通す。"""
    for table in _BEHAVIOR_TABLES:
        row = matrix[table]
        probe = probes[table]
        assert set(probe.protected_values) == set(row.protected_columns)
        assert set(probe.allowed_values) == set(row.allowed_update_columns) | set(
            row.conditional_update_columns
        )
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

    for table in _BEHAVIOR_TABLES:
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


def test_selected_immutability_update_behavior(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """受け取り先 C までの明示的な 7 表で更新・削除挙動を検査する。"""
    matrix = _load_behavior_matrix()
    assert set(matrix) == set(_BEHAVIOR_TABLES)
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
            probes = _seed_behavior_rows(connection)
            assert set(probes) == set(_BEHAVIOR_TABLES)
            _assert_update_behavior(connection, matrix, probes)
            _assert_append_and_mutable_delete_behavior(connection, probes)
