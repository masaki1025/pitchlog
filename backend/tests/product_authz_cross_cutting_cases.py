"""製品認可の横断 DB 試験に使う migration 由来のケースを組み立てる。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from product_authz_other_profiles_cases import other_profile_seed_rows
from product_authz_tenant_owned_cases import _migration_trigger_facts

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_DDL_ELEMENTS_PATH = (
    _REPOSITORY_ROOT / "contracts/authz/product/ddl-elements.staged.json"
)


@dataclass(frozen=True, slots=True)
class TriggerExpectation:
    """migration トリガ関数が拒否するときの識別可能な期待値。"""

    function_name: str
    sqlstate: str
    message: str


def _load_object(path: Path) -> dict[str, Any]:
    """JSON 資産を object として読む。"""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError(f"JSON 資産の root が object でない: {path}")
    return value


def _asset_trigger_function_names() -> frozenset[str]:
    """Staged 資産が宣言する migration トリガ関数名を返す。"""
    raw_functions = _load_object(_DDL_ELEMENTS_PATH).get("functions")
    if not isinstance(raw_functions, list):
        raise AssertionError("ddl-elements.functions は配列が必要")
    result: set[str] = set()
    for function in raw_functions:
        if not isinstance(function, dict):
            raise AssertionError("ddl-elements.functions の要素が不正")
        if function.get("function_kind") != "migration_trigger":
            continue
        function_name = function.get("function_name")
        if not isinstance(function_name, str) or not function_name:
            raise AssertionError("migration トリガ関数名が不正")
        if function_name in result:
            raise AssertionError(f"migration トリガ関数名が重複: {function_name}")
        result.add(function_name)
    return frozenset(result)


def trigger_expectations() -> tuple[TriggerExpectation, ...]:
    """資産と migration が一致する全トリガ関数の拒否期待値を返す。"""
    migration_functions, migration_triggers = _migration_trigger_facts()
    asset_names = _asset_trigger_function_names()
    attached_names = [trigger.function_name for trigger in migration_triggers.values()]
    if len(asset_names) != 37:
        raise AssertionError(
            f"staged 資産のトリガ関数が 37 個でない: {len(asset_names)}"
        )
    if len(attached_names) != len(set(attached_names)):
        raise AssertionError("1 個の migration トリガ関数が複数箇所に接続されている")
    if asset_names != set(attached_names):
        raise AssertionError(
            "staged 資産と migration の接続済みトリガ関数が一致しない: "
            f"asset_only={sorted(asset_names - set(attached_names))}, "
            f"migration_only={sorted(set(attached_names) - asset_names)}"
        )

    result: list[TriggerExpectation] = []
    for function_name in sorted(asset_names):
        function = migration_functions.get(function_name)
        if function is None:
            raise AssertionError(
                f"トリガ関数の RAISE EXCEPTION が migration に無い: {function_name}"
            )
        result.append(
            TriggerExpectation(
                function_name=function_name,
                sqlstate=function.sqlstate,
                message=function.message,
            )
        )
    return tuple(result)


def trigger_update_column(table: str, update_columns: tuple[str, ...]) -> str:
    """投入行で非 NULL の、トリガ対象 UPDATE 列を 1 個選ぶ。"""
    for row in other_profile_seed_rows():
        if row.table != table:
            continue
        for column, value in row.values.items():
            if column in update_columns and value is not None:
                return column
    raise AssertionError(
        f"トリガを発火できる非 NULL の投入値が無い: {table}/{update_columns}"
    )
