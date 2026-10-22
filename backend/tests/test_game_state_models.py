"""試合・スタメン・出場区間モデルを manifest と照合する。"""

from __future__ import annotations

import ast
import json
from copy import deepcopy
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any, TypedDict, cast
from uuid import UUID

import pytest
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Double,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import operators
from sqlalchemy.sql.elements import UnaryExpression
from sqlalchemy.sql.schema import DefaultClause, Index, Table
from type_boundary_contract import (
    PLAY_ROW_VOCABULARY_REFERENCES,
    ColumnContract,
    legacy_storage_types,
    play_row_destination_columns,
    play_row_type_violations,
)

from pitchlog.db.game_state import rule_snapshot
from pitchlog.db.game_state.models import (
    Game,
    GameLineup,
    GameTypeRuleDefault,
    LineupMemory,
    ParticipationInterval,
    PlayRow,
    PlayRunner,
    RuleSet,
    TournamentRuleAssignment,
    derive_migrated_play_row_id,
)
from pitchlog.db.game_state.rule_snapshot import (
    DomainValidatedRuleSnapshot,
    RuleSnapshotContractUnavailable,
    RuleSnapshotFailure,
    RuleSnapshotInvalid,
    decode_applied_rules,
    decode_structure,
    encode_applied_rules,
    validate_correlations,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_MANIFEST_PATH = _REPOSITORY_ROOT / "contracts" / "db" / "schema-manifest.json"
_DATA_MODEL_PATH = _REPOSITORY_ROOT / "docs" / "design" / "data-model.md"
_LEGACY_DATA_LAYER_PATH = (
    _REPOSITORY_ROOT / "docs" / "legacy" / "research" / "data-layer.md"
)
_PLAY_ROW_DESTINATION_MIGRATION_PATH = (
    _REPOSITORY_ROOT
    / "backend"
    / "migrations"
    / "versions"
    / "0020_play_row_destinations.py"
)
_MODEL_CLASSES: dict[str, Any] = {
    "games": Game,
    "lineup_memories": LineupMemory,
    "game_lineups": GameLineup,
    "participation_intervals": ParticipationInterval,
    "rule_sets": RuleSet,
    "game_type_rule_defaults": GameTypeRuleDefault,
    "tournament_rule_assignments": TournamentRuleAssignment,
    "play_rows": PlayRow,
    "play_runners": PlayRunner,
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
    if isinstance(column.type, Integer):
        return "integer"
    if isinstance(column.type, Double):
        return "double precision"
    if isinstance(column.type, Numeric):
        return "numeric"
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


def _index_columns(index: Index) -> list[str]:
    """索引式を列順と降順指定を保った manifest 表記へ変換する。"""
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
                "columns": _index_columns(index),
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
                "columns": _index_columns(index),
                "predicate": _index_predicate(index),
                "purpose": str(index.info["purpose"]),
            }
        )
    return sorted(contracts, key=lambda contract: contract["name"])


def _model_lifecycle(model: Any) -> dict[str, str]:
    """モデルのライフサイクル 3 軸を manifest の形へ変換する。"""
    return {
        "deletion": model.lifecycle.deletion.value,
        "append_mode": model.lifecycle.append_mode.value,
        "migration_retirement": model.lifecycle.migration_retirement.value,
    }


def _model_immutability(model: Any) -> dict[str, object]:
    """モデルの不変列マトリクスを比較用に正規化する。"""
    return {
        "protected_columns": sorted(model.immutability.protected_columns),
        "allowed_update_columns": sorted(model.immutability.allowed_update_columns),
        "conditional_update_columns": sorted(
            model.immutability.conditional_update_columns
        ),
        "coverage": model.immutability.coverage.value,
        "unclassified_handoff": model.immutability.unclassified_handoff,
    }


def test_game_state_models_match_manifest_contracts() -> None:
    """9 表の models が FK 以外の manifest 契約と exact-set 一致する。"""
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
            key: sorted(value) if isinstance(value, list) else value
            for key, value in manifest["immutability"].items()
        }
        assert set(table.columns.keys()).isdisjoint(manifest["forbidden_columns"])


def test_uniform_number_snapshot_roles_match_the_three_way_design() -> None:
    """先発の正本と出場区間の導出背番号が別の更新契約を持つと示す。"""
    lineup_column = GameLineup.__table__.columns["entries_with_uniform_number_snapshot"]
    interval_column = ParticipationInterval.__table__.columns["uniform_number_snapshot"]

    assert isinstance(lineup_column.type, JSONB)
    assert not lineup_column.nullable
    assert GameLineup.immutability.protected_columns == frozenset(
        {"entries_with_uniform_number_snapshot"}
    )
    assert GameLineup.immutability.allowed_update_columns == frozenset()
    assert isinstance(interval_column.type, Text)
    assert interval_column.nullable
    assert "uniform_number_snapshot" not in (
        ParticipationInterval.immutability.protected_columns
    )
    assert "uniform_number_snapshot" not in (
        ParticipationInterval.immutability.allowed_update_columns
    )
    assert ParticipationInterval.immutability.allowed_update_columns == frozenset(
        {"valid_until_d2", "retired_at"}
    )


def test_partial_uniqueness_and_games_without_business_uniqueness() -> None:
    """部分一意2件の述語と試合の業務的一意性0件を検査する。"""
    lineup_uniques = {
        contract["name"]: contract
        for contract in _model_unique_constraints(cast(Table, LineupMemory.__table__))
    }
    interval_uniques = {
        contract["name"]: contract
        for contract in _model_unique_constraints(
            cast(Table, ParticipationInterval.__table__)
        )
    }
    game_uniques = _model_unique_constraints(cast(Table, Game.__table__))

    assert lineup_uniques["uq_lineup_memories_active"]["predicate"] == (
        "retired_at IS NULL"
    )
    assert interval_uniques["uq_participation_intervals_active"]["predicate"] == (
        "retired_at IS NULL"
    )
    assert game_uniques == [
        {
            "name": "pk_games",
            "kind": "PRIMARY KEY",
            "columns": ["tenant_id", "id"],
            "predicate": None,
            "roles": ["fk_target", "primary_key"],
        }
    ]


def _foreign_key_targets(table: Table) -> dict[str, set[str]]:
    """Models の FK 名から参照先表名集合への対応を返す。"""
    targets: dict[str, set[str]] = {}
    for constraint in table.foreign_key_constraints:
        if not isinstance(constraint.name, str):
            raise AssertionError(f"FK 名が空である: {table.name}")
        targets[constraint.name] = {
            element.target_fullname.rsplit(".", maxsplit=1)[0]
            for element in constraint.elements
        }
    return targets


def _model_legacy_source_columns(table: Table) -> dict[int, Column[Any]]:
    """モデル列の追跡情報から旧列番号と物理列の対応を導出する。"""
    columns: dict[int, Column[Any]] = {}
    for column in table.columns:
        for source_number in column.info.get("legacy_source_columns", ()):
            if source_number in columns:
                raise AssertionError(f"旧列番号 {source_number} の対応列が重複している")
            columns[source_number] = column
    return columns


def _migration_added_play_row_columns() -> set[str]:
    """是正 migration の upgrade が追加するプレイ行列を AST から導出する。"""
    tree = ast.parse(_PLAY_ROW_DESTINATION_MIGRATION_PATH.read_text(encoding="utf-8"))
    upgrade = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "upgrade"
    )
    columns: set[str] = set()
    for node in ast.walk(upgrade):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "op"
            and node.func.attr == "add_column"
            and len(node.args) >= 2
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == "play_rows"
        ):
            continue
        column_call = node.args[1]
        if not (
            isinstance(column_call, ast.Call)
            and column_call.args
            and isinstance(column_call.args[0], ast.Constant)
            and isinstance(column_call.args[0].value, str)
        ):
            raise AssertionError("追加列名を migration から解決できない")
        columns.add(column_call.args[0].value)
    return columns


def test_play_row_columns_cover_canonical_destinations_exactly() -> None:
    """正本でプレイ行へ送る旧列をモデル列が過不足なく覆う。"""
    expected = set(
        play_row_destination_columns(_DATA_MODEL_PATH.read_text(encoding="utf-8"))
    )
    actual = set(_model_legacy_source_columns(cast(Table, PlayRow.__table__)))

    assert actual == expected
    assert "compatibility_payload" not in PlayRow.__table__.columns


def test_play_row_vocabulary_destinations_reference_their_owning_layers() -> None:
    """語彙列が管理層またはテナント層の正しい参照形を持つ。"""
    table = cast(Table, PlayRow.__table__)
    actual: dict[int, str] = {}
    for constraint in table.foreign_key_constraints:
        target_tables = {
            element.target_fullname.rsplit(".", maxsplit=1)[0]
            for element in constraint.elements
        }
        if not target_tables <= {"tenant_vocabularies", "admin_vocabularies"}:
            continue
        assert len(target_tables) == 1
        target_table = target_tables.pop()
        source_columns = list(constraint.columns)
        vocabulary_column = source_columns[-1]
        if target_table == "tenant_vocabularies":
            assert [column.name for column in source_columns[:1]] == ["tenant_id"]
            assert [element.target_fullname for element in constraint.elements] == [
                "tenant_vocabularies.tenant_id",
                "tenant_vocabularies.key",
            ]
        else:
            assert len(source_columns) == 1
            assert [element.target_fullname for element in constraint.elements] == [
                "admin_vocabularies.key"
            ]
        assert constraint.match == "SIMPLE"
        source_numbers = vocabulary_column.info.get("legacy_source_columns", ())
        assert len(source_numbers) == 1
        actual[source_numbers[0]] = target_table

    assert actual == PLAY_ROW_VOCABULARY_REFERENCES


def test_all_play_row_destinations_follow_legacy_storage_type_contract() -> None:
    """プレイ行行き先の全母集団へ旧保存型契約を適用する。"""
    table = cast(Table, PlayRow.__table__)
    source_columns = _model_legacy_source_columns(table)
    columns = {
        ("play_rows", column.name): ColumnContract(
            _column_type_name(column), bool(column.nullable), _column_default(column)
        )
        for column in table.columns
    }

    assert (
        play_row_type_violations(
            play_row_destination_columns(_DATA_MODEL_PATH.read_text(encoding="utf-8")),
            {number: column.name for number, column in source_columns.items()},
            columns,
            legacy_storage_types(_LEGACY_DATA_LAYER_PATH.read_text(encoding="utf-8")),
        )
        == []
    )


def test_added_play_row_columns_preserve_legacy_storage_types_and_nullability() -> None:
    """是正で追加する列が追跡情報を持ち、NULL 可・既定値なしである。"""
    table = cast(Table, PlayRow.__table__)
    source_columns = _model_legacy_source_columns(table)

    for column_name in _migration_added_play_row_columns():
        column = table.columns[column_name]
        source_numbers = column.info.get("legacy_source_columns", ())
        assert len(source_numbers) == 1
        source_number = source_numbers[0]
        assert source_columns[source_number] is column
        assert column.nullable
        assert _column_default(column) is None


def test_rule_assignment_scope_and_game_snapshot_structure() -> None:
    """規則表のテナント範囲と試合スナップショットの独立性を検査する。"""
    game_table = cast(Table, Game.__table__)
    rule_set_table = cast(Table, RuleSet.__table__)
    game_type_table = cast(Table, GameTypeRuleDefault.__table__)
    tournament_table = cast(Table, TournamentRuleAssignment.__table__)

    applied_rules = game_table.columns["applied_rules"]
    assert isinstance(applied_rules.type, JSONB)
    assert not applied_rules.nullable
    assert "rule_sets" not in {
        target
        for targets in _foreign_key_targets(game_table).values()
        for target in targets
    }

    assert "tenant_id" not in rule_set_table.columns
    assert "tenant_id" not in game_type_table.columns
    assert not tournament_table.columns["tenant_id"].nullable
    assert _foreign_key_targets(game_type_table) == {
        "fk_game_type_rule_defaults_type": {"system_vocabularies"},
        "fk_game_type_rule_defaults_rule": {"rule_sets"},
    }
    assert _foreign_key_targets(tournament_table) == {
        "fk_tournament_rule_assignments_tournament": {"tenant_vocabularies"},
        "fk_tournament_rule_assignments_rule": {"rule_sets"},
    }


def test_migrated_play_row_id_is_stable_across_reprojection() -> None:
    """同じ旧行と正本イベントからの2回の再投影が同じ ID になる。"""
    source_event_id = UUID("018f7765-9380-7bf2-89fd-8dd231cc1e7b")
    legacy_row_identifier = "legacy-play-row:0042"

    first_projection = PlayRow(
        id=derive_migrated_play_row_id(source_event_id, legacy_row_identifier),
        source_event_id=source_event_id,
        legacy_row_identifier=legacy_row_identifier,
    )
    second_projection = PlayRow(
        id=derive_migrated_play_row_id(source_event_id, legacy_row_identifier),
        source_event_id=source_event_id,
        legacy_row_identifier=legacy_row_identifier,
    )

    assert first_projection.id == second_projection.id
    assert first_projection.id == UUID("04088b4f-ea70-5f83-8776-848ef4e03b40")


def test_play_projection_does_not_copy_d2_and_keeps_legacy_identity_nullable() -> None:
    """投影2表が D2 を複製せず通常入力へ旧行識別子を強制しない。"""
    play_table = cast(Table, PlayRow.__table__)
    runner_table = cast(Table, PlayRunner.__table__)

    assert "d2" not in play_table.columns
    assert "d2" not in runner_table.columns
    assert play_table.columns["legacy_row_identifier"].nullable
    assert PlayRow.immutability.protected_columns == frozenset(
        {"id", "source_event_id", "legacy_row_identifier"}
    )


def test_play_runner_has_one_required_responsible_pitcher_column() -> None:
    """走者1行が責任投手を1列だけ必須保持すると示す。"""
    table = cast(Table, PlayRunner.__table__)
    responsible_columns = [
        column.name
        for column in table.columns
        if column.name.startswith("responsible_pitcher")
    ]

    assert responsible_columns == ["responsible_pitcher_id"]
    assert not table.columns["responsible_pitcher_id"].nullable


def test_play_runner_status_source_contract() -> None:
    """走者状況の由来が既定値なしの必須二値として宣言されている。"""
    table = cast(Table, PlayRunner.__table__)
    status = table.columns["status"]
    status_source = table.columns["status_source"]
    checks = {
        constraint.name: str(constraint.sqltext)
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert isinstance(status.type, Text)
    assert not status.nullable
    assert isinstance(status_source.type, Text)
    assert not status_source.nullable
    assert _column_default(status_source) is None
    assert checks["ck_play_runners_status_source"] == (
        "status_source IN ('auto', 'manual')"
    )


_RULE_SET_ID = "0a000000-0000-4000-8000-000000000001"


def _valid_applied_rules() -> dict[str, Any]:
    """付録F-2の公式戦に相当する有効な6-key値を返す。"""
    return {
        "ruleSetId": _RULE_SET_ID,
        "regulationInnings": 9,
        "coldConditions": [],
        "extensionLimit": 12,
        "tiebreak": {
            "startInning": 10,
            "runnerPlacement": "no_out_first_second",
            "leadoffRule": "continue_lineup",
        },
        "dh": True,
    }


def test_rule_snapshot_round_trip_uses_six_key_schema() -> None:
    """正規のIDと凍結5値を保存形へ往復できる。"""
    raw = _valid_applied_rules()

    decoded = decode_applied_rules(raw)
    encoded = encode_applied_rules(decoded)

    assert decoded.structural.rule_set_id == UUID(_RULE_SET_ID)
    assert encoded == raw
    assert set(encoded) == {
        "ruleSetId",
        "regulationInnings",
        "coldConditions",
        "extensionLimit",
        "tiebreak",
        "dh",
    }
    raw["tiebreak"]["startInning"] = 11
    assert decoded.structural.tiebreak is not None
    assert decoded.structural.tiebreak.start_inning == 10
    with pytest.raises(FrozenInstanceError):
        setattr(decoded.structural, "regulation_innings", 8)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda raw: raw.clear(),
        lambda raw: raw.pop("ruleSetId"),
        lambda raw: raw.update({"unknown": 1}),
        lambda raw: raw["tiebreak"].update({"unknown": 1}),
        lambda raw: raw["coldConditions"].append({"pointDifference": 10}),
    ],
    ids=("old-empty", "old-five-key", "extra-key", "nested-extra", "nested-missing"),
)
def test_rule_snapshot_rejects_legacy_and_incomplete_shapes(mutate) -> None:
    """旧行と過不足のあるtop-level・入れ子値を補完しない。"""
    raw = _valid_applied_rules()
    mutate(raw)

    with pytest.raises(RuleSnapshotInvalid) as caught:
        decode_structure(raw)
    assert caught.value.kind is RuleSnapshotFailure.SHAPE
    assert caught.value.__cause__ is None


@pytest.mark.parametrize(
    ("key", "value", "expected_kind"),
    [
        (
            "ruleSetId",
            "0A000000-0000-4000-8000-000000000001",
            RuleSnapshotFailure.VALUE,
        ),
        ("ruleSetId", "not-a-uuid", RuleSnapshotFailure.VALUE),
        (
            "ruleSetId",
            "{0a000000-0000-4000-8000-000000000001}",
            RuleSnapshotFailure.VALUE,
        ),
        ("ruleSetId", UUID(_RULE_SET_ID), RuleSnapshotFailure.VALUE),
        ("regulationInnings", True, RuleSnapshotFailure.SHAPE),
        ("regulationInnings", 0, RuleSnapshotFailure.VALUE),
        ("regulationInnings", 100, RuleSnapshotFailure.VALUE),
        ("extensionLimit", 100, RuleSnapshotFailure.VALUE),
        (
            "coldConditions",
            [{"pointDifference": 0, "startInning": 5}],
            RuleSnapshotFailure.VALUE,
        ),
        (
            "coldConditions",
            [{"pointDifference": 1, "startInning": 1}] * 17,
            RuleSnapshotFailure.SHAPE,
        ),
        ("dh", 1, RuleSnapshotFailure.SHAPE),
    ],
)
def test_rule_snapshot_rejects_invalid_uuid_types_and_ranges(
    key: str, value: object, expected_kind: RuleSnapshotFailure
) -> None:
    """ID正規形・型・値域の違反を既存schemaで拒否する。"""
    raw = _valid_applied_rules()
    raw[key] = value

    with pytest.raises(RuleSnapshotInvalid) as caught:
        decode_structure(raw)
    assert caught.value.kind is expected_kind
    assert _RULE_SET_ID not in str(caught.value)
    assert caught.value.__cause__ is None


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("runnerPlacement", "no_out_second"),
        ("leadoffRule", "restart_lineup"),
    ],
)
def test_rule_snapshot_rejects_unapproved_tiebreak_literals(
    key: str, value: str
) -> None:
    """採用済みのタイブレーク機械文字列以外を受理しない。"""
    raw = _valid_applied_rules()
    raw["tiebreak"][key] = value

    with pytest.raises(RuleSnapshotInvalid) as caught:
        decode_structure(raw)
    assert caught.value.kind is RuleSnapshotFailure.VALUE
    assert caught.value.__cause__ is None


def test_rule_snapshot_error_does_not_chain_untrusted_uuid() -> None:
    """不正UUIDを公開例外文や例外連鎖へ残さない。"""
    raw = _valid_applied_rules()
    raw["ruleSetId"] = "private-invalid-rule-id"

    with pytest.raises(RuleSnapshotInvalid) as caught:
        decode_structure(raw)
    assert "private-invalid-rule-id" not in str(caught.value)
    assert caught.value.__cause__ is None


def test_rule_snapshot_structure_cannot_be_encoded_as_validated() -> None:
    """構造検証だけではドメイン検証済みの保存形へ進めない。"""
    structural = decode_structure(_valid_applied_rules())

    with pytest.raises(TypeError, match="相関検証済み"):
        encode_applied_rules(cast(Any, structural))
    validated = validate_correlations(structural)
    assert isinstance(validated, DomainValidatedRuleSnapshot)
    assert encode_applied_rules(validated) == _valid_applied_rules()


def test_rule_snapshot_direct_validated_construction_checks_structure() -> None:
    """不変型の迂回変更からも検証済み値を作れない。"""
    structural = decode_structure(_valid_applied_rules())
    object.__setattr__(structural, "regulation_innings", 0)

    with pytest.raises(RuleSnapshotInvalid):
        DomainValidatedRuleSnapshot(structural)


def test_rule_snapshot_direct_validated_construction_checks_correlation() -> None:
    """公開型の直接生成でも相関違反を検証済みへ昇格しない。"""
    structural = decode_structure(_valid_applied_rules())
    object.__setattr__(structural, "extension_limit", 8)

    with pytest.raises(RuleSnapshotInvalid) as caught:
        DomainValidatedRuleSnapshot(structural)
    assert caught.value.kind is RuleSnapshotFailure.CORRELATION


@pytest.mark.parametrize(
    ("extension_limit", "tiebreak_start"),
    [(8, 10), (12, 9), (12, 13)],
    ids=("DRAW-01", "DRAW-03-regulation", "DRAW-03-limit"),
)
def test_rule_snapshot_single_correlation_path_rejects_invalid(
    extension_limit: int, tiebreak_start: int
) -> None:
    """凍結schemaが表せない付録F-1の相関違反を拒否する。"""
    raw = _valid_applied_rules()
    raw["extensionLimit"] = extension_limit
    raw["tiebreak"]["startInning"] = tiebreak_start
    structural = decode_structure(raw)

    with pytest.raises(RuleSnapshotInvalid) as caught:
        validate_correlations(structural)
    assert caught.value.kind is RuleSnapshotFailure.CORRELATION
    with pytest.raises(RuleSnapshotInvalid):
        decode_applied_rules(raw)


def test_rule_snapshot_cold_conflict_stays_unresolved_and_fails_closed() -> None:
    """FR-014とDRAW-04の未裁定例を有効として保存しない。"""
    raw = _valid_applied_rules()
    raw["coldConditions"] = [{"pointDifference": 1, "startInning": 10}]
    structural = decode_structure(raw)

    with pytest.raises(RuleSnapshotInvalid) as caught:
        validate_correlations(structural)
    assert caught.value.kind is RuleSnapshotFailure.UNRESOLVED
    with pytest.raises(TypeError):
        encode_applied_rules(cast(Any, structural))


def test_rule_snapshot_missing_frozen_contract_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """凍結schemaが読めないとき値を検証済みに昇格しない。"""
    rule_snapshot._validator.cache_clear()
    monkeypatch.setattr(rule_snapshot, "_CONTRACT_PATH", tmp_path / "missing.json")
    try:
        with pytest.raises(RuleSnapshotContractUnavailable):
            decode_structure(_valid_applied_rules())
    finally:
        rule_snapshot._validator.cache_clear()


def test_rule_snapshot_accepts_cold_tiers_within_regulation() -> None:
    """F-2のコールド段と延長なしを受理する。"""
    raw = _valid_applied_rules()
    raw["coldConditions"] = [
        {"pointDifference": 10, "startInning": 5},
        {"pointDifference": 7, "startInning": 7},
    ]
    raw["extensionLimit"] = 9
    raw["tiebreak"] = None

    assert encode_applied_rules(decode_applied_rules(raw)) == raw
    changed = deepcopy(raw)
    changed["coldConditions"][0]["pointDifference"] = 0
    with pytest.raises(RuleSnapshotInvalid):
        decode_applied_rules(changed)


def test_rule_snapshot_encoded_value_does_not_mutate_validated_snapshot() -> None:
    """encode結果の入れ子を変更しても検証済み値を変更しない。"""
    validated = decode_applied_rules(_valid_applied_rules())
    encoded = encode_applied_rules(validated)
    cast(dict[str, object], encoded["tiebreak"])["startInning"] = 11

    assert validated.structural.tiebreak is not None
    assert validated.structural.tiebreak.start_inning == 10
