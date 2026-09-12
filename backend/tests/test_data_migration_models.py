"""データ移行領域の models を manifest と照合する。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    LargeBinary,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import operators
from sqlalchemy.sql.elements import UnaryExpression
from sqlalchemy.sql.schema import Column, DefaultClause, Index, Table

from pitchlog.db.data_migration.models import (
    MigratedFinalLineup,
    MigrationQuarantine,
    MigrationResolutionReport,
    MigrationRun,
    MigrationWarningReport,
)
from pitchlog.db.game_state.models import PlayRow
from pitchlog.db.recording_rights.models import RecordingGeneration

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_MANIFEST_PATH = _REPOSITORY_ROOT / "contracts" / "db" / "schema-manifest.json"
_MIGRATION_PATH = (
    _REPOSITORY_ROOT
    / "backend"
    / "migrations"
    / "versions"
    / "0016_migration_quarantine.py"
)
_MIGRATED_FINAL_LINEUP_MIGRATION_PATH = (
    _REPOSITORY_ROOT
    / "backend"
    / "migrations"
    / "versions"
    / "0017_migrated_final_lineups.py"
)
_MIGRATION_REPORTS_MIGRATION_PATH = (
    _REPOSITORY_ROOT
    / "backend"
    / "migrations"
    / "versions"
    / "0018_migration_reports.py"
)


def _manifest_table(table_name: str) -> dict[str, Any]:
    """指定した表の manifest 契約を返す。"""
    manifest = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    return next(table for table in manifest["tables"] if table["name"] == table_name)


def _column_type(column: Column[Any]) -> str:
    """SQLAlchemy の型を manifest の型名へ変換する。"""
    if isinstance(column.type, Uuid):
        return "uuid"
    if isinstance(column.type, BigInteger):
        return "bigint"
    if isinstance(column.type, Boolean):
        return "boolean"
    if isinstance(column.type, JSONB):
        return "jsonb"
    if isinstance(column.type, LargeBinary):
        return "bytea"
    if isinstance(column.type, Text):
        return "text"
    if isinstance(column.type, DateTime) and column.type.timezone:
        return "timestamptz"
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
    manifest = _manifest_table("migration_quarantine")
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
    quarantine_foreign_key = next(iter(table.foreign_key_constraints))
    quarantine_target = quarantine_foreign_key.elements[0].target_fullname.split(".")
    assert {
        "name": quarantine_foreign_key.name,
        "columns": list(quarantine_foreign_key.columns.keys()),
        "references": {
            "table": quarantine_target[0],
            "columns": [quarantine_target[1]],
        },
        "match": quarantine_foreign_key.match or "SIMPLE",
        "on_delete": quarantine_foreign_key.ondelete or "NO ACTION",
        "composite": False,
        "cross_tenant": bool(quarantine_foreign_key.info.get("cross_tenant", False)),
    } == manifest["foreign_keys"][0]
    assert len(table.foreign_key_constraints) == 1
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
        "conditional_update_columns": sorted(
            MigrationQuarantine.immutability.conditional_update_columns
        ),
        "coverage": MigrationQuarantine.immutability.coverage.value,
        "unclassified_handoff": (MigrationQuarantine.immutability.unclassified_handoff),
    } == {
        key: sorted(value) if isinstance(value, list) else value
        for key, value in manifest["immutability"].items()
    }
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


def _unique_column_sets(table: Table) -> list[set[str]]:
    """表の主キーと一意制約・一意索引の構成列集合を返す。"""
    unique_columns = [set(table.primary_key.columns.keys())]
    unique_columns.extend(
        set(constraint.columns.keys())
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    )
    unique_columns.extend(
        set(index.columns.keys()) for index in table.indexes if index.unique
    )
    return unique_columns


def test_migrated_final_lineups_match_manifest_contract() -> None:
    """移行元最終オーダーの models が manifest と exact-set 一致する。"""
    manifest = _manifest_table("migrated_final_lineups")
    table = cast(Table, MigratedFinalLineup.__table__)

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

    actual_foreign_keys = sorted(
        (
            {
                "name": constraint.name,
                "columns": list(constraint.columns.keys()),
                "references": {
                    "table": constraint.elements[0].target_fullname.split(".")[0],
                    "columns": [
                        element.target_fullname.split(".")[1]
                        for element in constraint.elements
                    ],
                },
                "match": constraint.match or "SIMPLE",
                "on_delete": constraint.ondelete or "NO ACTION",
                "composite": len(constraint.columns) > 1,
                "cross_tenant": bool(constraint.info.get("cross_tenant", False)),
            }
            for constraint in table.foreign_key_constraints
        ),
        key=lambda constraint: str(constraint["name"]),
    )
    assert actual_foreign_keys == sorted(
        manifest["foreign_keys"], key=lambda constraint: constraint["name"]
    )

    actual_unique_constraints = [
        {
            "name": table.primary_key.name,
            "kind": "PRIMARY KEY",
            "columns": list(table.primary_key.columns.keys()),
            "predicate": None,
            "roles": sorted(table.primary_key.info["roles"]),
        }
    ]
    actual_unique_constraints.extend(
        {
            "name": index.name,
            "kind": "UNIQUE INDEX",
            "columns": list(index.columns.keys()),
            "predicate": str(index.dialect_options["postgresql"]["where"]),
            "roles": sorted(index.info["roles"]),
        }
        for index in table.indexes
        if index.unique
    )
    expected_unique_constraints = [
        {
            "name": constraint["name"],
            "kind": constraint["kind"],
            "columns": constraint["columns"],
            "predicate": constraint["predicate"],
            "roles": sorted(constraint["roles"]),
        }
        for constraint in manifest["unique_constraints"]
    ]
    assert sorted(
        actual_unique_constraints, key=lambda constraint: str(constraint["name"])
    ) == sorted(
        expected_unique_constraints, key=lambda constraint: str(constraint["name"])
    )
    assert [index for index in table.indexes if not index.unique] == []
    assert manifest["indexes"] == []
    assert {
        "deletion": MigratedFinalLineup.lifecycle.deletion.value,
        "append_mode": MigratedFinalLineup.lifecycle.append_mode.value,
        "migration_retirement": (
            MigratedFinalLineup.lifecycle.migration_retirement.value
        ),
    } == manifest["lifecycle"]
    assert {
        "protected_columns": sorted(MigratedFinalLineup.immutability.protected_columns),
        "allowed_update_columns": sorted(
            MigratedFinalLineup.immutability.allowed_update_columns
        ),
        "conditional_update_columns": sorted(
            MigratedFinalLineup.immutability.conditional_update_columns
        ),
        "coverage": MigratedFinalLineup.immutability.coverage.value,
        "unclassified_handoff": (MigratedFinalLineup.immutability.unclassified_handoff),
    } == {
        key: sorted(value) if isinstance(value, list) else value
        for key, value in manifest["immutability"].items()
    }
    assert set(table.columns.keys()).isdisjoint(manifest["forbidden_columns"])


def test_migrated_final_lineups_keep_only_unresolved_source_columns() -> None:
    """最終オーダーが8列だけで解決列と行識別子の一意性を持たない。"""
    table = cast(Table, MigratedFinalLineup.__table__)
    column_names = set(table.columns.keys())

    assert len(column_names) == 8
    assert column_names == {
        column["name"]
        for column in _manifest_table("migrated_final_lineups")["columns"]
    }
    assert all(not column.startswith("resolved_") for column in column_names)
    assert not table.columns["import_batch_id"].nullable
    assert all(
        "legacy_row_identifier" not in columns for columns in _unique_column_sets(table)
    )


def test_existing_migration_generation_contract_is_preserved() -> None:
    """移行世代の部分一意、D3 と保持端末の契約を既存 model で検査する。"""
    manifest = _manifest_table("recording_generations")
    table = cast(Table, RecordingGeneration.__table__)
    migration_index = next(
        index
        for index in table.indexes
        if index.name == "uq_recording_generations_migration"
    )
    expected_index = next(
        constraint
        for constraint in manifest["unique_constraints"]
        if constraint["name"] == "uq_recording_generations_migration"
    )

    assert {
        "name": migration_index.name,
        "kind": "UNIQUE INDEX",
        "columns": list(migration_index.columns.keys()),
        "predicate": str(migration_index.dialect_options["postgresql"]["where"]),
        "roles": sorted(migration_index.info["roles"]),
    } == {
        "name": expected_index["name"],
        "kind": expected_index["kind"],
        "columns": expected_index["columns"],
        "predicate": expected_index["predicate"],
        "roles": sorted(expected_index["roles"]),
    }
    confirmed_watermark = table.columns["confirmed_watermark"]
    assert isinstance(confirmed_watermark.type, BigInteger)
    assert not confirmed_watermark.nullable
    assert _column_default(confirmed_watermark) == "0"
    assert table.columns["holder_device"].nullable
    assert "kind <> 'migration' OR holder_device IS NULL" in {
        str(check.sqltext)
        for check in table.constraints
        if isinstance(check, CheckConstraint)
    }


def test_play_rows_keep_migration_verification_separate_from_play_number() -> None:
    """未検証印と移行行識別子が業務上のプレイ番号から独立している。"""
    table = cast(Table, PlayRow.__table__)
    migration_unverified = table.columns["migration_unverified"]

    assert isinstance(migration_unverified.type, Boolean)
    assert not migration_unverified.nullable
    assert _column_default(migration_unverified) == "false"
    assert table.columns["legacy_row_identifier"] is not table.columns["play_number"]
    assert (
        table.columns["legacy_row_identifier"].name != table.columns["play_number"].name
    )
    assert all(
        "legacy_row_identifier" not in columns for columns in _unique_column_sets(table)
    )


def test_migrated_final_lineup_migration_contains_no_dml_or_forbidden_ddl() -> None:
    """最終オーダー migration が権限 DDL・DML を含まないと示す。"""
    source = _MIGRATED_FINAL_LINEUP_MIGRATION_PATH.read_text(encoding="utf-8").upper()

    assert "INSERT" not in source
    assert "BULK_INSERT" not in source
    assert "CREATE POLICY" not in source
    assert "CREATE ROLE" not in source
    assert "ALTER ROLE" not in source
    assert "CREATE_ALL" not in source


def _index_columns(index: Index) -> list[str]:
    """索引の列順と降順指定を manifest の形へ変換する。"""
    columns: list[str] = []
    for expression in index.expressions:
        if isinstance(expression, Column):
            columns.append(expression.name)
            continue
        if (
            isinstance(expression, UnaryExpression)
            and expression.modifier is operators.desc_op
            and isinstance(expression.element, Column)
        ):
            columns.append(f"{expression.element.name} DESC")
            continue
        raise AssertionError(f"未対応の索引式: {index.name}: {expression}")
    return columns


def _foreign_key_contracts(table: Table) -> list[dict[str, object]]:
    """Models の FK を manifest と比較できる形へ変換する。"""
    contracts: list[dict[str, object]] = []
    for constraint in table.foreign_key_constraints:
        targets = [
            element.target_fullname.split(".") for element in constraint.elements
        ]
        target_tables = {target[0] for target in targets}
        if len(target_tables) != 1:
            raise AssertionError(f"FK の参照先表が一意でない: {constraint.name}")
        contracts.append(
            {
                "name": constraint.name,
                "columns": list(constraint.columns.keys()),
                "references": {
                    "table": target_tables.pop(),
                    "columns": [target[1] for target in targets],
                },
                "match": constraint.match or "SIMPLE",
                "on_delete": constraint.ondelete or "NO ACTION",
                "composite": len(constraint.columns) > 1,
                "cross_tenant": bool(constraint.info.get("cross_tenant", False)),
            }
        )
    return sorted(contracts, key=lambda contract: str(contract["name"]))


def _unique_contracts(table: Table) -> list[dict[str, object]]:
    """Models の主キー・一意制約・一意索引を比較用に返す。"""
    contracts: list[dict[str, object]] = [
        {
            "name": table.primary_key.name,
            "kind": "PRIMARY KEY",
            "columns": list(table.primary_key.columns.keys()),
            "predicate": None,
            "roles": sorted(table.primary_key.info["roles"]),
        }
    ]
    contracts.extend(
        {
            "name": constraint.name,
            "kind": "UNIQUE",
            "columns": list(constraint.columns.keys()),
            "predicate": None,
            "roles": sorted(constraint.info["roles"]),
        }
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    )
    contracts.extend(
        {
            "name": index.name,
            "kind": "UNIQUE INDEX",
            "columns": _index_columns(index),
            "predicate": (
                None
                if index.dialect_options["postgresql"]["where"] is None
                else str(index.dialect_options["postgresql"]["where"])
            ),
            "roles": sorted(index.info["roles"]),
        }
        for index in table.indexes
        if index.unique
    )
    return sorted(contracts, key=lambda contract: str(contract["name"]))


def _manifest_unique_contracts(manifest: dict[str, Any]) -> list[dict[str, object]]:
    """Manifest の一意制約からカタログ照合対象だけを返す。"""
    return sorted(
        (
            {
                "name": constraint["name"],
                "kind": constraint["kind"],
                "columns": constraint["columns"],
                "predicate": constraint["predicate"],
                "roles": sorted(constraint["roles"]),
            }
            for constraint in manifest["unique_constraints"]
        ),
        key=lambda contract: str(contract["name"]),
    )


def test_migration_result_and_report_models_match_manifest_exactly() -> None:
    """移行結果・解決・警告レポート3表が manifest と exact-set 一致する。"""
    models = {
        "migration_runs": MigrationRun,
        "migration_resolution_reports": MigrationResolutionReport,
        "migration_warning_reports": MigrationWarningReport,
    }

    for table_name, model in models.items():
        manifest = _manifest_table(table_name)
        table = cast(Table, model.__table__)
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
        assert _foreign_key_contracts(table) == sorted(
            manifest["foreign_keys"], key=lambda constraint: constraint["name"]
        )
        assert _unique_contracts(table) == _manifest_unique_contracts(manifest)
        assert sorted(
            (
                {
                    "name": index.name,
                    "columns": _index_columns(index),
                    "predicate": (
                        None
                        if index.dialect_options["postgresql"]["where"] is None
                        else str(index.dialect_options["postgresql"]["where"])
                    ),
                    "purpose": index.info["purpose"],
                }
                for index in table.indexes
                if not index.unique
            ),
            key=lambda index: str(index["name"]),
        ) == sorted(manifest["indexes"], key=lambda index: index["name"])
        assert {
            "deletion": model.lifecycle.deletion.value,
            "append_mode": model.lifecycle.append_mode.value,
            "migration_retirement": model.lifecycle.migration_retirement.value,
        } == manifest["lifecycle"]
        assert {
            "protected_columns": sorted(model.immutability.protected_columns),
            "allowed_update_columns": sorted(model.immutability.allowed_update_columns),
            "conditional_update_columns": sorted(
                model.immutability.conditional_update_columns
            ),
            "coverage": model.immutability.coverage.value,
            "unclassified_handoff": model.immutability.unclassified_handoff,
        } == {
            key: sorted(value) if isinstance(value, list) else value
            for key, value in manifest["immutability"].items()
        }
        assert set(table.columns.keys()).isdisjoint(manifest["forbidden_columns"])


def test_migration_reports_keep_duplicates_and_global_scope_representable() -> None:
    """重複行を拒否する一意性・警告種別CHECK・テナント列が無い。"""
    run = cast(Table, MigrationRun.__table__)
    resolution = cast(Table, MigrationResolutionReport.__table__)
    warning = cast(Table, MigrationWarningReport.__table__)

    for table in (run, resolution, warning):
        assert "tenant_id" not in table.columns
    assert "import_batch_id" not in run.columns
    assert not resolution.columns["import_batch_id"].nullable
    assert not warning.columns["import_batch_id"].nullable
    assert "retired_at" in run.columns
    assert "retired_at" not in resolution.columns
    assert "retired_at" not in warning.columns
    assert isinstance(warning.columns["warning_kind"].type, Text)
    assert not any(
        isinstance(constraint, CheckConstraint) for constraint in warning.constraints
    )

    for table, column_name in (
        (cast(Table, MigrationQuarantine.__table__), "raw_payload"),
        (cast(Table, MigratedFinalLineup.__table__), "legacy_row_identifier"),
        (cast(Table, PlayRow.__table__), "legacy_row_identifier"),
        (warning, "legacy_row_identifier"),
    ):
        assert all(column_name not in columns for columns in _unique_column_sets(table))

    assert "移行元の重複は 1 行に潰さず 2 行として取り込み" in (
        MigrationWarningReport.__doc__ or ""
    )
    assert "DB は重複を拒否しない" in (MigrationWarningReport.__doc__ or "")


def test_migration_reports_migration_contains_no_dml_or_forbidden_ddl() -> None:
    """移行レポート migration が権限 DDL・DML を含まないと示す。"""
    source = _MIGRATION_REPORTS_MIGRATION_PATH.read_text(encoding="utf-8").upper()

    assert "INSERT" not in source
    assert "BULK_INSERT" not in source
    assert "CREATE POLICY" not in source
    assert "CREATE ROLE" not in source
    assert "ALTER ROLE" not in source
    assert "CREATE_ALL" not in source
