"""ランタイム認可契約の宣言検査と生成モジュールの描画を提供する。"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

RUNTIME_CONTRACT_ASSET = Path("contracts/tenant_boundary/runtime-authz-contract.json")
GENERATED_MODULE = Path("backend/src/pitchlog/authz/runtime_contract.py")

_EXPECTED_ROLE_NAME = "pitchlog_app"
_EXPECTED_ASSET_KIND = "tenant_boundary_runtime_authz_contract"
_EXPECTED_CANONICALIZATION = "json-sort-keys-utf8-v1"
_EXPECTED_DANGEROUS_FIXTURES = {
    ("superuser", "DANGER_SUPERUSER"),
    ("bypassrls", "DANGER_BYPASSRLS"),
    ("schema_owner", "DANGER_SCHEMA_OWNER"),
    ("table_owner", "DANGER_TABLE_OWNER"),
    ("function_owner", "DANGER_FUNCTION_OWNER"),
}
_ROLE_ATTRIBUTE_NAMES = (
    "rolsuper",
    "rolbypassrls",
    "rolcanlogin",
    "rolcreaterole",
    "rolcreatedb",
    "rolreplication",
    "rolinherit",
)

JsonObject = dict[str, object]


class RuntimeContractError(ValueError):
    """ランタイム契約の資産を描画できない場合の例外。"""


def read_json_object(path: Path) -> JsonObject:
    """JSON object を読み込む。

    Args:
        path: 読み込むファイル。

    Returns:
        文字列キーを持つ JSON object。

    Raises:
        RuntimeContractError: ファイルの内容が JSON object でない場合。
    """
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise RuntimeContractError(f"JSON object ではありません: {path}")
    return cast(JsonObject, value)


def asset_digest(asset: Mapping[str, object]) -> str:
    """資産自身の digest 欄を除いて正規化 digest を計算する。

    Args:
        asset: ランタイム契約の資産。

    Returns:
        SHA-256 の十六進表現。
    """
    payload = dict(asset)
    payload.pop("source_digest", None)
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def declaration_violations(asset: Mapping[str, object] | None) -> set[str]:
    """全状態に共通する宣言 D1〜D5 の違反 ID を返す。

    Args:
        asset: ランタイム契約の資産。資産が無い場合は ``None``。

    Returns:
        違反 ID の集合。
    """
    if asset is None:
        return {"PROVISIONAL_ASSET_MISSING"}

    violations: set[str] = set()
    application_role = _mapping(asset.get("application_role"))
    if application_role is None or application_role.get("rolname") != (
        _EXPECTED_ROLE_NAME
    ):
        violations.add("DECLARED_ROLE_NAME_MISMATCH")

    schema_version = asset.get("schema_version")
    if (
        not isinstance(schema_version, int)
        or isinstance(schema_version, bool)
        or schema_version != 1
        or asset.get("asset_kind") != _EXPECTED_ASSET_KIND
        or asset.get("canonicalization") != _EXPECTED_CANONICALIZATION
    ):
        violations.add("DECLARED_VALUE_MISMATCH")

    fixtures = _dangerous_fixture_rows(asset.get("dangerous_endpoint_fixtures"))
    if (
        fixtures is None
        or len(fixtures) != len(_EXPECTED_DANGEROUS_FIXTURES)
        or set(fixtures) != _EXPECTED_DANGEROUS_FIXTURES
    ):
        violations.add("DANGEROUS_FIXTURES_MISMATCH")

    revision = asset.get("runtime_contract_revision")
    baseline_control = _mapping(asset.get("baseline_control"))
    identity = (
        _mapping(baseline_control.get("identity"))
        if baseline_control is not None
        else None
    )
    expected_identifiers = [f"runtime_contract_revision:{revision}"]
    if identity is None or identity.get("current_identifiers") != (
        expected_identifiers
    ):
        violations.add("IDENTIFIER_MISMATCH")

    if asset.get("source_digest") != asset_digest(asset):
        violations.add("SOURCE_DIGEST_STALE")
    return violations


def runtime_contract_violations(
    asset: Mapping[str, object] | None,
    generated_module_source: str | None,
) -> set[str]:
    """宣言と生成モジュールの違反 ID を返す。

    Args:
        asset: ランタイム契約の資産。資産が無い場合は ``None``。
        generated_module_source: 現在の生成モジュール。無い場合は ``None``。

    Returns:
        違反 ID の集合。
    """
    violations = declaration_violations(asset)
    if asset is None:
        return violations

    try:
        expected_source = render_runtime_contract(asset)
    except RuntimeContractError:
        violations.add("GENERATED_MODULE_STALE")
        return violations
    if generated_module_source != expected_source:
        violations.add("GENERATED_MODULE_STALE")
    return violations


def render_runtime_contract(asset: Mapping[str, object]) -> str:
    """資産からランタイム契約モジュールのソース文字列を描画する。

    一覧は資産に記録された順序を保つ。ステップ 1 の暫定状態では
    ``DERIVED_FROM`` は常に ``None`` とする。

    Args:
        asset: ランタイム契約の資産。

    Returns:
        UTF-8 で保存する生成モジュールのソース文字列。

    Raises:
        RuntimeContractError: 描画対象の値が期待する型でない場合。
    """
    schema_version = _integer(asset, "schema_version")
    revision = _integer(asset, "runtime_contract_revision")
    provisional = _boolean(asset, "provisional")
    superseded_by = _optional_string(asset.get("superseded_by"), "superseded_by")
    source_digest = _string(asset, "source_digest")

    application_role = _required_mapping(asset, "application_role")
    role_name = _string(application_role, "rolname")
    attributes = _required_mapping(application_role, "attributes")
    attribute_values = {
        name: _boolean(attributes, name) for name in _ROLE_ATTRIBUTE_NAMES
    }

    protected_objects = _required_mapping(asset, "protected_objects")
    schemas = _string_rows(protected_objects, "schemas")
    tables = _identifier_rows(protected_objects, "tables", width=2)
    functions = _identifier_rows(protected_objects, "functions", width=3)
    fixtures = _fixture_rows_for_render(asset)

    lines = [
        '"""テナント境界のランタイム認可契約を提供する生成モジュール。"""',
        "",
        "from dataclasses import dataclass",
        "",
        f"SCHEMA_VERSION = {schema_version}",
        f"RUNTIME_CONTRACT_REVISION = {revision}",
        f"PROVISIONAL = {provisional!r}",
        f"SUPERSEDED_BY = {_python_string_or_none(superseded_by)}",
        f'SOURCE_ASSET = "{RUNTIME_CONTRACT_ASSET.as_posix()}"',
        f"SOURCE_DIGEST = {_python_string(source_digest)}",
        "DERIVED_FROM = None",
        "",
        "",
        "@dataclass(frozen=True, slots=True)",
        "class ApplicationRoleAttributes:",
        '    """PostgreSQL アプリ用ロールの期待属性を保持する。"""',
        "",
    ]
    lines.extend(f"    {name}: bool" for name in _ROLE_ATTRIBUTE_NAMES)
    lines.extend(
        [
            "",
            "",
            f"APPLICATION_ROLE_NAME = {_python_string(role_name)}",
            "APPLICATION_ROLE_ATTRIBUTES = ApplicationRoleAttributes(",
        ]
    )
    lines.extend(
        f"    {name}={attribute_values[name]!r}," for name in _ROLE_ATTRIBUTE_NAMES
    )
    lines.extend(
        [
            ")",
            "",
            f"PROTECTED_SCHEMAS = {_render_string_tuple(schemas)}",
            "PROTECTED_TABLES = (",
        ]
    )
    lines.extend(f"    {_render_row(row)}," for row in tables)
    lines.extend([")", "PROTECTED_FUNCTIONS = ("])
    lines.extend(f"    {_render_row(row)}," for row in functions)
    lines.extend([")", "", "DANGEROUS_ENDPOINT_FIXTURES = ("])
    lines.extend(f"    {_render_row(row)}," for row in fixtures)
    lines.extend([")", ""])
    return "\n".join(lines)


def _mapping(value: object) -> Mapping[str, object] | None:
    """文字列キーの mapping なら値を返す。"""
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        return None
    return cast(Mapping[str, object], value)


def _required_mapping(value: Mapping[str, object], key: str) -> Mapping[str, object]:
    """必須の mapping を返す。"""
    result = _mapping(value.get(key))
    if result is None:
        raise RuntimeContractError(f"{key} は JSON object でなければなりません")
    return result


def _string(value: Mapping[str, object], key: str) -> str:
    """必須の文字列を返す。"""
    result = value.get(key)
    if not isinstance(result, str):
        raise RuntimeContractError(f"{key} は文字列でなければなりません")
    return result


def _optional_string(value: object, name: str) -> str | None:
    """文字列または ``None`` を返す。"""
    if value is not None and not isinstance(value, str):
        raise RuntimeContractError(f"{name} は文字列か null でなければなりません")
    return value


def _boolean(value: Mapping[str, object], key: str) -> bool:
    """必須の真偽値を返す。"""
    result = value.get(key)
    if not isinstance(result, bool):
        raise RuntimeContractError(f"{key} は真偽値でなければなりません")
    return result


def _integer(value: Mapping[str, object], key: str) -> int:
    """必須の整数を返す。"""
    result = value.get(key)
    if not isinstance(result, int) or isinstance(result, bool):
        raise RuntimeContractError(f"{key} は整数でなければなりません")
    return result


def _sequence(value: object) -> Sequence[object] | None:
    """文字列以外の sequence なら値を返す。"""
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return cast(Sequence[object], value)
    return None


def _string_rows(value: Mapping[str, object], key: str) -> list[str]:
    """文字列の配列を返す。"""
    rows = _sequence(value.get(key))
    if rows is None or not all(isinstance(row, str) for row in rows):
        raise RuntimeContractError(f"{key} は文字列の配列でなければなりません")
    return cast(list[str], list(rows))


def _identifier_rows(
    value: Mapping[str, object], key: str, *, width: int
) -> list[tuple[str, ...]]:
    """固定長の物理識別子配列を返す。"""
    values = _sequence(value.get(key))
    if values is None:
        raise RuntimeContractError(f"{key} は配列でなければなりません")
    result: list[tuple[str, ...]] = []
    for value_row in values:
        row = _sequence(value_row)
        if (
            row is None
            or len(row) != width
            or not all(isinstance(cell, str) for cell in row)
        ):
            raise RuntimeContractError(
                f"{key} の各要素は {width} 個の文字列でなければなりません"
            )
        result.append(tuple(cast(Sequence[str], row)))
    return result


def _dangerous_fixture_rows(value: object) -> list[tuple[str, str]] | None:
    """危険終点 fixture の行を比較可能な形で返す。"""
    values = _sequence(value)
    if values is None:
        return None
    result: list[tuple[str, str]] = []
    for value_row in values:
        row = _mapping(value_row)
        if row is None:
            return None
        category = row.get("category")
        fixture_id = row.get("fixture_id")
        if not isinstance(category, str) or not isinstance(fixture_id, str):
            return None
        result.append((category, fixture_id))
    return result


def _fixture_rows_for_render(
    asset: Mapping[str, object],
) -> list[tuple[str, str]]:
    """描画用の危険終点 fixture 行を返す。"""
    rows = _dangerous_fixture_rows(asset.get("dangerous_endpoint_fixtures"))
    if rows is None:
        raise RuntimeContractError(
            "dangerous_endpoint_fixtures は category と fixture_id を持つ配列で"
            "なければなりません"
        )
    return rows


def _python_string(value: str) -> str:
    """Python の二重引用符文字列を返す。"""
    return json.dumps(value, ensure_ascii=False)


def _python_string_or_none(value: str | None) -> str:
    """Python の文字列または ``None`` を返す。"""
    return "None" if value is None else _python_string(value)


def _render_row(row: tuple[str, ...]) -> str:
    """文字列 tuple の 1 行を描画する。"""
    return f"({', '.join(_python_string(value) for value in row)})"


def _render_string_tuple(values: list[str]) -> str:
    """文字列 tuple を 1 行で描画する。"""
    body = ", ".join(_python_string(value) for value in values)
    if len(values) == 1:
        body += ","
    return f"({body})"
