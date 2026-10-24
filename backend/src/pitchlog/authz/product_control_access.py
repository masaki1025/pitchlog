"""制御資源の補助関数・ポリシー・列ACLを決定的に生成する。"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Final

CONTROL_PROFILE: Final = "effective_group_control"
CONTROL_TABLE_IDS: Final = (
    "analysis_groups",
    "group_memberships",
    "sharing_grants",
    "group_invitations",
)
HELPER_SCHEMA: Final = "authz_private"
HELPER_NAME: Final = "tenant_has_effective_membership"
HELPER_IDENTITY_ARGS: Final = "uuid, boolean"
HELPER_FUNCTION_ID: Final = (
    "FUNCTION:authz_private:tenant_has_effective_membership(uuid, boolean)"
)
HELPER_OWNER_ROLE_ID: Final = "pitchlog_shared_fn_owner"
HELPER_SEARCH_PATH: Final = ("pg_catalog", "pg_temp")
RG1_SINGLETON_UPDATE_ACL_ID: Final = (
    "COLUMN-ACL:public:rg1_restore_gate:singleton_id:pitchlog_rg1_fn_owner"
)
RG1_COMMIT_CHECK_FUNCTION_ID: Final = (
    "FUNCTION:rg1_api:rg1_assert_open_before_commit(uuid)"
)
RG1_RESTORE_GATE_TABLE_ID: Final = "rg1_restore_gate"
RG1_FUNCTION_OWNER_ROLE_ID: Final = "pitchlog_rg1_fn_owner"
RULE_RESOLUTION_FUNCTION_ID: Final = (
    "FUNCTION:public:resolve_stage_a_rule(uuid, text, text, boolean)"
)
RULE_RESOLUTION_OWNER_ROLE_ID: Final = "pitchlog_rule_resolution_fn_owner"
RULE_RESOLUTION_UPDATE_COLUMNS: Final = frozenset(
    {
        ("game_type_rule_defaults", "game_type_category"),
        ("rule_sets", "id"),
        ("tenant_vocabularies", "disabled"),
    }
)
_CONTROL_POLICY_EXPRESSIONS: Final = (
    (
        "analysis_groups",
        "authz_private.tenant_has_effective_membership(id, false)",
    ),
    (
        "group_memberships",
        "authz_private.tenant_has_effective_membership(group_id, false)",
    ),
    (
        "sharing_grants",
        "EXISTS (SELECT 1 FROM public.group_memberships AS membership "
        "WHERE membership.id = sharing_grants.membership_id AND "
        "authz_private.tenant_has_effective_membership("
        "membership.group_id, false))",
    ),
    (
        "group_invitations",
        "authz_private.tenant_has_effective_membership(group_id, true)",
    ),
)


def _control_policy_expression(table_id: str) -> str:
    """制御資源表に対応する閉じた述語を返す。"""
    for expected_table_id, expression in _CONTROL_POLICY_EXPRESSIONS:
        if table_id == expected_table_id:
            return expression
    raise ValueError(f"制御資源の表識別子が閉集合にない: {table_id!r}")


def build_control_policy_declaration(table_id: str) -> dict[str, object]:
    """制御資源のSELECTポリシー宣言を組み立てる。"""
    using_expression = _control_policy_expression(table_id)
    return {
        "policy_id": f"POLICY:{table_id}:{CONTROL_PROFILE}",
        "table_id": table_id,
        "profile": CONTROL_PROFILE,
        "command": "SELECT",
        "policy_mode": "permissive",
        "role_ids": ["pitchlog_app"],
        "using_predicate_id": HELPER_FUNCTION_ID,
        "using_column": None,
        "using_expression": using_expression,
        "with_check_predicate_id": None,
        "with_check_column": None,
        "with_check_expression": None,
    }


def generate_control_policy_sql(table_id: str) -> str:
    """制御資源のSELECTポリシーSQLを生成する。"""
    declaration = build_control_policy_declaration(table_id)
    policy_id = str(declaration["policy_id"])
    using_expression = str(declaration["using_expression"])
    return (
        "-- ELEMENT-TYPE: policy\n"
        f"-- ELEMENT-ID: {policy_id}\n"
        "\n"
        "CREATE POLICY pitchlog_app_effective_group_control\n"
        f"    ON public.{table_id}\n"
        "    AS PERMISSIVE\n"
        "    FOR SELECT\n"
        "    TO pitchlog_app\n"
        "    USING (\n"
        f"        {using_expression}\n"
        "    );\n"
    )


def build_membership_helper_declaration() -> dict[str, object]:
    """実効参加判定の補助関数宣言を組み立てる。"""
    return {
        "function_id": HELPER_FUNCTION_ID,
        "schema_name": HELPER_SCHEMA,
        "function_name": HELPER_NAME,
        "identity_args": HELPER_IDENTITY_ARGS,
        "function_kind": "rls_helper",
        "owner_role_id": HELPER_OWNER_ROLE_ID,
        "language": "sql",
        "returns": "boolean",
        "security_mode": "definer",
        "volatility": "stable",
        "search_path": list(HELPER_SEARCH_PATH),
        "acl_expectations": [],
        "revoked_acl_expectations": [
            {"grantee": "PUBLIC", "privilege": "EXECUTE", "grantable": False},
            {
                "grantee": "pitchlog_app",
                "privilege": "EXECUTE",
                "grantable": False,
            },
        ],
    }


def generate_membership_helper_sql() -> str:
    """実効参加判定の補助関数SQLを生成する。"""
    return (
        "-- ELEMENT-TYPE: function\n"
        f"-- ELEMENT-ID: {HELPER_FUNCTION_ID}\n"
        "\n"
        "CREATE OR REPLACE FUNCTION "
        "authz_private.tenant_has_effective_membership(\n"
        "    p_group_id uuid,\n"
        "    p_require_admin boolean\n"
        ")\n"
        "RETURNS boolean\n"
        "LANGUAGE sql\n"
        "STABLE\n"
        "SECURITY DEFINER\n"
        "SET search_path = pg_catalog, pg_temp\n"
        "AS $function$\n"
        "    SELECT COALESCE(\n"
        "        (\n"
        "            SELECT true\n"
        "            FROM public.analysis_groups AS effective_group\n"
        "            JOIN public.group_memberships AS membership\n"
        "                ON membership.group_id = effective_group.id\n"
        "            JOIN public.tenants AS member_tenant\n"
        "                ON member_tenant.id = membership.tenant_id\n"
        "            WHERE effective_group.id = p_group_id\n"
        "              AND effective_group.status = 'active'\n"
        "              AND membership.status = 'active'\n"
        "              AND member_tenant.enabled\n"
        "              AND membership.tenant_id = NULLIF(\n"
        "                  pg_catalog.current_setting('app.tenant_id', true),\n"
        "                  ''\n"
        "              )::uuid\n"
        "              AND (NOT p_require_admin OR membership.role = 'admin')\n"
        "            LIMIT 1\n"
        "        ),\n"
        "        false\n"
        "    );\n"
        "$function$;\n"
        "ALTER FUNCTION authz_private.tenant_has_effective_membership(uuid, boolean)\n"
        "    OWNER TO pitchlog_shared_fn_owner;\n"
        "REVOKE ALL PRIVILEGES ON FUNCTION "
        "authz_private.tenant_has_effective_membership(uuid, boolean)\n"
        "    FROM PUBLIC, pitchlog_app;\n"
        "REVOKE ALL PRIVILEGES ON TABLE public.tenants, "
        "public.analysis_groups, public.group_memberships\n"
        "    FROM pitchlog_shared_fn_owner;\n"
        "REVOKE SELECT (id, name, enabled, disabled_at, import_batch_id)\n"
        "    ON TABLE public.tenants FROM pitchlog_shared_fn_owner;\n"
        "REVOKE SELECT (id, status, terminated_at, termination_reason)\n"
        "    ON TABLE public.analysis_groups FROM pitchlog_shared_fn_owner;\n"
        "REVOKE SELECT (id, group_id, tenant_id, role, status, joined_at, left_at)\n"
        "    ON TABLE public.group_memberships FROM pitchlog_shared_fn_owner;\n"
    )


def column_acl_expectation_id(table_id: str, column_id: str) -> str:
    """補助関数所有者の列ACL IDを安全な識別子から返す。"""
    for value in (table_id, column_id):
        if re.fullmatch(r"[a-z_][a-z0-9_]*", value) is None:
            raise ValueError(f"列ACLの識別子が不正: {value!r}")
    return f"COLUMN-ACL:public:{table_id}:{column_id}:{HELPER_OWNER_ROLE_ID}"


def build_helper_column_acl_declaration(
    table_id: str,
    column_id: str,
) -> dict[str, object]:
    """補助関数所有者へ与える1列のSELECT宣言を組み立てる。"""
    expectation_id = column_acl_expectation_id(table_id, column_id)
    return {
        "expectation_id": expectation_id,
        "object_kind": "column",
        "object_schema": "public",
        "object_id": table_id,
        "column_id": column_id,
        "grantee_role_id": HELPER_OWNER_ROLE_ID,
        "privilege_ids": ["SELECT"],
        "grant_option": False,
        "function_id": HELPER_FUNCTION_ID,
    }


def generate_helper_column_acl_sql(table_id: str, column_id: str) -> str:
    """補助関数所有者へ1列のSELECTを与えるSQLを生成する。"""
    expectation_id = column_acl_expectation_id(table_id, column_id)
    return (
        "-- ELEMENT-TYPE: column_acl_expectation\n"
        f"-- ELEMENT-ID: {expectation_id}\n"
        "\n"
        f"GRANT SELECT ({column_id}) ON TABLE public.{table_id} "
        f"TO {HELPER_OWNER_ROLE_ID};\n"
    )


def is_rg1_singleton_update_acl(declaration: Mapping[str, object]) -> bool:
    """RG1の単一列・専用owner・確定前関数だけへUPDATEを限定する。"""
    return dict(declaration) == {
        "expectation_id": RG1_SINGLETON_UPDATE_ACL_ID,
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "rg1_restore_gate",
        "column_id": "singleton_id",
        "grantee_role_id": "pitchlog_rg1_fn_owner",
        "privilege_ids": ["SELECT", "UPDATE"],
        "grant_option": False,
        "function_id": RG1_COMMIT_CHECK_FUNCTION_ID,
    }


def is_rg1_control_column_acl(declaration: Mapping[str, object]) -> bool:
    """実制御ownerの単一行2列だけをclose_gateの能力へ限定する。"""
    column = declaration.get("column_id")
    return (
        declaration.get("grant_option") is False
        and isinstance(column, str)
        and column in {"singleton_id", "state"}
        and dict(declaration)
        == {
            "expectation_id": (
                f"COLUMN-ACL:public:rg1_restore_gate:{column}:pitchlog_rg1_control_owner"
            ),
            "object_kind": "column",
            "object_schema": "public",
            "object_id": "rg1_restore_gate",
            "column_id": column,
            "grantee_role_id": "pitchlog_rg1_control_owner",
            "privilege_ids": ["SELECT", "UPDATE"] if column == "state" else ["SELECT"],
            "grant_option": False,
            "function_id": "FUNCTION:rg1_control:close_gate()",
        }
    )


def is_rule_resolution_update_acl(declaration: Mapping[str, object]) -> bool:
    """規則解決関数のロック用3列だけへUPDATEを限定する。"""
    table = declaration.get("object_id")
    column = declaration.get("column_id")
    expected_id = f"COLUMN-ACL:public:{table}:{column}:{RULE_RESOLUTION_OWNER_ROLE_ID}"
    return (
        isinstance(table, str)
        and isinstance(column, str)
        and (table, column) in RULE_RESOLUTION_UPDATE_COLUMNS
        and dict(declaration)
        == {
            "expectation_id": expected_id,
            "object_kind": "column",
            "object_schema": "public",
            "object_id": table,
            "column_id": column,
            "grantee_role_id": RULE_RESOLUTION_OWNER_ROLE_ID,
            "privilege_ids": ["SELECT", "UPDATE"],
            "grant_option": False,
            "function_id": RULE_RESOLUTION_FUNCTION_ID,
        }
    )


def is_forbidden_rg1_table_acl(declaration: Mapping[str, object]) -> bool:
    """RG1状態表または専用ownerの表単位ACLを拒否する。"""
    return declaration.get("object_id") == RG1_RESTORE_GATE_TABLE_ID or declaration.get(
        "grantee_role_id"
    ) in {
        RG1_FUNCTION_OWNER_ROLE_ID,
        "pitchlog_rg1_control_owner",
    }


def generate_function_owner_column_acl_sql(
    declaration: dict[str, object],
) -> str:
    """関数所有者の列SELECTと閉じた列UPDATE SQLを生成する。"""
    acl_id = str(declaration["expectation_id"])
    schema_name = str(declaration["object_schema"])
    table_id = str(declaration["object_id"])
    column_id = str(declaration["column_id"])
    role_id = str(declaration["grantee_role_id"])
    for value in (schema_name, table_id, column_id, role_id):
        if re.fullmatch(r"[a-z_][a-z0-9_]*", value) is None:
            raise ValueError(f"列ACLの識別子が不正: {value!r}")
    if acl_id != f"COLUMN-ACL:{schema_name}:{table_id}:{column_id}:{role_id}":
        raise ValueError("関数所有者の列 ACL ID が物理識別子と一致しない")
    needs_update = (
        is_rg1_singleton_update_acl(declaration)
        or is_rule_resolution_update_acl(declaration)
        or (
            is_rg1_control_column_acl(declaration)
            and declaration.get("column_id") == "state"
        )
    )
    if not needs_update and (
        declaration.get("privilege_ids") != ["SELECT"]
        or declaration.get("grant_option") is not False
    ):
        raise ValueError(
            "関数所有者の列 ACL は SELECT と固定3列/RG1限定UPDATEだけを許可する"
        )
    privileges = (
        f"SELECT ({column_id}), UPDATE ({column_id})"
        if needs_update
        else f"SELECT ({column_id})"
    )
    return (
        "-- ELEMENT-TYPE: column_acl_expectation\n"
        f"-- ELEMENT-ID: {acl_id}\n"
        "\n"
        f"GRANT {privileges} ON TABLE {schema_name}.{table_id} "
        f"TO {role_id};\n"
    )
