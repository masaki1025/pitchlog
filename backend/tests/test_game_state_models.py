"""試合・スタメン・出場区間モデルを manifest と照合する。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict, cast
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
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

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_MANIFEST_PATH = _REPOSITORY_ROOT / "contracts" / "db" / "schema-manifest.json"
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


def _model_immutability(model: Any) -> dict[str, list[str]]:
    """モデルの不変列マトリクスを比較用に正規化する。"""
    return {
        "protected_columns": sorted(model.immutability.protected_columns),
        "allowed_update_columns": sorted(model.immutability.allowed_update_columns),
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
            key: sorted(value) for key, value in manifest["immutability"].items()
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
