"""記録権世代・退避イベント原本モデルを manifest と照合する。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict, cast

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import operators
from sqlalchemy.sql.elements import UnaryExpression
from sqlalchemy.sql.schema import DefaultClause, Index, Table

from pitchlog.db.recording_rights.models import (
    EvacuatedEventOriginal,
    RecordingGeneration,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_MANIFEST_PATH = _REPOSITORY_ROOT / "contracts" / "db" / "schema-manifest.json"


class _ColumnContract(TypedDict):
    """比較用の列契約。"""

    name: str
    type: str
    nullable: bool
    default: str | None


class _UniqueContract(TypedDict):
    """比較用の一意制約契約。"""

    name: str
    kind: str
    columns: list[str]
    predicate: str | None
    roles: list[str]


class _IndexContract(TypedDict):
    """比較用の索引契約。"""

    name: str
    columns: list[str]
    predicate: str | None
    purpose: str


def _manifest_table(table_name: str) -> dict[str, Any]:
    """指定した表の manifest 契約を返す。"""
    manifest = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    return next(table for table in manifest["tables"] if table["name"] == table_name)


def _column_type_name(column: Column[Any]) -> str:
    """SQLAlchemy の列型を manifest の型名へ正規化する。"""
    if isinstance(column.type, Uuid):
        return "uuid"
    if isinstance(column.type, JSONB):
        return "jsonb"
    if isinstance(column.type, BigInteger):
        return "bigint"
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


def _model_columns(table: Table) -> list[_ColumnContract]:
    """Models の列契約を manifest と同じ形へ変換する。"""
    return sorted(
        (
            _ColumnContract(
                name=column.name,
                type=_column_type_name(column),
                nullable=bool(column.nullable),
                default=_column_default(column),
            )
            for column in table.columns
        ),
        key=lambda contract: contract["name"],
    )


def _model_uniques(table: Table) -> list[_UniqueContract]:
    """主キー・一意制約・一意索引を manifest と同じ形へ変換する。"""
    primary_key_name = table.primary_key.name
    if not isinstance(primary_key_name, str):
        raise AssertionError("記録権モデルの主キー名が空である")
    contracts: list[_UniqueContract] = [
        {
            "name": primary_key_name,
            "kind": "PRIMARY KEY",
            "columns": list(table.primary_key.columns.keys()),
            "predicate": None,
            "roles": sorted(str(role) for role in table.primary_key.info["roles"]),
        }
    ]
    for constraint in table.constraints:
        if not isinstance(constraint, UniqueConstraint):
            continue
        if not isinstance(constraint.name, str):
            raise AssertionError("記録権モデルの一意制約名が空である")
        contracts.append(
            {
                "name": constraint.name,
                "kind": "UNIQUE",
                "columns": list(constraint.columns.keys()),
                "predicate": None,
                "roles": sorted(str(role) for role in constraint.info["roles"]),
            }
        )
    for index in table.indexes:
        if not index.unique:
            continue
        if not isinstance(index.name, str):
            raise AssertionError("記録権モデルの一意索引名が空である")
        predicate = index.dialect_options["postgresql"]["where"]
        contracts.append(
            {
                "name": index.name,
                "kind": "UNIQUE INDEX",
                "columns": _index_columns(index),
                "predicate": None if predicate is None else str(predicate),
                "roles": sorted(str(role) for role in index.info["roles"]),
            }
        )
    return sorted(contracts, key=lambda contract: contract["name"])


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


def _model_indexes(table: Table) -> list[_IndexContract]:
    """記録権モデルの非一意索引を manifest と同じ形へ変換する。"""
    contracts: list[_IndexContract] = []
    for index in table.indexes:
        if index.unique:
            continue
        if not isinstance(index.name, str):
            raise AssertionError("退避原本の索引名が空である")
        predicate = index.dialect_options["postgresql"]["where"]
        contracts.append(
            {
                "name": index.name,
                "columns": _index_columns(index),
                "predicate": None if predicate is None else str(predicate),
                "purpose": str(index.info["purpose"]),
            }
        )
    return sorted(contracts, key=lambda contract: contract["name"])


def _assert_model_matches_manifest(model: Any, table_name: str) -> None:
    """記録権モデルと manifest の FK 以外を exact-set 照合する。"""
    manifest = _manifest_table(table_name)
    table = cast(Table, model.__table__)

    assert _model_columns(table) == sorted(
        manifest["columns"], key=lambda column: column["name"]
    )
    assert {
        str(check.sqltext)
        for check in table.constraints
        if isinstance(check, CheckConstraint)
    } == set(manifest["checks"])
    assert _model_uniques(table) == sorted(
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
        key=lambda contract: contract["name"],
    )
    assert _model_indexes(table) == sorted(
        manifest["indexes"], key=lambda index: index["name"]
    )
    assert {
        "deletion": model.lifecycle.deletion.value,
        "append_mode": model.lifecycle.append_mode.value,
        "migration_retirement": model.lifecycle.migration_retirement.value,
    } == manifest["lifecycle"]
    assert {
        "protected_columns": sorted(model.immutability.protected_columns),
        "allowed_update_columns": sorted(model.immutability.allowed_update_columns),
    } == {key: sorted(value) for key, value in manifest["immutability"].items()}
    assert set(table.columns.keys()).isdisjoint(manifest["forbidden_columns"])


def test_recording_rights_models_match_manifest_contracts() -> None:
    """記録権世代と退避原本が manifest 契約と exact-set 一致する。"""
    _assert_model_matches_manifest(EvacuatedEventOriginal, "evacuated_event_originals")
    _assert_model_matches_manifest(RecordingGeneration, "recording_generations")


def test_evacuated_original_uses_kind_bound_full_match_fk() -> None:
    """退避原本が非 NULL の固定種別を含む MATCH FULL で台帳を参照する。"""
    table = cast(Table, EvacuatedEventOriginal.__table__)
    ledger_fk = next(
        constraint
        for constraint in table.foreign_key_constraints
        if constraint.name == "fk_evacuated_event_originals_ledger"
    )

    assert not table.columns["kind"].nullable
    assert list(ledger_fk.columns.keys()) == ["tenant_id", "d5", "kind"]
    assert ledger_fk.match == "FULL"
    assert [element.target_fullname for element in ledger_fk.elements] == [
        "idempotency_ledger.tenant_id",
        "idempotency_ledger.d5",
        "idempotency_ledger.kind",
    ]


def test_recording_generation_d3_starts_from_required_zero() -> None:
    """D3 が bigint NOT NULL かつ新世代の既定値 0 であると示す。"""
    table = cast(Table, RecordingGeneration.__table__)
    d3 = table.columns["confirmed_watermark"]

    assert isinstance(d3.type, BigInteger)
    assert not d3.nullable
    assert _column_default(d3) == "0"


def test_step_twelve_evacuated_original_contract_is_preserved() -> None:
    """退避原本の物理キーと保持期限の NULL 既定を検査する。"""
    table = cast(Table, EvacuatedEventOriginal.__table__)
    uniques = {contract["name"]: contract for contract in _model_uniques(table)}
    retention_deadline = table.columns["retention_deadline"]

    assert uniques["uq_evacuated_event_originals_source"]["columns"] == [
        "tenant_id",
        "game_id",
        "old_generation",
        "original_d1",
    ]
    assert retention_deadline.nullable
    assert retention_deadline.default is None
    assert retention_deadline.server_default is None
