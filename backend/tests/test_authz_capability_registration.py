"""Capability 登録の ID・表・操作・SQLAlchemy 式木を検査する。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import (
    and_,
    bindparam,
    delete,
    desc,
    func,
    insert,
    literal_column,
    select,
    true,
    update,
)
from sqlalchemy.sql.elements import ClauseElement
from sqlalchemy.sql.schema import Table
from sqlalchemy.sql.selectable import CTE

from pitchlog.authz.capability_registration import (
    CapabilityRegistrationError,
    validate_capability_registrations,
)
from pitchlog.authz.classification import load_json_object
from pitchlog.db import all_models
from pitchlog.db.base import Base
from pitchlog.repositories import base as repository_base
from pitchlog.repositories import repository_contract

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_CATALOG_PATH = (
    _REPOSITORY_ROOT / "contracts" / "authz" / "product" / "capability-catalog.json"
)


@dataclass(frozen=True, slots=True)
class _Registration:
    """試験内だけで使う仮の capability 登録。"""

    capability_id: str
    statement: ClauseElement


@pytest.fixture(scope="module")
def catalog() -> dict[str, Any]:
    """検査対象の capability カタログを読み込む。"""
    return load_json_object(_CATALOG_PATH)


@pytest.fixture(scope="module")
def tables() -> tuple[Table, Table]:
    """モデル登録済み metadata から直接表と未宣言表を返す。"""
    assert all_models.IMPORTED_MODEL_MODULE_NAMES
    return Base.metadata.tables["games"], Base.metadata.tables["players"]


def _read_statement(games: Table) -> ClauseElement:
    return (
        select(
            games.c.id,
            func.pg_catalog.lower(games.c.game_number_label).label("game_number"),
        )
        .where(
            and_(
                games.c.tenant_id == bindparam("tenant_id"),
                games.c.status != bindparam("excluded_status"),
            )
        )
        .order_by(desc(games.c.id))
        .limit(100)
    )


def _valid_registrations(games: Table) -> tuple[_Registration, ...]:
    return (
        _Registration("CAP:games:read", _read_statement(games)),
        _Registration(
            "CAP:games:insert",
            insert(games).values(
                id=bindparam("game_id"),
                tenant_id=bindparam("tenant_id"),
            ),
        ),
        _Registration(
            "CAP:games:update",
            update(games)
            .where(
                and_(
                    games.c.id == bindparam("game_id"),
                    games.c.tenant_id == bindparam("tenant_id"),
                )
            )
            .values(status=bindparam("status")),
        ),
    )


def _assert_mutation_rejected(
    catalog: dict[str, Any],
    games: Table,
    registrations: tuple[_Registration, ...],
) -> CapabilityRegistrationError:
    """改変前の green を表明してから登録変異の拒否を確かめる。"""
    validate_capability_registrations(
        catalog=catalog,
        registrations=_valid_registrations(games),
    )
    with pytest.raises(CapabilityRegistrationError) as caught:
        validate_capability_registrations(
            catalog=catalog,
            registrations=registrations,
        )
    return caught.value


def _unknown_id(games: Table, _players: Table) -> tuple[_Registration, ...]:
    return (_Registration("CAP:not_cataloged:read", _read_statement(games)),)


def _different_table(_games: Table, players: Table) -> tuple[_Registration, ...]:
    return (_Registration("CAP:games:read", select(players.c.id)),)


def _different_operation(games: Table, _players: Table) -> tuple[_Registration, ...]:
    return (
        _Registration(
            "CAP:games:read",
            insert(games).values(id=bindparam("game_id")),
        ),
    )


def _undeclared_join(games: Table, players: Table) -> tuple[_Registration, ...]:
    statement = select(games.c.id).select_from(
        games.join(players, players.c.id == games.c.home_team_record_id)
    )
    return (_Registration("CAP:games:read", statement),)


def _undeclared_subquery(
    games: Table,
    players: Table,
) -> tuple[_Registration, ...]:
    player_id = select(players.c.id).where(
        players.c.tenant_id == bindparam("tenant_id")
    )
    statement = select(games.c.id).where(
        games.c.home_team_record_id == player_id.scalar_subquery()
    )
    return (_Registration("CAP:games:read", statement),)


def _duplicate_id(games: Table, _players: Table) -> tuple[_Registration, ...]:
    registration = _Registration("CAP:games:read", _read_statement(games))
    return registration, registration


_BINDING_MUTATIONS = (
    pytest.param(_unknown_id, id="unknown-capability-id"),
    pytest.param(_different_table, id="different-table"),
    pytest.param(_different_operation, id="different-operation"),
    pytest.param(_undeclared_join, id="undeclared-join"),
    pytest.param(_undeclared_subquery, id="undeclared-subquery"),
    pytest.param(_duplicate_id, id="duplicate-id"),
)


def test_valid_registrations_match_catalog(
    catalog: dict[str, Any],
    tables: tuple[Table, Table],
) -> None:
    """正しい ID は 1 表だけの同種コマンドへ登録できる。"""
    games, _players = tables

    validate_capability_registrations(
        catalog=catalog,
        registrations=_valid_registrations(games),
    )


@pytest.mark.parametrize("mutation", _BINDING_MUTATIONS)
def test_catalog_binding_mutation_is_rejected(
    catalog: dict[str, Any],
    tables: tuple[Table, Table],
    mutation: Callable[[Table, Table], tuple[_Registration, ...]],
) -> None:
    """未知・重複 ID と表・操作・再帰的な参照表の不一致を拒否する。"""
    games, players = tables

    _assert_mutation_rejected(catalog, games, mutation(games, players))


def test_user_defined_scalar_function_is_rejected(
    catalog: dict[str, Any],
    tables: tuple[Table, Table],
) -> None:
    """SELECT 句のユーザー定義スカラー関数を拒否する。"""
    games, _players = tables
    statement = select(
        games.c.id,
        func.authz_private.evil(games.c.id),
    )

    error = _assert_mutation_rejected(
        catalog,
        games,
        (_Registration("CAP:games:read", statement),),
    )

    assert any("許可されていない関数" in item for item in error.violations)


def test_user_defined_table_valued_function_is_rejected(
    catalog: dict[str, Any],
    tables: tuple[Table, Table],
) -> None:
    """FROM 句のユーザー定義テーブル関数を拒否する。"""
    games, _players = tables
    evil_rows = func.authz_private.evil().table_valued("value")
    statement = select(games.c.id).select_from(games.join(evil_rows, true()))

    error = _assert_mutation_rejected(
        catalog,
        games,
        (_Registration("CAP:games:read", statement),),
    )

    assert any("許可されていない関数" in item for item in error.violations)


def test_opaque_sql_fragment_is_rejected(
    catalog: dict[str, Any],
    tables: tuple[Table, Table],
) -> None:
    """Literal column に埋め込んだ不透明な SQL 断片を拒否する。"""
    games, _players = tables
    statement = select(
        games.c.id,
        literal_column("authz_private.evil()"),
    )

    error = _assert_mutation_rejected(
        catalog,
        games,
        (_Registration("CAP:games:read", statement),),
    )

    assert any("閉じた集合外" in item for item in error.violations)


def _insert_cte(games: Table) -> CTE:
    return insert(games).values(id=bindparam("side_effect_id")).cte("side_effect")


def _update_cte(games: Table) -> CTE:
    return (
        update(games)
        .where(games.c.id == bindparam("side_effect_id"))
        .values(status=bindparam("side_effect_status"))
        .cte("side_effect")
    )


def _delete_cte(games: Table) -> CTE:
    return (
        delete(games)
        .where(games.c.id == bindparam("side_effect_id"))
        .cte("side_effect")
    )


@pytest.mark.parametrize(
    "cte_factory",
    (
        pytest.param(_insert_cte, id="insert"),
        pytest.param(_update_cte, id="update"),
        pytest.param(_delete_cte, id="delete"),
    ),
)
def test_unreferenced_dml_cte_is_rejected(
    catalog: dict[str, Any],
    tables: tuple[Table, Table],
    cte_factory: Callable[[Table], CTE],
) -> None:
    """読み取り文へ add_cte した未参照の DML CTE を再帰的に拒否する。"""
    games, _players = tables
    statement = select(games.c.id).add_cte(cte_factory(games))

    error = _assert_mutation_rejected(
        catalog,
        games,
        (_Registration("CAP:games:read", statement),),
    )

    assert any("DMLのCTE" in item for item in error.violations)


def test_product_registries_remain_empty() -> None:
    """本ステップでは製品の capability と operation を登録しない。"""
    assert repository_contract.PRODUCT_CAPABILITY_IDS == ()
    assert repository_contract.PRODUCT_OPERATION_TOKEN_TYPES == ()
    assert repository_contract.CROSS_TENANT_FUNCTIONS == ()
    assert repository_base._OPERATION_REGISTRY == {}
