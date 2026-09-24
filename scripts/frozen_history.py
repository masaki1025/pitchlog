"""凍結基準の版付き履歴を判別する。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


class ContractError(ValueError):
    """凍結履歴契約の不整合を表す。"""


@dataclass(frozen=True)
class HistoryRecord:
    """schema 版を確定した履歴 record を表す。

    Attributes:
        schema_version: record の schema 版。
        value: JSON から読んだ record の生の値。
    """

    schema_version: int
    value: Mapping[str, Any]


def parse_history(
    base_history: object,
    head_history: object,
    *,
    location: str = "baseline_control.history",
) -> tuple[HistoryRecord, ...]:
    """比較元 prefix を保護し、HEAD の履歴 record の版を確定する。

    比較元の履歴はその時点の信頼根として扱い、HEAD の同じ位置にある生 JSON
    値との同一性だけを検査する。比較元 prefix より後ろでは、明示的な v2
    record だけを受理する。v2 のフィールド検査はこの関数では行わない。

    Args:
        base_history: 比較元資産の history。
        head_history: HEAD 資産の history。
        location: エラー表示用の位置。

    Returns:
        schema 版を確定した HEAD の履歴 record。

    Raises:
        ContractError: 履歴が配列でない、prefix が一致しない、または追記 record
            が明示的な v2 でない場合。
    """
    base_records = _history_array(base_history, f"比較元.{location}")
    head_records = _history_array(head_history, f"HEAD.{location}")
    prefix_length = len(base_records)

    if len(head_records) < prefix_length or not _json_deep_equal(
        head_records[:prefix_length], base_records
    ):
        raise ContractError(f"{location}: 比較元の履歴 prefix は変更・削除できない")

    parsed: list[HistoryRecord] = []
    for index, raw_record in enumerate(head_records[:prefix_length]):
        record = _record_object(raw_record, f"{location}[{index}]")
        parsed.append(HistoryRecord(schema_version=1, value=record))

    for index, raw_record in enumerate(head_records[prefix_length:], start=prefix_length):
        record_location = f"{location}[{index}]"
        record = _record_object(raw_record, record_location)
        if "record_schema_version" not in record:
            raise ContractError(f"{record_location}: record_schema_version が必要")
        version = record["record_schema_version"]
        if type(version) is not int or version != 2:
            raise ContractError(
                f"{record_location}: prefix 以後は record_schema_version 2 が必要"
            )
        parsed.append(HistoryRecord(schema_version=2, value=record))

    return tuple(parsed)


def validate_history_authority(assets: Mapping[str, object]) -> str:
    """履歴 authority を宣言した資産がちょうど 1 件であることを検査する。

    Args:
        assets: 資産名から JSON object へのマップ。

    Returns:
        唯一の履歴 authority である資産名。

    Raises:
        ContractError: 資産構造または宣言が不正か、authority がちょうど 1 件で
            ない場合。
    """
    authorities: list[str] = []
    for asset_name, raw_asset in assets.items():
        asset = _mapping(raw_asset, asset_name)
        control = _mapping(asset.get("baseline_control"), f"{asset_name}.baseline_control")
        authority = control.get("history_authority")
        if type(authority) is not bool:
            raise ContractError(
                f"{asset_name}.baseline_control.history_authority: bool が必要"
            )
        if authority:
            authorities.append(asset_name)

    if len(authorities) != 1:
        raise ContractError(
            "history_authority: true の資産はちょうど 1 件必要: "
            f"actual={len(authorities)}"
        )
    return authorities[0]


def _history_array(value: object, location: str) -> list[object]:
    """履歴配列を取得する。"""
    if not isinstance(value, list):
        raise ContractError(f"{location}: 配列が必要")
    return value


def _record_object(value: object, location: str) -> Mapping[str, Any]:
    """履歴 record の JSON object を取得する。"""
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ContractError(f"{location}: 文字列キーの object が必要")
    return value


def _mapping(value: object, location: str) -> Mapping[str, Any]:
    """文字列キーのマップを取得する。"""
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ContractError(f"{location}: 文字列キーの object が必要")
    return value


def _json_deep_equal(left: object, right: object) -> bool:
    """object のキー順を無視し、配列の順序を保って JSON 値を比較する。"""
    if isinstance(left, dict) and isinstance(right, dict):
        if set(left) != set(right):
            return False
        return all(_json_deep_equal(left[key], right[key]) for key in left)
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            _json_deep_equal(left_item, right_item)
            for left_item, right_item in zip(left, right, strict=True)
        )
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return type(left) is type(right) and left == right
    return type(left) is type(right) and left == right
