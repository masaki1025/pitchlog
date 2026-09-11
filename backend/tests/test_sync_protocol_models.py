"""イベントスロット・操作イベントモデルを manifest と照合する。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict, cast

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql.schema import DefaultClause, Index, Table

from pitchlog.db.sync_protocol.models import (
    EventSlot,
    IdempotencyLedger,
    OperationEvent,
    RejectedEventOriginal,
    TemporaryPlayerIdMapping,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_MANIFEST_PATH = _REPOSITORY_ROOT / "contracts" / "db" / "schema-manifest.json"
_MODEL_CLASSES: dict[str, Any] = {
    "event_slots": EventSlot,
    "operation_events": OperationEvent,
    "temporary_player_id_mappings": TemporaryPlayerIdMapping,
    "idempotency_ledger": IdempotencyLedger,
    "rejected_event_originals": RejectedEventOriginal,
}
_C12_CHECKS = {
    "ledger_kind = 'accepted'",
    "(d1 IS NULL) = (generation IS NULL)",
    "event_kind NOT IN ('play_change', 'play_delete', 'substitution_change') OR "
    "(d1 IS NULL AND d2 IS NULL AND generation IS NULL AND target_generation IS "
    "NOT NULL AND target_d1 IS NOT NULL AND expected_version IS NOT NULL)",
    "event_kind IN ('play_change', 'play_delete', 'substitution_change') OR d1 IS "
    "NOT NULL",
}
_FORBIDDEN_EVENT_COLUMNS = {
    "v12",
    "recording_authority_proof",
    "created_by",
    "created_by_user_id",
    "inputter_id",
}


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


def _load_manifest_tables() -> dict[str, dict[str, Any]]:
    """Manifest の表を名前で引ける形にして返す。"""
    manifest = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    return {table["name"]: table for table in manifest["tables"]}


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
    if isinstance(column.type, Boolean):
        return "boolean"
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
    contracts: list[_ColumnContract] = []
    for column in table.columns:
        if column.nullable is None:
            raise AssertionError(f"NULL 性が未確定である: {table.name}.{column.name}")
        contracts.append(
            _ColumnContract(
                name=column.name,
                type=_column_type_name(column),
                nullable=column.nullable,
                default=_column_default(column),
            )
        )
    return sorted(contracts, key=lambda contract: contract["name"])


def _index_predicate(index: Index) -> str | None:
    """PostgreSQL 部分索引の述語全文を返す。"""
    predicate = index.dialect_options["postgresql"]["where"]
    return None if predicate is None else str(predicate)


def _model_unique_constraints(table: Table) -> list[_UniqueContract]:
    """主キー・一意制約・一意索引を manifest の形へ変換する。"""
    primary_key_name = table.primary_key.name
    if not isinstance(primary_key_name, str):
        raise AssertionError(f"主キー名が空である: {table.name}")
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
            raise AssertionError(f"一意制約名が空である: {table.name}")
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
            raise AssertionError(f"一意索引名が空である: {table.name}")
        contracts.append(
            {
                "name": index.name,
                "kind": "UNIQUE INDEX",
                "columns": list(index.columns.keys()),
                "predicate": _index_predicate(index),
                "roles": sorted(str(role) for role in index.info["roles"]),
            }
        )
    return sorted(contracts, key=lambda contract: contract["name"])


def _manifest_unique_constraints(table: dict[str, Any]) -> list[_UniqueContract]:
    """Manifest の一意制約から比較対象の構造を取り出す。"""
    return sorted(
        (
            {
                "name": constraint["name"],
                "kind": constraint["kind"],
                "columns": constraint["columns"],
                "predicate": constraint["predicate"],
                "roles": sorted(constraint["roles"]),
            }
            for constraint in table["unique_constraints"]
        ),
        key=lambda contract: contract["name"],
    )


def _model_indexes(table: Table) -> list[_IndexContract]:
    """非一意索引を manifest の索引契約へ変換する。"""
    contracts: list[_IndexContract] = []
    for index in table.indexes:
        if index.unique:
            continue
        if not isinstance(index.name, str):
            raise AssertionError(f"索引名が空である: {table.name}")
        contracts.append(
            {
                "name": index.name,
                "columns": list(index.columns.keys()),
                "predicate": _index_predicate(index),
                "purpose": str(index.info["purpose"]),
            }
        )
    return sorted(contracts, key=lambda contract: contract["name"])


def _model_lifecycle(model: Any) -> dict[str, str]:
    """モデルのライフサイクル3軸を manifest の形へ変換する。"""
    return {
        "deletion": model.lifecycle.deletion.value,
        "append_mode": model.lifecycle.append_mode.value,
        "migration_retirement": model.lifecycle.migration_retirement.value,
    }


def _model_immutability(model: Any) -> dict[str, list[str]]:
    """モデルの不変列マトリクスを比較用に正規化する。"""
    return {
        "protected_columns": sorted(model.immutability.protected_columns),
        "allowed_update_columns": sorted(model.immutability.allowed_update_columns),
    }


def _foreign_key_targets(table: Table) -> dict[str, tuple[str, tuple[str, ...]]]:
    """FK 名から参照先表と列順への対応を返す。"""
    targets: dict[str, tuple[str, tuple[str, ...]]] = {}
    for constraint in table.foreign_key_constraints:
        if not isinstance(constraint.name, str):
            raise AssertionError(f"FK 名が空である: {table.name}")
        target_parts = [
            element.target_fullname.rsplit(".", maxsplit=1)
            for element in constraint.elements
        ]
        target_tables = {part[0] for part in target_parts}
        if len(target_tables) != 1:
            raise AssertionError(f"FK の参照先表が一意でない: {constraint.name}")
        targets[constraint.name] = (
            target_tables.pop(),
            tuple(part[1] for part in target_parts),
        )
    return targets


def test_sync_protocol_models_match_manifest_contracts() -> None:
    """5 表の models が FK 以外の manifest 契約と exact-set 一致する。"""
    manifest_tables = _load_manifest_tables()

    for table_name, model in _MODEL_CLASSES.items():
        manifest = manifest_tables[table_name]
        table = model.__table__

        assert _model_columns(table) == sorted(
            manifest["columns"], key=lambda column: column["name"]
        )
        assert {
            str(check.sqltext)
            for check in table.constraints
            if isinstance(check, CheckConstraint)
        } == set(manifest["checks"])
        assert _model_unique_constraints(table) == _manifest_unique_constraints(
            manifest
        )
        assert _model_indexes(table) == sorted(
            manifest["indexes"], key=lambda index: index["name"]
        )
        assert _model_lifecycle(model) == manifest["lifecycle"]
        assert _model_immutability(model) == {
            key: sorted(value) for key, value in manifest["immutability"].items()
        }
        assert set(table.columns.keys()).isdisjoint(manifest["forbidden_columns"])


def test_event_slot_primary_key_has_all_three_roles() -> None:
    """イベントスロット主キーが完全キーで非排他の3役割を持つと示す。"""
    contracts = _model_unique_constraints(cast(Table, EventSlot.__table__))

    assert contracts == [
        {
            "name": "pk_event_slots",
            "kind": "PRIMARY KEY",
            "columns": ["tenant_id", "game_id", "generation", "d1"],
            "predicate": None,
            "roles": ["business_unique", "fk_target", "primary_key"],
        }
    ]


def test_operation_event_c12_checks_and_forbidden_columns() -> None:
    """C12 を表レベル CHECK で表現し入力者識別列を持たないと示す。"""
    table = cast(Table, OperationEvent.__table__)
    checks = {
        str(check.sqltext)
        for check in table.constraints
        if isinstance(check, CheckConstraint)
    }

    assert checks == _C12_CHECKS
    assert table.columns["generation"].nullable
    assert table.columns["d1"].nullable
    assert table.columns["d2"].nullable
    assert set(table.columns.keys()).isdisjoint(_FORBIDDEN_EVENT_COLUMNS)


def test_operation_event_slot_fks_and_partial_uniqueness() -> None:
    """V10 のイベントスロット参照と一意制約3件を検査する。"""
    event_table = cast(Table, OperationEvent.__table__)
    slot_table = cast(Table, EventSlot.__table__)
    event_foreign_keys = _foreign_key_targets(event_table)
    slot_foreign_keys = _foreign_key_targets(slot_table)
    uniques = {
        contract["name"]: contract
        for contract in _model_unique_constraints(event_table)
    }

    assert slot_foreign_keys == {
        "fk_event_slots_game": ("games", ("tenant_id", "id")),
        "fk_event_slots_generation": (
            "recording_generations",
            ("tenant_id", "game_id", "generation"),
        ),
    }
    assert event_foreign_keys == {
        "fk_operation_events_game": ("games", ("tenant_id", "id")),
        "fk_operation_events_ledger": (
            "idempotency_ledger",
            ("tenant_id", "d5", "kind"),
        ),
        "fk_operation_events_slot": (
            "event_slots",
            ("tenant_id", "game_id", "generation", "d1"),
        ),
        "fk_operation_events_target": (
            "event_slots",
            ("tenant_id", "game_id", "generation", "d1"),
        ),
    }
    assert uniques["uq_operation_events_active_slot"]["predicate"] == (
        "d1 IS NOT NULL AND replaced_at IS NULL"
    )
    assert uniques["uq_operation_events_active_d2"]["predicate"] == (
        "d2 IS NOT NULL AND replaced_at IS NULL AND retired_at IS NULL"
    )
    assert uniques["uq_operation_events_d5"]["predicate"] is None


def test_temporary_player_mapping_uses_immutable_uuid_identifiers() -> None:
    """一時 ID が UUID でテナント内一意かつ写像の両端が不変と示す。"""
    table = cast(Table, TemporaryPlayerIdMapping.__table__)
    uniques = {
        contract["name"]: contract for contract in _model_unique_constraints(table)
    }

    assert isinstance(table.columns["temporary_id"].type, Uuid)
    assert uniques["uq_temporary_player_id_mappings_temporary"] == {
        "name": "uq_temporary_player_id_mappings_temporary",
        "kind": "UNIQUE",
        "columns": ["tenant_id", "temporary_id"],
        "predicate": None,
        "roles": ["business_unique"],
    }
    assert TemporaryPlayerIdMapping.immutability.protected_columns == frozenset(
        {"temporary_id", "player_id"}
    )
    assert TemporaryPlayerIdMapping.immutability.allowed_update_columns == frozenset()


def test_d5_ledger_and_sync_sources_use_kind_bound_full_match_fks() -> None:
    """D5 台帳と同期側参照元が種別を含む完全 FK で結ばれると示す。"""
    ledger_table = cast(Table, IdempotencyLedger.__table__)
    event_table = cast(Table, OperationEvent.__table__)
    rejected_table = cast(Table, RejectedEventOriginal.__table__)
    ledger_uniques = {
        contract["name"]: contract
        for contract in _model_unique_constraints(ledger_table)
    }

    assert not ledger_table.columns["d5"].nullable
    assert "game_id" not in ledger_table.columns
    assert ledger_uniques["uq_idempotency_ledger_kind"] == {
        "name": "uq_idempotency_ledger_kind",
        "kind": "UNIQUE",
        "columns": ["tenant_id", "d5", "kind"],
        "predicate": None,
        "roles": ["fk_target"],
    }
    assert not event_table.columns["ledger_kind"].nullable
    assert not rejected_table.columns["kind"].nullable

    source_fks = {
        constraint.name: constraint
        for table in (event_table, rejected_table)
        for constraint in table.foreign_key_constraints
        if constraint.name
        in {
            "fk_operation_events_ledger",
            "fk_rejected_event_originals_ledger",
        }
    }
    assert set(source_fks) == {
        "fk_operation_events_ledger",
        "fk_rejected_event_originals_ledger",
    }
    for constraint in source_fks.values():
        assert constraint.match == "FULL"
        assert list(constraint.columns.keys()) in (
            ["tenant_id", "d5", "ledger_kind"],
            ["tenant_id", "d5", "kind"],
        )
