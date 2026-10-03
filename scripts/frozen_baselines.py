"""凍結基準台帳の読み取りと識別値比較戦略を提供する。"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Final


class FrozenBaselineError(ValueError):
    """凍結基準の読み取りまたは素材解決に失敗したことを表す。"""


@dataclass(frozen=True, order=True)
class IdentityValue:
    """戦略が抽出した識別値を表す。"""

    kind: str
    value: str


ComparisonStrategy = Callable[
    [Mapping[str, bytes], Sequence[str]],
    tuple[IdentityValue, ...],
]


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """JSON object の重複キーを拒否して辞書へ変換する。"""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FrozenBaselineError(f"JSONキーが重複している: {key}")
        result[key] = value
    return result


def parse_frozen_baseline_ledger(data: bytes, source: str) -> dict[str, Any]:
    """凍結基準台帳の生bytesを重複キーを許さずパースする。

    Args:
        data: 台帳の生bytes。
        source: エラー表示に使う台帳の由来。

    Returns:
        パース済みのトップレベルオブジェクト。

    Raises:
        FrozenBaselineError: JSONが壊れているかトップレベルがobjectでない場合。
    """
    try:
        value = json.loads(
            data,
            object_pairs_hook=_object_without_duplicate_keys,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FrozenBaselineError(f"台帳JSONを解析できない: {source}: {exc}") from exc
    if not isinstance(value, dict):
        raise FrozenBaselineError(
            f"台帳のトップレベルはobjectでなければならない: {source}"
        )
    return value


def load_frozen_baseline_ledger(path: Path) -> dict[str, Any]:
    """凍結基準台帳ファイルを読み取ってパースする。

    Args:
        path: 読み取る台帳ファイル。

    Returns:
        パース済みのトップレベルオブジェクト。

    Raises:
        FrozenBaselineError: JSONが壊れているかトップレベルがobjectでない場合。
        OSError: 台帳を読み取れない場合。
    """
    return parse_frozen_baseline_ledger(path.read_bytes(), str(path))


def load_latest_series_identity(path: Path, series: str) -> tuple[IdentityValue, ...]:
    """台帳の系列履歴末尾から現在の識別値を読み取る。

    Args:
        path: 読み取る台帳ファイル。
        series: 読み取る系列名。

    Returns:
        履歴末尾の順序を保った識別値。

    Raises:
        FrozenBaselineError: 系列履歴または識別値の形が不正な場合。
        OSError: 台帳を読み取れない場合。
    """
    ledger = load_frozen_baseline_ledger(path)
    history = ledger.get("history")
    if not isinstance(history, list):
        raise FrozenBaselineError("台帳のhistoryがarrayでない")
    matching_records: list[dict[str, Any]] = []
    for index, record in enumerate(history):
        if not isinstance(record, dict):
            raise FrozenBaselineError(f"台帳のhistory[{index}]がobjectでない")
        if record.get("series") == series:
            matching_records.append(record)
    if not matching_records:
        raise FrozenBaselineError(f"台帳に系列履歴がない: {series}")

    new_identity = matching_records[-1].get("new_identity")
    if not isinstance(new_identity, dict) or set(new_identity) != {"present", "values"}:
        raise FrozenBaselineError(f"系列のnew_identityの形が不正: {series}")
    values = new_identity["values"]
    if new_identity["present"] is not True or not isinstance(values, list) or not values:
        raise FrozenBaselineError(f"系列の現在識別値が存在しない: {series}")

    identities: list[IdentityValue] = []
    for index, raw_value in enumerate(values):
        if not isinstance(raw_value, dict) or set(raw_value) != {"kind", "value"}:
            raise FrozenBaselineError(
                f"系列のnew_identity.values[{index}]の形が不正: {series}"
            )
        kind = raw_value["kind"]
        value = raw_value["value"]
        if not isinstance(kind, str) or not isinstance(value, str):
            raise FrozenBaselineError(
                f"系列のnew_identity.values[{index}]が文字列でない: {series}"
            )
        identities.append(IdentityValue(kind=kind, value=value))
    if len(identities) != len(set(identities)):
        raise FrozenBaselineError(f"系列の現在識別値が重複している: {series}")
    return tuple(identities)


def _split_target(target: str) -> tuple[str, str]:
    """pointer付きlocatorをファイルパスとJSON pointerへ分割する。"""
    path, separator, pointer = target.partition("#")
    if not separator or not path or not pointer.startswith("/"):
        raise FrozenBaselineError(f"frozen_target の形式が不正: {target}")
    return path, pointer


def _safe_repository_path(root: Path, path_text: str) -> Path:
    """リポジトリ相対の純粋なファイルパスを検証して返す。"""
    pure_path = PurePosixPath(path_text)
    if pure_path.is_absolute() or ".." in pure_path.parts or "#" in path_text:
        raise FrozenBaselineError(f"素材パスがリポジトリ相対でない: {path_text}")
    return root.joinpath(*pure_path.parts)


def collect_materials(
    repository_root: Path,
    declared_targets: Sequence[str],
    requested_paths: Sequence[str],
) -> dict[str, bytes]:
    """宣言済みtargetのファイルパスだけから生bytesを収集する。

    Args:
        repository_root: 素材ファイルを解決するリポジトリルート。
        declared_targets: pointer付きの宣言済みtarget。
        requested_paths: 読み取る純粋なファイルパス。

    Returns:
        純粋なファイルパスをキーとする生bytesの写像。

    Raises:
        FrozenBaselineError: 宣言にないパスを要求した場合。
        OSError: 素材ファイルを読み取れない場合。
    """
    declared_paths = {_split_target(target)[0] for target in declared_targets}
    requested_set = set(requested_paths)
    undeclared_paths = sorted(requested_set - declared_paths)
    if undeclared_paths:
        raise FrozenBaselineError(f"宣言にない素材パスは読めない: {undeclared_paths!r}")
    if len(requested_paths) != len(requested_set):
        raise FrozenBaselineError("素材パスが重複している")
    return {
        path_text: _safe_repository_path(repository_root, path_text).read_bytes()
        for path_text in requested_paths
    }


def _decode_pointer_token(token: str) -> str:
    """RFC 6901のエスケープを検証しながら復号する。"""
    result: list[str] = []
    index = 0
    while index < len(token):
        character = token[index]
        if character != "~":
            result.append(character)
            index += 1
            continue
        if index + 1 >= len(token) or token[index + 1] not in {"0", "1"}:
            raise FrozenBaselineError(f"JSON pointer のescapeが不正: {token}")
        result.append("~" if token[index + 1] == "0" else "/")
        index += 2
    return "".join(result)


def _resolve_json_pointer(document: Any, pointer: str, target: str) -> Any:
    """JSON documentからRFC 6901 pointerの値を解決する。"""
    current = document
    for encoded_token in pointer.removeprefix("/").split("/"):
        token = _decode_pointer_token(encoded_token)
        if isinstance(current, dict):
            if token not in current:
                raise FrozenBaselineError(f"JSON pointer のキーが存在しない: {target}")
            current = current[token]
        elif isinstance(current, list):
            if not token.isdecimal():
                raise FrozenBaselineError(f"JSON pointer の配列indexが不正: {target}")
            array_index = int(token)
            if array_index >= len(current):
                raise FrozenBaselineError(f"JSON pointer の配列indexが範囲外: {target}")
            current = current[array_index]
        else:
            raise FrozenBaselineError(f"JSON pointer の途中がcontainerでない: {target}")
    return current


def literal_commit_string_at_json_pointer(
    materials: Mapping[str, bytes],
    targets: Sequence[str],
) -> tuple[IdentityValue, ...]:
    """素材JSONの各pointerからcommit文字列を順番どおり抽出する。

    Args:
        materials: 純粋なファイルパスから生bytesへの写像。
        targets: pointer付きlocator文字列。

    Returns:
        target順の識別値。

    Raises:
        FrozenBaselineError: 素材不足、JSON破損、pointer不正、値型不正の場合。
    """
    documents: dict[str, Any] = {}
    values: list[IdentityValue] = []
    for target in targets:
        path_text, pointer = _split_target(target)
        if path_text not in materials:
            raise FrozenBaselineError(f"戦略に必要な素材がない: {path_text}")
        if path_text not in documents:
            try:
                documents[path_text] = json.loads(materials[path_text])
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise FrozenBaselineError(f"素材JSONを解析できない: {path_text}: {exc}") from exc
        value = _resolve_json_pointer(documents[path_text], pointer, target)
        if not isinstance(value, str):
            raise FrozenBaselineError(f"識別値が文字列でない: {target}")
        values.append(IdentityValue(kind="literal_commit_string", value=value))
    return tuple(values)


COMPARISON_STRATEGIES: Final[dict[tuple[str, str], ComparisonStrategy]] = {
    ("literal_commit_string", "json_pointer_value"): (
        literal_commit_string_at_json_pointer
    ),
}
