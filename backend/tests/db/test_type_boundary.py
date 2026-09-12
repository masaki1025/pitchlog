"""型境界の隔離原本往復と正規スキーマ構造を実 PostgreSQL で検査する。"""

from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from psycopg.types.json import Jsonb
from type_boundary_contract import (
    ColumnContract,
    four_shape_violations,
    legacy_storage_types,
    play_row_destination_columns,
    play_row_type_violations,
    raw_payload_round_trip_violations,
    regular_schema_violations,
)

from pitchlog.db.game_state.models import PlayRow

from .conftest import DisposablePostgres
from .test_alembic_migrations import _alembic_config, _sqlalchemy_url

pytestmark = pytest.mark.requires_db

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_DATA_MODEL_PATH = _REPOSITORY_ROOT / "docs" / "design" / "data-model.md"
_DATA_LAYER_PATH = _REPOSITORY_ROOT / "docs" / "legacy" / "research" / "data-layer.md"


def _raw_payload_cases() -> dict[int, bytes]:
    """4 形態と損失しやすい境界値を含む 88 列 raw 行を返す。"""
    four_shapes: list[object] = [0, "0", "", None]
    four_shapes.extend(f"field-{index}" for index in range(4, 88))
    boundary_values: list[object] = [
        "123456789012345678901234567890",
        "007",
        " 1 ",
        "１２３",
    ]
    boundary_values.extend(f"field-{index}" for index in range(4, 88))
    return {
        1: json.dumps(four_shapes, ensure_ascii=False, separators=(",", ":")).encode(),
        2: json.dumps(
            boundary_values, ensure_ascii=False, separators=(",", ":")
        ).encode(),
        3: b"\x1f".join(
            [b"\xff\xfe\x80"] + [f"field-{index}".encode() for index in range(1, 88)]
        ),
    }


def test_quarantine_raw_payload_round_trips_all_boundary_shapes(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A1〜A3 の 4 形態・境界値を bytea でバイト同値往復する。"""
    expected = _raw_payload_cases()
    assert len(json.loads(expected[1].decode("utf-8"))) == 88
    assert len(json.loads(expected[2].decode("utf-8"))) == 88
    assert len(expected[3].split(b"\x1f")) == 88
    with disposable_postgres_cluster() as cluster:
        monkeypatch.setenv(
            "PITCHLOG_MIGRATION_DATABASE_URL", _sqlalchemy_url(cluster.admin_dsn)
        )
        command.upgrade(_alembic_config(), "head")
        with psycopg.connect(cluster.admin_dsn, autocommit=True) as connection:
            import_batch_id = uuid4()
            connection.execute(
                """
                INSERT INTO migration_runs (
                    id, source_counts, generated_copy_counts, validation_results
                ) VALUES (%s, %s, %s, %s)
                """,
                (import_batch_id, Jsonb({}), Jsonb({}), Jsonb({})),
            )
            for order, payload in expected.items():
                connection.execute(
                    """
                    INSERT INTO migration_quarantine (
                        id, import_batch_id, source_read_order, raw_payload
                    ) VALUES (%s, %s, %s, %s)
                    """,
                    (uuid4(), import_batch_id, order, payload),
                )
            rows = connection.execute(
                """
                SELECT source_read_order, raw_payload
                FROM migration_quarantine
                WHERE import_batch_id = %s
                ORDER BY source_read_order
                """,
                (import_batch_id,),
            ).fetchall()

    actual = {int(order): bytes(payload) for order, payload in rows}
    assert raw_payload_round_trip_violations(expected, actual) == []
    decoded_shapes = json.loads(actual[1].decode("utf-8"))[:4]
    assert four_shape_violations(decoded_shapes) == []
    assert [index for index, value in enumerate(decoded_shapes) if value is None] == [3]
    with pytest.raises(UnicodeDecodeError):
        actual[3].decode("utf-8")


def _type_boundary_catalog(
    connection: psycopg.Connection[Any],
) -> dict[tuple[str, str], ColumnContract]:
    """C の対象 2 表の全列を PostgreSQL カタログから返す。"""
    rows = connection.execute(
        """
        SELECT
            relation.relname,
            attribute.attname,
            format_type(attribute.atttypid, attribute.atttypmod),
            NOT attribute.attnotnull,
            pg_get_expr(default_row.adbin, default_row.adrelid, true)
        FROM pg_attribute AS attribute
        JOIN pg_class AS relation ON relation.oid = attribute.attrelid
        JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
        LEFT JOIN pg_attrdef AS default_row
          ON default_row.adrelid = attribute.attrelid
         AND default_row.adnum = attribute.attnum
        WHERE namespace.nspname = 'public'
          AND relation.relname = ANY(%s)
          AND attribute.attnum > 0
          AND NOT attribute.attisdropped
        ORDER BY relation.relname, attribute.attnum
        """,
        (["play_rows", "migrated_final_lineups"],),
    ).fetchall()
    return {
        (str(table), str(name)): ColumnContract(
            str(data_type), bool(nullable), None if default is None else str(default)
        )
        for table, name, data_type, nullable, default in rows
    }


def test_regular_schema_original_and_resolved_columns_follow_legacy_types(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """プレイ行の全旧列型と C1〜C4 を実 PostgreSQL カタログで検査する。"""
    with disposable_postgres_cluster() as cluster:
        monkeypatch.setenv(
            "PITCHLOG_MIGRATION_DATABASE_URL", _sqlalchemy_url(cluster.admin_dsn)
        )
        command.upgrade(_alembic_config(), "head")
        with psycopg.connect(cluster.admin_dsn, autocommit=True) as connection:
            columns = _type_boundary_catalog(connection)

    source_types = legacy_storage_types(_DATA_LAYER_PATH.read_text(encoding="utf-8"))
    source_columns = {
        source_number: column.name
        for column in PlayRow.__table__.columns
        for source_number in column.info.get("legacy_source_columns", ())
    }
    assert (
        play_row_type_violations(
            play_row_destination_columns(_DATA_MODEL_PATH.read_text(encoding="utf-8")),
            source_columns,
            columns,
            source_types,
        )
        == []
    )
    assert regular_schema_violations(columns, source_types) == []
