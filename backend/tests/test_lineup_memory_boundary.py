"""スタメン記憶のロックと JSONB 結果の境界を検証する。"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, cast
from uuid import uuid4

import pytest
from sqlalchemy import bindparam, select
from sqlalchemy.sql.selectable import Select

from pitchlog.authz.capability_catalog import (
    CATALOG_SCHEMA_VERSION,
    CLASSIFICATION_SOURCE,
)
from pitchlog.authz.capability_registration import (
    CapabilityRegistrationError,
    validate_capability_registrations,
)
from pitchlog.db.tenant_isolation.models import Player, TeamRecord
from pitchlog.repositories.base import (
    _materialize_value,
    _operation_spec,
    _TenantOperationError,
    _validate_prepared_statement,
)
from pitchlog.repositories.lineup_memory import (
    _ActiveLineupPlayerLockToken,
    _build_lineup_memory_statement,
)


@dataclass(frozen=True)
class _Registration:
    """検証対象の読み取り登録。"""

    capability_id: str
    statement: Select[Any]


def _locked_team() -> Select[Any]:
    """対象 self チーム 1 行だけの登録文を作る。"""
    table = TeamRecord.__table__
    return (
        select(table.c.id)
        .where(table.c.tenant_id == bindparam("tenant_id"))
        .where(table.c.id == bindparam("team_record_id"))
        .where(table.c.kind == bindparam("kind"))
        .where(table.c.hidden_at.is_(None))
        .with_for_update()
    )


def _locked_player() -> Select[Any]:
    """現役選手 1 行だけの登録文を作る。"""
    return cast(Select[Any], _build_lineup_memory_statement("player_lock"))


def _validate(
    statement: Select[Any], capability_id: str = "CAP:team_records:read"
) -> None:
    """1 件の登録を製品カタログと同じ書式で検査する。"""
    table_id = capability_id.split(":")[1]
    validate_capability_registrations(
        catalog={
            "schema_version": CATALOG_SCHEMA_VERSION,
            "source_classification": CLASSIFICATION_SOURCE,
            "capabilities": [
                {
                    "capability_id": capability_id,
                    "table_id": table_id,
                    "operation": "read",
                }
            ],
        },
        registrations=(_Registration(capability_id, statement),),
    )


def test_self_team_single_row_lock_is_accepted() -> None:
    """対象チームへの通常の FOR UPDATE を許可する。"""
    _validate(_locked_team())


def test_active_player_single_row_lock_is_accepted() -> None:
    """限定した現役選手の通常 FOR UPDATE だけを許可する。"""
    _validate(_locked_player(), "CAP:players:read")


@pytest.mark.parametrize(
    "statement",
    [
        _locked_player().with_for_update(nowait=True),
        _locked_player().with_for_update(read=True),
        _locked_player().with_for_update(skip_locked=True),
        _locked_player().with_for_update(key_share=True),
        _locked_player().where(Player.__table__.c.id == bindparam("another_id")),
        select(Player.__table__.c.id)
        .where(Player.__table__.c.tenant_id == bindparam("tenant_id"))
        .where(Player.__table__.c.id == bindparam("player_id"))
        .where(Player.__table__.c.roster_status_key == bindparam("roster_status_key"))
        .where(Player.__table__.c.hidden_at.is_(None))
        .with_for_update(),
        _locked_team(),
    ],
)
def test_other_player_lock_shapes_are_rejected(statement: Select[Any]) -> None:
    """選手ロックの条件欠落・変種・別表を拒否する。"""
    with pytest.raises(CapabilityRegistrationError):
        _validate(statement, "CAP:players:read")


def test_active_player_lock_rejects_wrong_fixed_binding() -> None:
    """現役以外へのロックを登録済み token の実行境界でも拒否する。"""
    token = _ActiveLineupPlayerLockToken(uuid4(), uuid4())
    spec = _operation_spec(token)
    statement, parameters = spec.prepare(token)
    parameters["tenant_id"] = uuid4()
    parameters["roster_status_key"] = "ob"
    with pytest.raises(_TenantOperationError, match="束縛値が不正"):
        _validate_prepared_statement(spec, statement, parameters)


@pytest.mark.parametrize("missing", ("tenant", "player", "team", "active", "visible"))
def test_player_lock_rejects_each_missing_row_boundary(missing: str) -> None:
    """テナント・選手・チーム・現役・非表示条件の欠落を拒否する。"""
    table = Player.__table__
    clauses = {
        "tenant": table.c.tenant_id == bindparam("tenant_id"),
        "player": table.c.id == bindparam("player_id"),
        "team": table.c.team_record_id == bindparam("team_record_id"),
        "active": table.c.roster_status_key == bindparam("roster_status_key"),
        "visible": table.c.hidden_at.is_(None),
    }
    statement = (
        select(table.c.id)
        .where(*(clause for name, clause in clauses.items() if name != missing))
        .with_for_update()
    )
    with pytest.raises(CapabilityRegistrationError):
        _validate(statement, "CAP:players:read")


def test_lineup_memory_builder_rejects_unknown_kind() -> None:
    """登録外の操作種別では SQL 文を構築しない。"""
    with pytest.raises(ValueError, match="未知のスタメン記憶操作"):
        _build_lineup_memory_statement("delete")


@pytest.mark.parametrize(
    "statement",
    [
        _locked_team().with_for_update(nowait=True),
        _locked_team().with_for_update(read=True),
        _locked_team().with_for_update(skip_locked=True),
        _locked_team().with_for_update(key_share=True),
        _locked_team().where(TeamRecord.__table__.c.id == bindparam("another_id")),
        select(Player.__table__.c.id).with_for_update(),
        select(TeamRecord.__table__.c.id)
        .where(TeamRecord.__table__.c.tenant_id == bindparam("tenant_id"))
        .with_for_update(),
    ],
)
def test_other_lock_shapes_are_rejected(statement: Select[Any]) -> None:
    """別表・対象 bind 欠落・ロック変種を拒否する。"""
    with pytest.raises(CapabilityRegistrationError):
        _validate(statement)


def test_jsonb_results_are_deeply_immutable() -> None:
    """入れ子の配列と辞書を不変値へ閉じる。"""
    source: list[dict[str, object]] = [{"slots": [{"order": 1}]}]
    value = _materialize_value(source)
    assert isinstance(value, tuple)
    assert isinstance(value[0], MappingProxyType)
    assert isinstance(value[0]["slots"], tuple)
    source[0]["slots"] = []
    assert value[0]["slots"] == (MappingProxyType({"order": 1}),)
    with pytest.raises(TypeError):
        cast(Any, value[0]["slots"][0])["order"] = 2


@pytest.mark.parametrize("source", [{1: "bad"}, {"slot": set()}])
def test_unknown_jsonb_values_are_rejected(source: object) -> None:
    """非文字列キーと未知の可変型を拒否する。"""
    with pytest.raises(_TenantOperationError):
        _materialize_value(source)
