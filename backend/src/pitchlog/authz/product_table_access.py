"""製品表の直接アクセスポリシーとACLを決定的に生成する。"""

from __future__ import annotations

from typing import Final

TENANT_PREDICATE_ID: Final = "PREDICATE:TENANT"
TENANT_PREDICATE_TEMPLATE: Final = (
    "COALESCE({column} = NULLIF(pg_catalog.current_setting('app.tenant_id', true), "
    "'')::UUID, FALSE)"
)
DIRECT_POLICY_PROFILES: Final = frozenset(
    {"tenant_owned", "self_tenant_row", "global_read_only"}
)
DIRECT_ACL_PROFILES: Final = DIRECT_POLICY_PROFILES

_IDENTIFIER_INITIALS = "abcdefghijklmnopqrstuvwxyz_"
_IDENTIFIER_CHARACTERS = f"{_IDENTIFIER_INITIALS}0123456789"
_PROFILE_COMMANDS: Final = {
    "tenant_owned": "ALL",
    "self_tenant_row": "SELECT",
    "global_read_only": "SELECT",
}
_PROFILE_COLUMNS: Final = {
    "tenant_owned": "tenant_id",
    "self_tenant_row": "id",
    "global_read_only": None,
}
_PROFILE_PRIVILEGES: Final = {
    "tenant_owned": ("SELECT", "INSERT", "UPDATE"),
    "self_tenant_row": ("SELECT",),
    "global_read_only": ("SELECT",),
}


def _require_identifier(value: str, label: str) -> None:
    """引用を要しない小文字のSQL識別子だけを許可する。"""
    if (
        not value
        or value[0] not in _IDENTIFIER_INITIALS
        or any(character not in _IDENTIFIER_CHARACTERS for character in value)
    ):
        raise ValueError(f"{label}が不正: {value!r}")


def _require_direct_profile(profile: str) -> None:
    """ステップ11で作成する3プロファイルだけを許可する。"""
    if profile not in DIRECT_POLICY_PROFILES:
        raise ValueError(f"直接アクセスプロファイルが不正: {profile!r}")


def expand_tenant_predicate(column: str) -> str:
    """TENANT(c)を指定列へ展開する。

    Args:
        column: テナント識別子と比較する列名。

    Returns:
        設計で固定されたNULL安全なUUID比較式。

    Raises:
        ValueError: 列名が正規な識別子でない場合。
    """
    _require_identifier(column, "TENANT述語の列識別子")
    return TENANT_PREDICATE_TEMPLATE.replace("{column}", column)


def build_product_predicate_declaration() -> dict[str, object]:
    """TENANT(c)の単一述語要素を組み立てる。"""
    return {
        "predicate_id": TENANT_PREDICATE_ID,
        "predicate_kind": "tenant_column",
        "parameter": "column",
        "expression_template": TENANT_PREDICATE_TEMPLATE,
    }


def product_policy_id(table_id: str, profile: str) -> str:
    """表とプロファイルから一意なポリシーIDを返す。"""
    _require_identifier(table_id, "ポリシーの表識別子")
    _require_direct_profile(profile)
    return f"POLICY:{table_id}:{profile}"


def build_product_policy_declaration(
    table_id: str,
    profile: str,
) -> dict[str, object]:
    """設計上のプロファイルからポリシー宣言を導出する。"""
    policy_id = product_policy_id(table_id, profile)
    column = _PROFILE_COLUMNS[profile]
    using_expression = expand_tenant_predicate(column) if column is not None else "true"
    has_with_check = profile == "tenant_owned"
    return {
        "policy_id": policy_id,
        "table_id": table_id,
        "profile": profile,
        "command": _PROFILE_COMMANDS[profile],
        "policy_mode": "permissive",
        "role_ids": ["pitchlog_app"],
        "using_predicate_id": (TENANT_PREDICATE_ID if column is not None else None),
        "using_column": column,
        "using_expression": using_expression,
        "with_check_predicate_id": TENANT_PREDICATE_ID if has_with_check else None,
        "with_check_column": column if has_with_check else None,
        "with_check_expression": using_expression if has_with_check else None,
    }


def generate_product_predicate_sql() -> str:
    """TENANT(c)の論理要素を表す固定bodyを生成する。"""
    return (
        "-- ELEMENT-TYPE: predicate\n"
        f"-- ELEMENT-ID: {TENANT_PREDICATE_ID}\n"
        "\n"
        "-- PostgreSQLに独立した述語オブジェクトはないため、各ポリシーへ展開する。\n"
        f"-- TENANT(c) = {TENANT_PREDICATE_TEMPLATE}\n"
    )


def generate_product_policy_sql(table_id: str, profile: str) -> str:
    """表の直接アクセスポリシーSQLを生成する。"""
    declaration = build_product_policy_declaration(table_id, profile)
    policy_id = str(declaration["policy_id"])
    command = str(declaration["command"])
    using_expression = str(declaration["using_expression"])
    policy_name = f"pitchlog_app_{profile}"
    sql = (
        "-- ELEMENT-TYPE: policy\n"
        f"-- ELEMENT-ID: {policy_id}\n"
        "\n"
        f"CREATE POLICY {policy_name}\n"
        f"    ON public.{table_id}\n"
        "    AS PERMISSIVE\n"
        f"    FOR {command}\n"
        "    TO pitchlog_app\n"
        "    USING (\n"
        f"        {using_expression}\n"
        "    )"
    )
    with_check_expression = declaration["with_check_expression"]
    if with_check_expression is not None:
        sql += f"\n    WITH CHECK (\n        {with_check_expression}\n    )"
    return f"{sql};\n"


def product_table_acl_id(table_id: str) -> str:
    """アプリ用ロールの表ACL IDを返す。"""
    _require_identifier(table_id, "ACLの表識別子")
    return f"ACL:{table_id}:pitchlog_app"


def build_product_table_acl_declaration(
    table_id: str,
    profile: str,
) -> dict[str, object]:
    """設計上のプロファイルから表ACL宣言を導出する。"""
    _require_direct_profile(profile)
    return {
        "acl_id": product_table_acl_id(table_id),
        "object_kind": "table",
        "object_schema": "public",
        "object_id": table_id,
        "profile": profile,
        "grantee_role_id": "pitchlog_app",
        "privilege_ids": list(_PROFILE_PRIVILEGES[profile]),
        "grant_option": False,
    }


def generate_product_table_acl_sql(table_id: str, profile: str) -> str:
    """表ACLを閉集合へ正規化するSQLを生成する。"""
    declaration = build_product_table_acl_declaration(table_id, profile)
    acl_id = str(declaration["acl_id"])
    privilege_ids = declaration["privilege_ids"]
    if not isinstance(privilege_ids, list):  # pragma: no cover - 内部契約の防御。
        raise ValueError("ACL権限の内部表現が不正")
    privileges = ", ".join(str(privilege) for privilege in privilege_ids)
    return (
        "-- ELEMENT-TYPE: acl_expectation\n"
        f"-- ELEMENT-ID: {acl_id}\n"
        "\n"
        f"REVOKE ALL PRIVILEGES ON TABLE public.{table_id} "
        "FROM PUBLIC, pitchlog_app;\n"
        f"GRANT {privileges} ON TABLE public.{table_id} TO pitchlog_app;\n"
    )
