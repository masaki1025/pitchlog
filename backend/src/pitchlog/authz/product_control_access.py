"""制御資源の補助関数・ポリシー・列ACLを決定的に生成する。"""

from __future__ import annotations

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
HELPER_DEPENDENCY_COLUMNS: Final = (
    ("tenants", "id"),
    ("tenants", "enabled"),
    ("analysis_groups", "id"),
    ("analysis_groups", "status"),
    ("group_memberships", "group_id"),
    ("group_memberships", "tenant_id"),
    ("group_memberships", "role"),
    ("group_memberships", "status"),
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
    """補助関数所有者の列ACL IDを返す。"""
    if (table_id, column_id) not in HELPER_DEPENDENCY_COLUMNS:
        raise ValueError(f"補助関数の依存列が閉集合にない: {table_id}.{column_id}")
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
