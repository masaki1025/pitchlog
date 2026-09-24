"""migration由来の製品関数ACLを決定的に生成する。"""

from __future__ import annotations

_IDENTIFIER_INITIALS = "abcdefghijklmnopqrstuvwxyz_"
_IDENTIFIER_CHARACTERS = f"{_IDENTIFIER_INITIALS}0123456789"


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
        ValueError: 識別子が不正、または本ステップに引数付き関数が現れた場合。
    """
    _require_identifier(schema_name, "関数スキーマ識別子")
    _require_identifier(function_name, "関数名識別子")
    if identity_args:
        raise ValueError("ステップ12のmigrationトリガ関数は引数を持てない")
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
