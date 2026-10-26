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
        "ALTER FUNCTION authz_private.tenant_has_effective_membe"
        "rship(uuid, boolean)\n"
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
        "REVOKE SELECT (id, group_id, tenant_id, role, status, j"
        "oined_at, left_at)\n"
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
    """旧2列と初回epoch専用1列を、それぞれの固定関数へ限定する。"""
    if declaration.get("grant_option") is not False:
        return False
    column = declaration.get("column_id")
    if column == "recovery_generation":
        return dict(declaration) == {
            "expectation_id": (
                "COLUMN-ACL:public:rg1_restore_gate:recovery_generation:"
                "pitchlog_rg1_control_owner"
            ),
            "object_kind": "column",
            "object_schema": "public",
            "object_id": "rg1_restore_gate",
            "column_id": "recovery_generation",
            "grantee_role_id": "pitchlog_rg1_control_owner",
            "privilege_ids": ["SELECT", "UPDATE"],
            "grant_option": False,
            "function_id": "FUNCTION:rg1_control:bind_initial_fresh_epoch(bigint)",
        }
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
    return declaration.get("object_id") in {
        *INITIAL_STORAGE_TABLES,
        RG1_RESTORE_GATE_TABLE_ID,
    } or declaration.get("grantee_role_id") in {
        "pitchlog_initial_fn_owner",
        "pitchlog_initial_actor",
        RG1_FUNCTION_OWNER_ROLE_ID,
        "pitchlog_rg1_control_owner",
        "pitchlog_rg1_control_actor",
        "pitchlog_ledger_identity_owner",
        "pitchlog_ledger_identity_probe",
    }


def generate_function_owner_column_acl_sql(
    declaration: dict[str, object],
) -> str:
    """関数所有者の列SELECTと閉じた列UPDATE SQLを生成する。"""
    from pitchlog.authz.initial_start_sql import (
        generate_start_column_acl_sql,
        is_start_column_acl,
    )

    if is_start_column_acl(declaration):
        return generate_start_column_acl_sql(declaration)
    if is_initial_column_acl(declaration) or is_enrollment_column_acl(declaration):
        return generate_initial_column_acl_sql(declaration)
    if declaration.get("grantee_role_id") in {
        "pitchlog_initial_fn_owner",
        "pitchlog_initial_actor",
        "pitchlog_app",
    }:
        raise ValueError("初期主体の列ACLがexact集合にない")
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
    if role_id in {
        "pitchlog_rg1_control_actor",
        "pitchlog_ledger_identity_owner",
        "pitchlog_ledger_identity_probe",
    }:
        raise ValueError("RG1制御actor/観測主体には業務列ACLを許可しない")
    if role_id == "pitchlog_rg1_control_owner" and not is_rg1_control_column_acl(
        declaration
    ):
        raise ValueError("RG1制御ownerには固定2列以外の列ACLを許可しない")
    needs_update = (
        is_rg1_singleton_update_acl(declaration)
        or is_rule_resolution_update_acl(declaration)
        or (
            is_rg1_control_column_acl(declaration)
            and declaration.get("column_id") in {"state", "recovery_generation"}
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


INITIAL_STORAGE_TABLES: Final = (
    "trusted_devices",
    "game_start_requests",
    "game_start_attempts",
    "recording_right_deliveries",
)

_INITIAL_COLUMN_ACLS: Final[dict[str, dict[str, object]]] = {
    "COLUMN-ACL:public:trusted_devices:tenant_id:pitchlog_initial_fn_owner": {
        "expectation_id": (
            "COLUMN-ACL:public:trusted_devices:tenant_id:pitchlog_initial_fn_owner"
        ),
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "trusted_devices",
        "column_id": "tenant_id",
        "grantee_role_id": "pitchlog_initial_fn_owner",
        "privilege_ids": ["SELECT"],
        "grant_option": False,
    },
    "COLUMN-ACL:public:trusted_devices:device_id:pitchlog_initial_fn_owner": {
        "expectation_id": (
            "COLUMN-ACL:public:trusted_devices:device_id:pitchlog_initial_fn_owner"
        ),
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "trusted_devices",
        "column_id": "device_id",
        "grantee_role_id": "pitchlog_initial_fn_owner",
        "privilege_ids": ["SELECT", "UPDATE"],
        "grant_option": False,
    },
    ("COLUMN-ACL:public:trusted_devices:credential_digest:pitchlog_initial_fn_owner"): {
        "expectation_id": (
            "COLUMN-ACL:public:trusted_devices:credential_digest:pit"
            "chlog_initial_fn_owner"
        ),
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "trusted_devices",
        "column_id": "credential_digest",
        "grantee_role_id": "pitchlog_initial_fn_owner",
        "privilege_ids": ["SELECT"],
        "grant_option": False,
    },
    "COLUMN-ACL:public:trusted_devices:revoked_at:pitchlog_initial_fn_owner": {
        "expectation_id": (
            "COLUMN-ACL:public:trusted_devices:revoked_at:pitchlog_initial_fn_owner"
        ),
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "trusted_devices",
        "column_id": "revoked_at",
        "grantee_role_id": "pitchlog_initial_fn_owner",
        "privilege_ids": ["SELECT"],
        "grant_option": False,
    },
    ("COLUMN-ACL:public:game_start_requests:tenant_id:pitchlog_initial_fn_owner"): {
        "expectation_id": (
            "COLUMN-ACL:public:game_start_requests:tenant_id:pitchlog_initial_fn_owner"
        ),
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "game_start_requests",
        "column_id": "tenant_id",
        "grantee_role_id": "pitchlog_initial_fn_owner",
        "privilege_ids": ["SELECT", "INSERT"],
        "grant_option": False,
    },
    "COLUMN-ACL:public:game_start_requests:game_id:pitchlog_initial_fn_owner": {
        "expectation_id": (
            "COLUMN-ACL:public:game_start_requests:game_id:pitchlog_initial_fn_owner"
        ),
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "game_start_requests",
        "column_id": "game_id",
        "grantee_role_id": "pitchlog_initial_fn_owner",
        "privilege_ids": ["SELECT", "INSERT"],
        "grant_option": False,
    },
    (
        "COLUMN-ACL:public:game_start_requests:start_request_id:"
        "pitchlog_initial_fn_owner"
    ): {
        "expectation_id": (
            "COLUMN-ACL:public:game_start_requests:start_request_id:"
            "pitchlog_initial_fn_owner"
        ),
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "game_start_requests",
        "column_id": "start_request_id",
        "grantee_role_id": "pitchlog_initial_fn_owner",
        "privilege_ids": ["SELECT", "INSERT", "UPDATE"],
        "grant_option": False,
    },
    ("COLUMN-ACL:public:game_start_requests:device_id:pitchlog_initial_fn_owner"): {
        "expectation_id": (
            "COLUMN-ACL:public:game_start_requests:device_id:pitchlog_initial_fn_owner"
        ),
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "game_start_requests",
        "column_id": "device_id",
        "grantee_role_id": "pitchlog_initial_fn_owner",
        "privilege_ids": ["SELECT", "INSERT"],
        "grant_option": False,
    },
    (
        "COLUMN-ACL:public:game_start_requests:request_digest:pitchlog_initial_fn_owner"
    ): {
        "expectation_id": (
            "COLUMN-ACL:public:game_start_requests:request_digest:pi"
            "tchlog_initial_fn_owner"
        ),
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "game_start_requests",
        "column_id": "request_digest",
        "grantee_role_id": "pitchlog_initial_fn_owner",
        "privilege_ids": ["SELECT", "INSERT"],
        "grant_option": False,
    },
    ("COLUMN-ACL:public:game_start_attempts:tenant_id:pitchlog_initial_fn_owner"): {
        "expectation_id": (
            "COLUMN-ACL:public:game_start_attempts:tenant_id:pitchlog_initial_fn_owner"
        ),
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "game_start_attempts",
        "column_id": "tenant_id",
        "grantee_role_id": "pitchlog_initial_fn_owner",
        "privilege_ids": ["SELECT", "INSERT"],
        "grant_option": False,
    },
    ("COLUMN-ACL:public:game_start_attempts:attempt_id:pitchlog_initial_fn_owner"): {
        "expectation_id": (
            "COLUMN-ACL:public:game_start_attempts:attempt_id:pitchlog_initial_fn_owner"
        ),
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "game_start_attempts",
        "column_id": "attempt_id",
        "grantee_role_id": "pitchlog_initial_fn_owner",
        "privilege_ids": ["SELECT", "INSERT"],
        "grant_option": False,
    },
    "COLUMN-ACL:public:game_start_attempts:game_id:pitchlog_initial_fn_owner": {
        "expectation_id": (
            "COLUMN-ACL:public:game_start_attempts:game_id:pitchlog_initial_fn_owner"
        ),
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "game_start_attempts",
        "column_id": "game_id",
        "grantee_role_id": "pitchlog_initial_fn_owner",
        "privilege_ids": ["SELECT", "INSERT"],
        "grant_option": False,
    },
    (
        "COLUMN-ACL:public:game_start_attempts:start_request_id:"
        "pitchlog_initial_fn_owner"
    ): {
        "expectation_id": (
            "COLUMN-ACL:public:game_start_attempts:start_request_id:"
            "pitchlog_initial_fn_owner"
        ),
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "game_start_attempts",
        "column_id": "start_request_id",
        "grantee_role_id": "pitchlog_initial_fn_owner",
        "privilege_ids": ["SELECT", "INSERT"],
        "grant_option": False,
    },
    ("COLUMN-ACL:public:game_start_attempts:device_id:pitchlog_initial_fn_owner"): {
        "expectation_id": (
            "COLUMN-ACL:public:game_start_attempts:device_id:pitchlog_initial_fn_owner"
        ),
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "game_start_attempts",
        "column_id": "device_id",
        "grantee_role_id": "pitchlog_initial_fn_owner",
        "privilege_ids": ["SELECT", "INSERT"],
        "grant_option": False,
    },
    "COLUMN-ACL:public:game_start_attempts:outcome:pitchlog_initial_fn_owner": {
        "expectation_id": (
            "COLUMN-ACL:public:game_start_attempts:outcome:pitchlog_initial_fn_owner"
        ),
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "game_start_attempts",
        "column_id": "outcome",
        "grantee_role_id": "pitchlog_initial_fn_owner",
        "privilege_ids": ["SELECT", "UPDATE"],
        "grant_option": False,
    },
    ("COLUMN-ACL:public:game_start_attempts:resolved_at:pitchlog_initial_fn_owner"): {
        "expectation_id": (
            "COLUMN-ACL:public:game_start_attempts:resolved_at:pitch"
            "log_initial_fn_owner"
        ),
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "game_start_attempts",
        "column_id": "resolved_at",
        "grantee_role_id": "pitchlog_initial_fn_owner",
        "privilege_ids": ["UPDATE"],
        "grant_option": False,
    },
    (
        "COLUMN-ACL:public:recording_right_deliveries:tenant_id:"
        "pitchlog_initial_fn_owner"
    ): {
        "expectation_id": (
            "COLUMN-ACL:public:recording_right_deliveries:tenant_id:"
            "pitchlog_initial_fn_owner"
        ),
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "recording_right_deliveries",
        "column_id": "tenant_id",
        "grantee_role_id": "pitchlog_initial_fn_owner",
        "privilege_ids": ["SELECT", "INSERT"],
        "grant_option": False,
    },
    (
        "COLUMN-ACL:public:recording_right_deliveries:game_id:pitchlog_initial_fn_owner"
    ): {
        "expectation_id": (
            "COLUMN-ACL:public:recording_right_deliveries:game_id:pi"
            "tchlog_initial_fn_owner"
        ),
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "recording_right_deliveries",
        "column_id": "game_id",
        "grantee_role_id": "pitchlog_initial_fn_owner",
        "privilege_ids": ["SELECT", "INSERT"],
        "grant_option": False,
    },
    (
        "COLUMN-ACL:public:recording_right_deliveries:generation"
        ":pitchlog_initial_fn_owner"
    ): {
        "expectation_id": (
            "COLUMN-ACL:public:recording_right_deliveries:generation"
            ":pitchlog_initial_fn_owner"
        ),
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "recording_right_deliveries",
        "column_id": "generation",
        "grantee_role_id": "pitchlog_initial_fn_owner",
        "privilege_ids": ["SELECT", "INSERT", "UPDATE"],
        "grant_option": False,
    },
    (
        "COLUMN-ACL:public:recording_right_deliveries:start_requ"
        "est_id:pitchlog_initial_fn_owner"
    ): {
        "expectation_id": (
            "COLUMN-ACL:public:recording_right_deliveries:start_requ"
            "est_id:pitchlog_initial_fn_owner"
        ),
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "recording_right_deliveries",
        "column_id": "start_request_id",
        "grantee_role_id": "pitchlog_initial_fn_owner",
        "privilege_ids": ["SELECT", "INSERT"],
        "grant_option": False,
    },
    (
        "COLUMN-ACL:public:recording_right_deliveries:device_id:"
        "pitchlog_initial_fn_owner"
    ): {
        "expectation_id": (
            "COLUMN-ACL:public:recording_right_deliveries:device_id:"
            "pitchlog_initial_fn_owner"
        ),
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "recording_right_deliveries",
        "column_id": "device_id",
        "grantee_role_id": "pitchlog_initial_fn_owner",
        "privilege_ids": ["SELECT", "INSERT"],
        "grant_option": False,
    },
    ("COLUMN-ACL:public:recording_right_deliveries:key_id:pitchlog_initial_fn_owner"): {
        "expectation_id": (
            "COLUMN-ACL:public:recording_right_deliveries:key_id:pit"
            "chlog_initial_fn_owner"
        ),
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "recording_right_deliveries",
        "column_id": "key_id",
        "grantee_role_id": "pitchlog_initial_fn_owner",
        "privilege_ids": ["SELECT", "INSERT"],
        "grant_option": False,
    },
    ("COLUMN-ACL:public:recording_right_deliveries:nonce:pitchlog_initial_fn_owner"): {
        "expectation_id": (
            "COLUMN-ACL:public:recording_right_deliveries:nonce:pitc"
            "hlog_initial_fn_owner"
        ),
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "recording_right_deliveries",
        "column_id": "nonce",
        "grantee_role_id": "pitchlog_initial_fn_owner",
        "privilege_ids": ["SELECT", "INSERT"],
        "grant_option": False,
    },
    (
        "COLUMN-ACL:public:recording_right_deliveries:ciphertext"
        ":pitchlog_initial_fn_owner"
    ): {
        "expectation_id": (
            "COLUMN-ACL:public:recording_right_deliveries:ciphertext"
            ":pitchlog_initial_fn_owner"
        ),
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "recording_right_deliveries",
        "column_id": "ciphertext",
        "grantee_role_id": "pitchlog_initial_fn_owner",
        "privilege_ids": ["SELECT", "INSERT"],
        "grant_option": False,
    },
    (
        "COLUMN-ACL:public:recording_right_deliveries:revoked_at"
        ":pitchlog_initial_fn_owner"
    ): {
        "expectation_id": (
            "COLUMN-ACL:public:recording_right_deliveries:revoked_at"
            ":pitchlog_initial_fn_owner"
        ),
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "recording_right_deliveries",
        "column_id": "revoked_at",
        "grantee_role_id": "pitchlog_initial_fn_owner",
        "privilege_ids": ["SELECT"],
        "grant_option": False,
    },
    ("COLUMN-ACL:public:recording_generations:tenant_id:pitchlog_initial_fn_owner"): {
        "expectation_id": (
            "COLUMN-ACL:public:recording_generations:tenant_id:pitch"
            "log_initial_fn_owner"
        ),
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "recording_generations",
        "column_id": "tenant_id",
        "grantee_role_id": "pitchlog_initial_fn_owner",
        "privilege_ids": ["SELECT", "INSERT"],
        "grant_option": False,
    },
    ("COLUMN-ACL:public:recording_generations:game_id:pitchlog_initial_fn_owner"): {
        "expectation_id": (
            "COLUMN-ACL:public:recording_generations:game_id:pitchlog_initial_fn_owner"
        ),
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "recording_generations",
        "column_id": "game_id",
        "grantee_role_id": "pitchlog_initial_fn_owner",
        "privilege_ids": ["SELECT", "INSERT"],
        "grant_option": False,
    },
    ("COLUMN-ACL:public:recording_generations:generation:pitchlog_initial_fn_owner"): {
        "expectation_id": (
            "COLUMN-ACL:public:recording_generations:generation:pitc"
            "hlog_initial_fn_owner"
        ),
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "recording_generations",
        "column_id": "generation",
        "grantee_role_id": "pitchlog_initial_fn_owner",
        "privilege_ids": ["SELECT", "INSERT", "UPDATE"],
        "grant_option": False,
    },
    "COLUMN-ACL:public:recording_generations:kind:pitchlog_initial_fn_owner": {
        "expectation_id": (
            "COLUMN-ACL:public:recording_generations:kind:pitchlog_initial_fn_owner"
        ),
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "recording_generations",
        "column_id": "kind",
        "grantee_role_id": "pitchlog_initial_fn_owner",
        "privilege_ids": ["SELECT", "INSERT"],
        "grant_option": False,
    },
    (
        "COLUMN-ACL:public:recording_generations:holder_device:p"
        "itchlog_initial_fn_owner"
    ): {
        "expectation_id": (
            "COLUMN-ACL:public:recording_generations:holder_device:p"
            "itchlog_initial_fn_owner"
        ),
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "recording_generations",
        "column_id": "holder_device",
        "grantee_role_id": "pitchlog_initial_fn_owner",
        "privilege_ids": ["SELECT", "INSERT"],
        "grant_option": False,
    },
    (
        "COLUMN-ACL:public:recording_generations:proof_digest:pitchlog_initial_fn_owner"
    ): {
        "expectation_id": (
            "COLUMN-ACL:public:recording_generations:proof_digest:pi"
            "tchlog_initial_fn_owner"
        ),
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "recording_generations",
        "column_id": "proof_digest",
        "grantee_role_id": "pitchlog_initial_fn_owner",
        "privilege_ids": ["SELECT", "INSERT"],
        "grant_option": False,
    },
    (
        "COLUMN-ACL:public:recording_generations:recovery_genera"
        "tion:pitchlog_initial_fn_owner"
    ): {
        "expectation_id": (
            "COLUMN-ACL:public:recording_generations:recovery_genera"
            "tion:pitchlog_initial_fn_owner"
        ),
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "recording_generations",
        "column_id": "recovery_generation",
        "grantee_role_id": "pitchlog_initial_fn_owner",
        "privilege_ids": ["SELECT", "INSERT"],
        "grant_option": False,
    },
    ("COLUMN-ACL:public:recording_generations:revoked_at:pitchlog_initial_fn_owner"): {
        "expectation_id": (
            "COLUMN-ACL:public:recording_generations:revoked_at:pitc"
            "hlog_initial_fn_owner"
        ),
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "recording_generations",
        "column_id": "revoked_at",
        "grantee_role_id": "pitchlog_initial_fn_owner",
        "privilege_ids": ["SELECT"],
        "grant_option": False,
    },
    (
        "COLUMN-ACL:public:recording_generations:issuance_order:"
        "pitchlog_initial_fn_owner"
    ): {
        "expectation_id": (
            "COLUMN-ACL:public:recording_generations:issuance_order:"
            "pitchlog_initial_fn_owner"
        ),
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "recording_generations",
        "column_id": "issuance_order",
        "grantee_role_id": "pitchlog_initial_fn_owner",
        "privilege_ids": ["INSERT"],
        "grant_option": False,
    },
    (
        "COLUMN-ACL:public:recording_generations:confirmed_water"
        "mark:pitchlog_initial_fn_owner"
    ): {
        "expectation_id": (
            "COLUMN-ACL:public:recording_generations:confirmed_water"
            "mark:pitchlog_initial_fn_owner"
        ),
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "recording_generations",
        "column_id": "confirmed_watermark",
        "grantee_role_id": "pitchlog_initial_fn_owner",
        "privilege_ids": ["INSERT"],
        "grant_option": False,
    },
    (
        "COLUMN-ACL:public:recording_generations:applied_prefix:"
        "pitchlog_initial_fn_owner"
    ): {
        "expectation_id": (
            "COLUMN-ACL:public:recording_generations:applied_prefix:"
            "pitchlog_initial_fn_owner"
        ),
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "recording_generations",
        "column_id": "applied_prefix",
        "grantee_role_id": "pitchlog_initial_fn_owner",
        "privilege_ids": ["INSERT"],
        "grant_option": False,
    },
    "COLUMN-ACL:public:games:tenant_id:pitchlog_initial_fn_owner": {
        "expectation_id": "COLUMN-ACL:public:games:tenant_id:pitchlog_initial_fn_owner",
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "games",
        "column_id": "tenant_id",
        "grantee_role_id": "pitchlog_initial_fn_owner",
        "privilege_ids": ["SELECT"],
        "grant_option": False,
    },
    "COLUMN-ACL:public:games:id:pitchlog_initial_fn_owner": {
        "expectation_id": "COLUMN-ACL:public:games:id:pitchlog_initial_fn_owner",
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "games",
        "column_id": "id",
        "grantee_role_id": "pitchlog_initial_fn_owner",
        "privilege_ids": ["SELECT"],
        "grant_option": False,
    },
    "COLUMN-ACL:public:games:status:pitchlog_initial_fn_owner": {
        "expectation_id": "COLUMN-ACL:public:games:status:pitchlog_initial_fn_owner",
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "games",
        "column_id": "status",
        "grantee_role_id": "pitchlog_initial_fn_owner",
        "privilege_ids": ["SELECT", "UPDATE"],
        "grant_option": False,
    },
    ("COLUMN-ACL:public:rg1_restore_gate:singleton_id:pitchlog_initial_fn_owner"): {
        "expectation_id": (
            "COLUMN-ACL:public:rg1_restore_gate:singleton_id:pitchlog_initial_fn_owner"
        ),
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "rg1_restore_gate",
        "column_id": "singleton_id",
        "grantee_role_id": "pitchlog_initial_fn_owner",
        "privilege_ids": ["SELECT"],
        "grant_option": False,
    },
    (
        "COLUMN-ACL:public:rg1_restore_gate:recovery_generation:"
        "pitchlog_initial_fn_owner"
    ): {
        "expectation_id": (
            "COLUMN-ACL:public:rg1_restore_gate:recovery_generation:"
            "pitchlog_initial_fn_owner"
        ),
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "rg1_restore_gate",
        "column_id": "recovery_generation",
        "grantee_role_id": "pitchlog_initial_fn_owner",
        "privilege_ids": ["SELECT"],
        "grant_option": False,
    },
    "COLUMN-ACL:public:recording_generations:tenant_id:pitchlog_app": {
        "expectation_id": (
            "COLUMN-ACL:public:recording_generations:tenant_id:pitchlog_app"
        ),
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "recording_generations",
        "column_id": "tenant_id",
        "grantee_role_id": "pitchlog_app",
        "privilege_ids": ["SELECT", "UPDATE"],
        "grant_option": False,
    },
    "COLUMN-ACL:public:recording_generations:import_batch_id:pitchlog_app": {
        "expectation_id": (
            "COLUMN-ACL:public:recording_generations:import_batch_id:pitchlog_app"
        ),
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "recording_generations",
        "column_id": "import_batch_id",
        "grantee_role_id": "pitchlog_app",
        "privilege_ids": ["SELECT", "UPDATE"],
        "grant_option": False,
    },
    "COLUMN-ACL:public:recording_generations:retired_at:pitchlog_app": {
        "expectation_id": (
            "COLUMN-ACL:public:recording_generations:retired_at:pitchlog_app"
        ),
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "recording_generations",
        "column_id": "retired_at",
        "grantee_role_id": "pitchlog_app",
        "privilege_ids": ["SELECT", "UPDATE"],
        "grant_option": False,
    },
    "COLUMN-ACL:public:recording_generations:game_id:pitchlog_app": {
        "expectation_id": (
            "COLUMN-ACL:public:recording_generations:game_id:pitchlog_app"
        ),
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "recording_generations",
        "column_id": "game_id",
        "grantee_role_id": "pitchlog_app",
        "privilege_ids": ["SELECT", "UPDATE"],
        "grant_option": False,
    },
    "COLUMN-ACL:public:recording_generations:generation:pitchlog_app": {
        "expectation_id": (
            "COLUMN-ACL:public:recording_generations:generation:pitchlog_app"
        ),
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "recording_generations",
        "column_id": "generation",
        "grantee_role_id": "pitchlog_app",
        "privilege_ids": ["SELECT", "UPDATE"],
        "grant_option": False,
    },
    "COLUMN-ACL:public:recording_generations:kind:pitchlog_app": {
        "expectation_id": "COLUMN-ACL:public:recording_generations:kind:pitchlog_app",
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "recording_generations",
        "column_id": "kind",
        "grantee_role_id": "pitchlog_app",
        "privilege_ids": ["SELECT", "UPDATE"],
        "grant_option": False,
    },
    "COLUMN-ACL:public:recording_generations:issuance_order:pitchlog_app": {
        "expectation_id": (
            "COLUMN-ACL:public:recording_generations:issuance_order:pitchlog_app"
        ),
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "recording_generations",
        "column_id": "issuance_order",
        "grantee_role_id": "pitchlog_app",
        "privilege_ids": ["SELECT", "UPDATE"],
        "grant_option": False,
    },
    "COLUMN-ACL:public:recording_generations:holder_device:pitchlog_app": {
        "expectation_id": (
            "COLUMN-ACL:public:recording_generations:holder_device:pitchlog_app"
        ),
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "recording_generations",
        "column_id": "holder_device",
        "grantee_role_id": "pitchlog_app",
        "privilege_ids": ["SELECT", "UPDATE"],
        "grant_option": False,
    },
    "COLUMN-ACL:public:recording_generations:confirmed_watermark:pitchlog_app": {
        "expectation_id": (
            "COLUMN-ACL:public:recording_generations:confirmed_watermark:pitchlog_app"
        ),
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "recording_generations",
        "column_id": "confirmed_watermark",
        "grantee_role_id": "pitchlog_app",
        "privilege_ids": ["SELECT", "UPDATE"],
        "grant_option": False,
    },
    "COLUMN-ACL:public:recording_generations:applied_prefix:pitchlog_app": {
        "expectation_id": (
            "COLUMN-ACL:public:recording_generations:applied_prefix:pitchlog_app"
        ),
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "recording_generations",
        "column_id": "applied_prefix",
        "grantee_role_id": "pitchlog_app",
        "privilege_ids": ["SELECT", "UPDATE"],
        "grant_option": False,
    },
    "COLUMN-ACL:public:recording_generations:granted_at:pitchlog_app": {
        "expectation_id": (
            "COLUMN-ACL:public:recording_generations:granted_at:pitchlog_app"
        ),
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "recording_generations",
        "column_id": "granted_at",
        "grantee_role_id": "pitchlog_app",
        "privilege_ids": ["SELECT", "UPDATE"],
        "grant_option": False,
    },
    "COLUMN-ACL:public:recording_generations:revoked_at:pitchlog_app": {
        "expectation_id": (
            "COLUMN-ACL:public:recording_generations:revoked_at:pitchlog_app"
        ),
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "recording_generations",
        "column_id": "revoked_at",
        "grantee_role_id": "pitchlog_app",
        "privilege_ids": ["SELECT", "UPDATE"],
        "grant_option": False,
    },
}

# 識別/述語束縛のテンプレート。外部宣言の正解は共通TENANT展開済みbuilderだけ。
_INITIAL_POLICIES: Final[dict[str, dict[str, object]]] = {
    "POLICY:trusted_devices:initial_right_trusted_devices_select": {
        "policy_id": "POLICY:trusted_devices:initial_right_trusted_devices_select",
        "table_id": "trusted_devices",
        "profile": "function_only",
        "policy_name": "initial_right_trusted_devices_select",
        "command": "SELECT",
        "policy_mode": "permissive",
        "role_ids": ["pitchlog_initial_fn_owner"],
        "using_predicate_id": "PREDICATE:TENANT",
        "using_column": "tenant_id",
        "using_expression": None,
        "with_check_predicate_id": None,
        "with_check_column": None,
        "with_check_expression": None,
    },
    "POLICY:trusted_devices:initial_right_trusted_devices_update": {
        "policy_id": "POLICY:trusted_devices:initial_right_trusted_devices_update",
        "table_id": "trusted_devices",
        "profile": "function_only",
        "policy_name": "initial_right_trusted_devices_update",
        "command": "UPDATE",
        "policy_mode": "permissive",
        "role_ids": ["pitchlog_initial_fn_owner"],
        "using_predicate_id": "PREDICATE:TENANT",
        "using_column": "tenant_id",
        "using_expression": None,
        "with_check_predicate_id": "PREDICATE:TENANT",
        "with_check_column": "tenant_id",
        "with_check_expression": None,
    },
    "POLICY:game_start_requests:initial_right_game_start_requests_select": {
        "policy_id": (
            "POLICY:game_start_requests:initial_right_game_start_requests_select"
        ),
        "table_id": "game_start_requests",
        "profile": "function_only",
        "policy_name": "initial_right_game_start_requests_select",
        "command": "SELECT",
        "policy_mode": "permissive",
        "role_ids": ["pitchlog_initial_fn_owner"],
        "using_predicate_id": "PREDICATE:TENANT",
        "using_column": "tenant_id",
        "using_expression": None,
        "with_check_predicate_id": None,
        "with_check_column": None,
        "with_check_expression": None,
    },
    "POLICY:game_start_requests:initial_right_game_start_requests_insert": {
        "policy_id": (
            "POLICY:game_start_requests:initial_right_game_start_requests_insert"
        ),
        "table_id": "game_start_requests",
        "profile": "function_only",
        "policy_name": "initial_right_game_start_requests_insert",
        "command": "INSERT",
        "policy_mode": "permissive",
        "role_ids": ["pitchlog_initial_fn_owner"],
        "using_predicate_id": None,
        "using_column": None,
        "using_expression": None,
        "with_check_predicate_id": "PREDICATE:TENANT",
        "with_check_column": "tenant_id",
        "with_check_expression": None,
    },
    "POLICY:game_start_requests:initial_right_game_start_requests_update": {
        "policy_id": (
            "POLICY:game_start_requests:initial_right_game_start_requests_update"
        ),
        "table_id": "game_start_requests",
        "profile": "function_only",
        "policy_name": "initial_right_game_start_requests_update",
        "command": "UPDATE",
        "policy_mode": "permissive",
        "role_ids": ["pitchlog_initial_fn_owner"],
        "using_predicate_id": "PREDICATE:TENANT",
        "using_column": "tenant_id",
        "using_expression": None,
        "with_check_predicate_id": "PREDICATE:TENANT",
        "with_check_column": "tenant_id",
        "with_check_expression": None,
    },
    "POLICY:game_start_attempts:initial_right_game_start_attempts_select": {
        "policy_id": (
            "POLICY:game_start_attempts:initial_right_game_start_attempts_select"
        ),
        "table_id": "game_start_attempts",
        "profile": "function_only",
        "policy_name": "initial_right_game_start_attempts_select",
        "command": "SELECT",
        "policy_mode": "permissive",
        "role_ids": ["pitchlog_initial_fn_owner"],
        "using_predicate_id": "PREDICATE:TENANT",
        "using_column": "tenant_id",
        "using_expression": None,
        "with_check_predicate_id": None,
        "with_check_column": None,
        "with_check_expression": None,
    },
    "POLICY:game_start_attempts:initial_right_game_start_attempts_insert": {
        "policy_id": (
            "POLICY:game_start_attempts:initial_right_game_start_attempts_insert"
        ),
        "table_id": "game_start_attempts",
        "profile": "function_only",
        "policy_name": "initial_right_game_start_attempts_insert",
        "command": "INSERT",
        "policy_mode": "permissive",
        "role_ids": ["pitchlog_initial_fn_owner"],
        "using_predicate_id": None,
        "using_column": None,
        "using_expression": None,
        "with_check_predicate_id": "PREDICATE:TENANT",
        "with_check_column": "tenant_id",
        "with_check_expression": None,
    },
    "POLICY:game_start_attempts:initial_right_game_start_attempts_update": {
        "policy_id": (
            "POLICY:game_start_attempts:initial_right_game_start_attempts_update"
        ),
        "table_id": "game_start_attempts",
        "profile": "function_only",
        "policy_name": "initial_right_game_start_attempts_update",
        "command": "UPDATE",
        "policy_mode": "permissive",
        "role_ids": ["pitchlog_initial_fn_owner"],
        "using_predicate_id": "PREDICATE:TENANT",
        "using_column": "tenant_id",
        "using_expression": None,
        "with_check_predicate_id": "PREDICATE:TENANT",
        "with_check_column": "tenant_id",
        "with_check_expression": None,
    },
    (
        "POLICY:recording_right_deliveries:initial_right_recordi"
        "ng_right_deliveries_select"
    ): {
        "policy_id": (
            "POLICY:recording_right_deliveries:initial_right_recordi"
            "ng_right_deliveries_select"
        ),
        "table_id": "recording_right_deliveries",
        "profile": "function_only",
        "policy_name": "initial_right_recording_right_deliveries_select",
        "command": "SELECT",
        "policy_mode": "permissive",
        "role_ids": ["pitchlog_initial_fn_owner"],
        "using_predicate_id": "PREDICATE:TENANT",
        "using_column": "tenant_id",
        "using_expression": None,
        "with_check_predicate_id": None,
        "with_check_column": None,
        "with_check_expression": None,
    },
    (
        "POLICY:recording_right_deliveries:initial_right_recordi"
        "ng_right_deliveries_insert"
    ): {
        "policy_id": (
            "POLICY:recording_right_deliveries:initial_right_recordi"
            "ng_right_deliveries_insert"
        ),
        "table_id": "recording_right_deliveries",
        "profile": "function_only",
        "policy_name": "initial_right_recording_right_deliveries_insert",
        "command": "INSERT",
        "policy_mode": "permissive",
        "role_ids": ["pitchlog_initial_fn_owner"],
        "using_predicate_id": None,
        "using_column": None,
        "using_expression": None,
        "with_check_predicate_id": "PREDICATE:TENANT",
        "with_check_column": "tenant_id",
        "with_check_expression": None,
    },
    (
        "POLICY:recording_right_deliveries:initial_right_recordi"
        "ng_right_deliveries_update"
    ): {
        "policy_id": (
            "POLICY:recording_right_deliveries:initial_right_recordi"
            "ng_right_deliveries_update"
        ),
        "table_id": "recording_right_deliveries",
        "profile": "function_only",
        "policy_name": "initial_right_recording_right_deliveries_update",
        "command": "UPDATE",
        "policy_mode": "permissive",
        "role_ids": ["pitchlog_initial_fn_owner"],
        "using_predicate_id": "PREDICATE:TENANT",
        "using_column": "tenant_id",
        "using_expression": None,
        "with_check_predicate_id": "PREDICATE:TENANT",
        "with_check_column": "tenant_id",
        "with_check_expression": None,
    },
    "POLICY:recording_generations:initial_right_recording_generations_select": {
        "policy_id": (
            "POLICY:recording_generations:initial_right_recording_generations_select"
        ),
        "table_id": "recording_generations",
        "profile": "tenant_owned",
        "policy_name": "initial_right_recording_generations_select",
        "command": "SELECT",
        "policy_mode": "permissive",
        "role_ids": ["pitchlog_initial_fn_owner"],
        "using_predicate_id": "PREDICATE:TENANT",
        "using_column": "tenant_id",
        "using_expression": None,
        "with_check_predicate_id": None,
        "with_check_column": None,
        "with_check_expression": None,
    },
    "POLICY:recording_generations:initial_right_recording_generations_insert": {
        "policy_id": (
            "POLICY:recording_generations:initial_right_recording_generations_insert"
        ),
        "table_id": "recording_generations",
        "profile": "tenant_owned",
        "policy_name": "initial_right_recording_generations_insert",
        "command": "INSERT",
        "policy_mode": "permissive",
        "role_ids": ["pitchlog_initial_fn_owner"],
        "using_predicate_id": None,
        "using_column": None,
        "using_expression": None,
        "with_check_predicate_id": "PREDICATE:TENANT",
        "with_check_column": "tenant_id",
        "with_check_expression": None,
    },
    "POLICY:recording_generations:initial_right_recording_generations_update": {
        "policy_id": (
            "POLICY:recording_generations:initial_right_recording_generations_update"
        ),
        "table_id": "recording_generations",
        "profile": "tenant_owned",
        "policy_name": "initial_right_recording_generations_update",
        "command": "UPDATE",
        "policy_mode": "permissive",
        "role_ids": ["pitchlog_initial_fn_owner"],
        "using_predicate_id": "PREDICATE:TENANT",
        "using_column": "tenant_id",
        "using_expression": None,
        "with_check_predicate_id": "PREDICATE:TENANT",
        "with_check_column": "tenant_id",
        "with_check_expression": None,
    },
    "POLICY:games:initial_right_games_select": {
        "policy_id": "POLICY:games:initial_right_games_select",
        "table_id": "games",
        "profile": "tenant_owned",
        "policy_name": "initial_right_games_select",
        "command": "SELECT",
        "policy_mode": "permissive",
        "role_ids": ["pitchlog_initial_fn_owner"],
        "using_predicate_id": "PREDICATE:TENANT",
        "using_column": "tenant_id",
        "using_expression": None,
        "with_check_predicate_id": None,
        "with_check_column": None,
        "with_check_expression": None,
    },
    "POLICY:games:initial_right_games_update": {
        "policy_id": "POLICY:games:initial_right_games_update",
        "table_id": "games",
        "profile": "tenant_owned",
        "policy_name": "initial_right_games_update",
        "command": "UPDATE",
        "policy_mode": "permissive",
        "role_ids": ["pitchlog_initial_fn_owner"],
        "using_predicate_id": "PREDICATE:TENANT",
        "using_column": "tenant_id",
        "using_expression": None,
        "with_check_predicate_id": "PREDICATE:TENANT",
        "with_check_column": "tenant_id",
        "with_check_expression": None,
    },
    "POLICY:rg1_restore_gate:initial_right_rg1_restore_gate_select": {
        "policy_id": "POLICY:rg1_restore_gate:initial_right_rg1_restore_gate_select",
        "table_id": "rg1_restore_gate",
        "profile": "function_only",
        "policy_name": "initial_right_rg1_restore_gate_select",
        "command": "SELECT",
        "policy_mode": "permissive",
        "role_ids": ["pitchlog_initial_fn_owner"],
        "using_predicate_id": None,
        "using_column": None,
        "using_expression": "singleton_id = 1",
        "with_check_predicate_id": None,
        "with_check_column": None,
        "with_check_expression": None,
    },
}


def build_initial_column_acl_declarations() -> dict[str, dict[str, object]]:
    """初期owner41列とapp旧12列の閉じた期待宣言を返す。"""
    from copy import deepcopy

    return deepcopy(_INITIAL_COLUMN_ACLS)


def is_initial_column_acl(declaration: Mapping[str, object]) -> bool:
    """権限・所有者・関数束縛を全field一致で照合する。"""
    key = declaration.get("expectation_id")
    return (
        declaration.get("grant_option") is False
        and isinstance(key, str)
        and key in _INITIAL_COLUMN_ACLS
        and dict(declaration) == _INITIAL_COLUMN_ACLS[key]
    )


def build_initial_policy_declarations() -> dict[str, dict[str, object]]:
    """初期owner17policyを既単一TENANT展開へ束縛して返す。"""
    from copy import deepcopy

    from pitchlog.authz.product_table_access import build_product_policy_declaration

    result = deepcopy(_INITIAL_POLICIES)
    for row in result.values():
        if row["table_id"] == "rg1_restore_gate":
            continue
        table_id = row["table_id"]
        if not isinstance(table_id, str) or row["command"] not in {
            "SELECT",
            "INSERT",
            "UPDATE",
        }:
            raise ValueError("初期tenant policyの固定表/commandが不正")
        tenant = build_product_policy_declaration(table_id, "tenant_owned")
        for side, required in (
            ("using", row["command"] in {"SELECT", "UPDATE"}),
            ("with_check", row["command"] in {"INSERT", "UPDATE"}),
        ):
            for field in ("predicate_id", "column"):
                key = f"{side}_{field}"
                expected = tenant[key] if required else None
                if row[key] != expected:
                    raise ValueError("初期tenant policyの述語/列束縛が不正")
            row[f"{side}_expression"] = (
                tenant[f"{side}_expression"] if required else None
            )
    return result


def initial_policy_expressions(
    declaration: Mapping[str, object],
) -> tuple[str | None, str | None]:
    """閉宣言の全fieldを検証し、空のTENANT式をcatalog期待へ流さない。"""
    expected = build_initial_policy_declarations()
    key = declaration.get("policy_id")
    if (
        not isinstance(key, str)
        or key not in expected
        or dict(declaration) != expected[key]
    ):
        raise ValueError("初期owner policyの表/主体/述語/実式が閉宣言と不一致")
    using = expected[key]["using_expression"]
    check = expected[key]["with_check_expression"]
    if (using is not None and not isinstance(using, str)) or (
        check is not None and not isinstance(check, str)
    ):
        raise ValueError("初期owner policy実式の型が不正")
    return using, check


def generate_initial_policy_sql(policy_id: str) -> str:
    """固定17policyだけを同じ宣言から生成する。"""
    if policy_id not in _INITIAL_POLICIES:
        raise ValueError("初期policyが閉集合にない")
    row = build_initial_policy_declarations()[policy_id]
    sql = (
        "-- ELEMENT-TYPE: policy\n"
        f"-- ELEMENT-ID: {policy_id}\n\n"
        f"CREATE POLICY {row['policy_name']} ON public.{row['table_id']}\n"
        f"AS PERMISSIVE FOR {row['command']} TO pitchlog_initial_fn_owner\n"
    )
    if row["using_expression"] is not None:
        sql += f"USING ({row['using_expression']})\n"
    if row["with_check_expression"] is not None:
        sql += f"WITH CHECK ({row['with_check_expression']})\n"
    return sql.rstrip() + ";\n"


def generate_initial_column_acl_sql(declaration: Mapping[str, object]) -> str:
    """appの表権限を剥奪し、新2列を除くexact列だけを付与する。"""
    if not (
        is_initial_column_acl(declaration) or is_enrollment_column_acl(declaration)
    ):
        raise ValueError("初期列ACLが閉集合にない")
    table = str(declaration["object_id"])
    column = str(declaration["column_id"])
    role = str(declaration["grantee_role_id"])
    privileges = declaration["privilege_ids"]
    assert isinstance(privileges, list)
    reset = (
        "REVOKE SELECT, INSERT, UPDATE ON TABLE public.recording_generations "
        "FROM pitchlog_app;\n"
        if role == "pitchlog_app" and column == "tenant_id"
        else ""
    )
    grants = ", ".join(f"{privilege} ({column})" for privilege in privileges)
    return (
        "-- ELEMENT-TYPE: column_acl_expectation\n"
        f"-- ELEMENT-ID: {declaration['expectation_id']}\n\n"
        + reset
        + f"GRANT {grants} ON TABLE public.{table} TO {role};\n"
    )


ENROLL_POLICY_ID = "POLICY:trusted_devices:initial_right_trusted_devices_insert"


def build_enrollment_column_acl_declarations() -> dict[str, dict[str, object]]:
    """既3IDの権限を保持し、INSERTだけを追加したoverlayを返す。"""
    from copy import deepcopy

    result = {}
    for column in ("tenant_id", "device_id", "credential_digest"):
        key = f"COLUMN-ACL:public:trusted_devices:{column}:pitchlog_initial_fn_owner"
        row = deepcopy(_INITIAL_COLUMN_ACLS[key])
        privileges = row["privilege_ids"]
        assert isinstance(privileges, list)
        privileges.append("INSERT")
        result[key] = row
    return result


def build_enrollment_policy_declarations() -> dict[str, dict[str, object]]:
    """既単一TENANT展開器によるINSERT WITH CHECK一件を返す。"""
    from copy import deepcopy

    from pitchlog.authz.product_table_access import build_product_policy_declaration

    row = deepcopy(
        _INITIAL_POLICIES[
            "POLICY:game_start_requests:initial_right_game_start_requests_insert"
        ]
    )
    row.update(
        policy_id=ENROLL_POLICY_ID,
        policy_name="initial_right_trusted_devices_insert",
        table_id="trusted_devices",
    )
    tenant = build_product_policy_declaration("trusted_devices", "tenant_owned")
    row["with_check_expression"] = tenant["with_check_expression"]
    return {ENROLL_POLICY_ID: row}


def enrollment_assets_present(asset: Mapping[str, object]) -> bool:
    """部分追加も新集合へ分類し、旧期待に紛れる欠落を拒否させる。"""
    from pitchlog.authz.product_function_acl import ENROLL_FUNCTION_ID

    for section, key, target in (
        ("functions", "function_id", ENROLL_FUNCTION_ID),
        ("policies", "policy_id", ENROLL_POLICY_ID),
    ):
        rows = asset.get(section)
        if isinstance(rows, list) and any(
            isinstance(row, dict) and row.get(key) == target for row in rows
        ):
            return True
    columns = asset.get("column_acl_expectations")
    ids = build_enrollment_column_acl_declarations()
    return isinstance(columns, list) and any(
        isinstance(row, dict)
        and row.get("expectation_id") in ids
        and isinstance(row.get("privilege_ids"), list)
        and "INSERT" in row["privilege_ids"]
        for row in columns
    )


def is_enrollment_column_acl(declaration: Mapping[str, object]) -> bool:
    """overlay3を全fieldで検査し、未知の権限追加を認めない。"""
    key = declaration.get("expectation_id")
    return isinstance(key, str) and dict(
        declaration
    ) == build_enrollment_column_acl_declarations().get(key)


def enrollment_policy_expressions(
    declaration: Mapping[str, object],
) -> tuple[str | None, str | None]:
    """新policyを全fieldで閉宣言に照合する。"""
    expected = build_enrollment_policy_declarations()[ENROLL_POLICY_ID]
    if dict(declaration) != expected:
        raise ValueError("端末登録policyの全fieldが不一致")
    value = expected["with_check_expression"]
    if not isinstance(value, str):
        raise ValueError("端末登録policy実式が不正")
    return None, value


def generate_enrollment_policy_sql() -> str:
    """Tenant CHECKを省略しない固定owner INSERT policyを生成する。"""
    row = build_enrollment_policy_declarations()[ENROLL_POLICY_ID]
    return (
        f"-- ELEMENT-TYPE: policy\n-- ELEMENT-ID: {ENROLL_POLICY_ID}\n\n"
        "CREATE POLICY initial_right_trusted_devices_insert ON public.trusted_devices\n"
        "AS PERMISSIVE FOR INSERT TO pitchlog_initial_fn_owner\n"
        f"WITH CHECK ({row['with_check_expression']});\n"
    )
