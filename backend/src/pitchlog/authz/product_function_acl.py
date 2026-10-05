"""migration由来の製品関数ACLを決定的に生成する。"""

from __future__ import annotations

import json
import re
from pathlib import Path

from pitchlog.authz.asset_spec import PRODUCT_SPEC

_IDENTIFIER_INITIALS = "abcdefghijklmnopqrstuvwxyz_"
_IDENTIFIER_CHARACTERS = f"{_IDENTIFIER_INITIALS}0123456789"
_ARGUMENT_TYPE = (
    r"[a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)?(?:\[\])?(?: [a-z_][a-z0-9_]*)*"
)
_IDENTITY_ARGS_RE = re.compile(rf"{_ARGUMENT_TYPE}(?:, {_ARGUMENT_TYPE})*\Z")
_REPOSITORY_ROOT = Path(__file__).parents[4]


def valid_product_identity_args(value: str) -> bool:
    """SQL に安全な型名だけからなる引数列を判定する。"""
    return value == "" or _IDENTITY_ARGS_RE.fullmatch(value) is not None


def _declared_identity_args() -> frozenset[str]:
    """製品関数の宣言から許可する引数の形を読む。"""
    path = _REPOSITORY_ROOT / PRODUCT_SPEC.ddl_elements_path
    try:
        asset = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("製品関数の宣言を読めない") from error
    if not isinstance(asset, dict) or not isinstance(asset.get("functions"), list):
        raise ValueError("製品関数の宣言が不正")
    rows = asset["functions"]
    if not all(
        isinstance(row, dict) and isinstance(row.get("identity_args"), str)
        for row in rows
    ):
        raise ValueError("製品関数の引数宣言が不正")
    return frozenset(row["identity_args"] for row in rows)


def _require_identifier(value: str, label: str) -> None:
    """引用を要しない小文字のSQL識別子だけを許可する。"""
    if (
        not value
        or value[0] not in _IDENTIFIER_INITIALS
        or any(character not in _IDENTIFIER_CHARACTERS for character in value)
    ):
        raise ValueError(f"{label}が不正: {value!r}")


def product_function_id(
    schema_name: str,
    function_name: str,
    identity_args: str,
) -> str:
    """物理識別子から製品関数IDを生成する。

    Args:
        schema_name: 関数を置くスキーマ名。
        function_name: 関数名。
        identity_args: ``pg_get_function_identity_arguments`` 相当の引数列。

    Returns:
        スキーマ・名前・引数を含む一意な要素ID。

    Raises:
        ValueError: 識別子または製品資産で許可しない引数列が現れた場合。
    """
    _require_identifier(schema_name, "関数スキーマ識別子")
    _require_identifier(function_name, "関数名識別子")
    if not valid_product_identity_args(identity_args):
        raise ValueError(f"製品関数のidentity_argsの形が不正: {identity_args!r}")
    if identity_args not in _declared_identity_args():
        raise ValueError(f"製品関数のidentity_argsが資産宣言にない: {identity_args!r}")
    return f"FUNCTION:{schema_name}:{function_name}({identity_args})"


def build_product_function_acl_declaration(
    schema_name: str,
    function_name: str,
    identity_args: str,
) -> dict[str, object]:
    """migrationトリガ関数の所有者とACL期待を組み立てる。"""
    return {
        "function_id": product_function_id(
            schema_name,
            function_name,
            identity_args,
        ),
        "schema_name": schema_name,
        "function_name": function_name,
        "identity_args": identity_args,
        "function_kind": "migration_trigger",
        "owner_role_id": "pitchlog_owner",
        "acl_expectations": [],
        "revoked_acl_expectations": [
            {
                "grantee": "PUBLIC",
                "privilege": "EXECUTE",
                "grantable": False,
            },
            {
                "grantee": "pitchlog_app",
                "privilege": "EXECUTE",
                "grantable": False,
            },
        ],
    }


def generate_product_function_acl_sql(
    schema_name: str,
    function_name: str,
    identity_args: str,
) -> str:
    """PUBLICとアプリ用ロールから関数実行権を剥奪するSQLを生成する。"""
    function_id = product_function_id(
        schema_name,
        function_name,
        identity_args,
    )
    physical_name = f"{schema_name}.{function_name}({identity_args})"
    return (
        "-- ELEMENT-TYPE: function\n"
        f"-- ELEMENT-ID: {function_id}\n"
        "\n"
        f"REVOKE EXECUTE ON FUNCTION {physical_name} FROM PUBLIC;\n"
        f"REVOKE EXECUTE ON FUNCTION {physical_name} FROM pitchlog_app;\n"
    )
