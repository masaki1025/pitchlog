"""認証資産と実カタログに共用する独立した意味上の期待集合。"""

from __future__ import annotations

from typing import Any

AUTHN_OWNER = "pitchlog_auth_fn_owner"
AUTHN_EXTENSION = ("pgcrypto", "authn_crypto")
AUTHN_FUNCTION_GRANTEES = {
    ("login_attempt", "text, text, text"): "pitchlog_app",
    ("verify_token", "uuid"): "pitchlog_app",
    ("logout", "uuid"): "pitchlog_app",
    ("change_password", "uuid, text, text"): "pitchlog_app",
    ("issue_initial_password", "uuid, text"): "pitchlog_management_fn_owner",
    ("reset_password", "uuid, text"): "pitchlog_management_fn_owner",
    ("revoke_tenant_tokens", "uuid"): "pitchlog_management_fn_owner",
    ("record_admin_login_failure", "text"): "pitchlog_management_fn_owner",
    ("password_policy_ok", "text"): None,
    ("setting_positive_integer", "text"): None,
    ("record_failure", "text, bigint, bigint, bigint, boolean"): None,
}
AUTHN_SCHEMA_USERS = {
    "authn": frozenset({"pitchlog_app", "pitchlog_management_fn_owner", AUTHN_OWNER}),
    "authn_crypto": frozenset({AUTHN_OWNER}),
}
AUTHN_TABLE_GRANTS = {
    "tenant_auth_subjects": frozenset({"SELECT", "INSERT"}),
    "tenant_credentials": frozenset({"SELECT", "INSERT", "UPDATE"}),
    "tenant_tokens": frozenset({"SELECT", "INSERT", "UPDATE"}),
    "rate_limit_counters": frozenset({"SELECT", "INSERT", "UPDATE"}),
}
AUTHN_COLUMN_GRANTS = {
    ("tenants", "id"),
    ("tenants", "name_normalized"),
    ("tenants", "enabled"),
    ("tenants", "retired_at"),
    ("system_settings", "key"),
    ("system_settings", "value"),
}


def validate_authn_asset(asset: dict[str, Any]) -> None:
    """認証の関数群・付与先・スキーマ・拡張を独立集合へ照合する。"""
    functions = {
        (row.get("function_name"), row.get("identity_args")): row
        for row in asset["functions"]
        if row.get("schema_name") == "authn"
    }
    if set(functions) != set(AUTHN_FUNCTION_GRANTEES):
        raise ValueError("認証関数の署名が独立の期待集合と不一致")
    for key, grantee in AUTHN_FUNCTION_GRANTEES.items():
        row = functions[key]
        grants = row.get("acl_expectations")
        expected_grants = (
            []
            if grantee is None
            else [{"grantee": grantee, "privilege": "EXECUTE", "grantable": False}]
        )
        if (
            row.get("function_kind") != "definer"
            or row.get("owner_role_id") != AUTHN_OWNER
            or row.get("security_mode") != "definer"
            or row.get("search_path") != ["pg_catalog", "pg_temp"]
            or grants != expected_grants
            or row.get("revoked_acl_expectations")
            != [{"grantee": "PUBLIC", "privilege": "EXECUTE", "grantable": False}]
        ):
            raise ValueError(f"認証関数の所有・属性・付与先が不正: {key}")
    schemas = {
        row.get("schema_name"): row
        for row in asset["schemas"]
        if row.get("schema_name") in AUTHN_SCHEMA_USERS
    }
    if set(schemas) != set(AUTHN_SCHEMA_USERS):
        raise ValueError("認証スキーマの集合が不正")
    for name, users in AUTHN_SCHEMA_USERS.items():
        row = schemas[name]
        grants = {
            (entry.get("grantee"), entry.get("privilege"), entry.get("grantable"))
            for entry in row.get("acl_expectations", [])
        }
        revoked = {
            (entry.get("grantee"), entry.get("privilege"), entry.get("grantable"))
            for entry in row.get("revoked_acl_expectations", [])
        }
        if (
            row.get("creation") != "product_ddl"
            or row.get("owner") != "pitchlog_owner"
            or row.get("ownership_path") != "direct"
            or grants != {(user, "USAGE", False) for user in users}
            or revoked
            != {("PUBLIC", "USAGE", False), ("PUBLIC", "CREATE", False)}
            | {(user, "CREATE", False) for user in users}
        ):
            raise ValueError(f"認証スキーマの所有・ACLが不正: {name}")
    extensions = {
        (row.get("extension_name"), row.get("schema_name"))
        for row in asset.get("extensions", [])
    }
    if extensions != {AUTHN_EXTENSION}:
        raise ValueError("認証拡張の所属が不正")
    public = next(row for row in asset["schemas"] if row.get("schema_name") == "public")
    if {"grantee": AUTHN_OWNER, "privilege": "USAGE", "grantable": False} not in public[
        "acl_expectations"
    ]:
        raise ValueError("認証関数所有ロールの public USAGE が無い")
    normalizer = next(
        row
        for row in asset["functions"]
        if row.get("function_id") == "FUNCTION:public:authn_normalize_team_name(text)"
    )
    if {
        "grantee": AUTHN_OWNER,
        "privilege": "EXECUTE",
        "grantable": False,
    } not in normalizer["acl_expectations"]:
        raise ValueError("認証関数所有ロールの正規化関数 EXECUTE が無い")
    table_grants = {
        row["object_id"]: frozenset(row["privilege_ids"])
        for row in asset["acl_expectations"]
        if row.get("grantee_role_id") == AUTHN_OWNER
    }
    if table_grants != AUTHN_TABLE_GRANTS:
        raise ValueError("認証関数所有ロールの表 ACL が独立集合と不一致")
    column_grants = {
        (row["object_id"], row["column_id"])
        for row in asset["column_acl_expectations"]
        if row.get("grantee_role_id") == AUTHN_OWNER
        and row.get("privilege_ids") == ["SELECT"]
        and row.get("grant_option") is False
    }
    if column_grants != AUTHN_COLUMN_GRANTS:
        raise ValueError("認証関数所有ロールの列 ACL が独立集合と不一致")
