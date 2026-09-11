"""データ移行領域の models を manifest と照合する。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from sqlalchemy import BigInteger, CheckConstraint, LargeBinary, Uuid
from sqlalchemy.sql.schema import Column, DefaultClause, Table

from pitchlog.db.data_migration.models import MigrationQuarantine

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_MANIFEST_PATH = _REPOSITORY_ROOT / "contracts" / "db" / "schema-manifest.json"
_MIGRATION_PATH = (
    _REPOSITORY_ROOT
    / "backend"
    / "migrations"
    / "versions"
    / "0016_migration_quarantine.py"
)


def _manifest_table() -> dict[str, Any]:
    """隔離表の manifest 契約を返す。"""
    manifest = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    return next(
        table for table in manifest["tables"] if table["name"] == "migration_quarantine"
    )


def _column_type(column: Column[Any]) -> str:
    """SQLAlchemy の型を manifest の型名へ変換する。"""
    if isinstance(column.type, Uuid):
        return "uuid"
    if isinstance(column.type, BigInteger):
        return "bigint"
    if isinstance(column.type, LargeBinary):
        return "bytea"
    raise AssertionError(f"未対応の列型: {column.name}: {column.type}")


def _column_default(column: Column[Any]) -> str | None:
    """サーバー既定値を manifest と比較できる文字列へ変換する。"""
    if column.default is not None:
        raise AssertionError(f"Python 側だけの既定値がある: {column.name}")
    if column.server_default is None:
        return None
    if not isinstance(column.server_default, DefaultClause):
        raise AssertionError(f"未対応のサーバー既定値: {column.name}")
    return str(column.server_default.arg)


def test_migration_quarantine_matches_manifest_contract() -> None:
    """隔離表の列・制約・索引・メタデータが manifest と一致する。"""
    manifest = _manifest_table()
    table = cast(Table, MigrationQuarantine.__table__)

    actual_columns = sorted(
        (
            {
                "name": column.name,
                "type": _column_type(column),
                "nullable": column.nullable,
                "default": _column_default(column),
            }
            for column in table.columns
        ),
        key=lambda column: str(column["name"]),
    )
    assert actual_columns == sorted(
        manifest["columns"], key=lambda column: column["name"]
    )
    assert {
        str(check.sqltext)
        for check in table.constraints
        if isinstance(check, CheckConstraint)
    } == set(manifest["checks"])
    assert table.foreign_key_constraints == set()
    actual_primary_key = {
        "name": table.primary_key.name,
        "kind": "PRIMARY KEY",
        "columns": list(table.primary_key.columns.keys()),
        "predicate": None,
        "roles": sorted(table.primary_key.info["roles"]),
    }
    manifest_primary_key = manifest["unique_constraints"][0]
    assert actual_primary_key == {
        "name": manifest_primary_key["name"],
        "kind": manifest_primary_key["kind"],
        "columns": manifest_primary_key["columns"],
        "predicate": manifest_primary_key["predicate"],
        "roles": sorted(manifest_primary_key["roles"]),
    }
    assert [
        {
            "name": index.name,
            "columns": list(index.columns.keys()),
            "predicate": None,
            "purpose": index.info["purpose"],
        }
        for index in table.indexes
    ] == manifest["indexes"]
    assert {
        "deletion": MigrationQuarantine.lifecycle.deletion.value,
        "append_mode": MigrationQuarantine.lifecycle.append_mode.value,
        "migration_retirement": (
            MigrationQuarantine.lifecycle.migration_retirement.value
        ),
    } == manifest["lifecycle"]
    assert {
        "protected_columns": sorted(MigrationQuarantine.immutability.protected_columns),
        "allowed_update_columns": sorted(
            MigrationQuarantine.immutability.allowed_update_columns
        ),
    } == {key: sorted(value) for key, value in manifest["immutability"].items()}
    assert set(table.columns.keys()).isdisjoint(manifest["forbidden_columns"])


def test_quarantine_has_only_raw_payload_and_technical_identifiers() -> None:
    """隔離表が4列だけで raw 内容を意味列へ分解しないと示す。"""
    table = cast(Table, MigrationQuarantine.__table__)

    assert set(table.columns.keys()) == {
        "id",
        "import_batch_id",
        "source_read_order",
        "raw_payload",
    }
    assert [name for name in table.columns.keys() if "payload" in name] == [
        "raw_payload"
    ]
    assert isinstance(table.columns["raw_payload"].type, LargeBinary)
    assert "tenant_id" not in table.columns


def test_quarantine_migration_contains_no_dml_or_forbidden_ddl() -> None:
    """隔離 migration が内容制約や権限 DDL・DML を含まないと示す。"""
    source = _MIGRATION_PATH.read_text(encoding="utf-8").upper()

    assert "INSERT" not in source
    assert "BULK_INSERT" not in source
    assert "CREATE POLICY" not in source
    assert "CREATE ROLE" not in source
    assert "ALTER ROLE" not in source
    assert "CREATE_ALL" not in source
