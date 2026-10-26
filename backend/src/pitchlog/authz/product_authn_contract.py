"""認証資産と実カタログに共用する独立した意味上の期待集合。"""

from __future__ import annotations

from typing import Any

INITIAL_AUTH_VERIFIER = "pitchlog_initial_auth_verifier"


def authn_function_grants(name: str, args: str) -> list[dict[str, object]]:
    """旧付与先を保持し、検証一関数だけ専用主体を追加する。"""
    grantee = AUTHN_FUNCTION_GRANTEES[(name, args)]
    result: list[dict[str, object]] = (
        []
        if grantee is None
        else [dict(grantee=grantee, privilege="EXECUTE", grantable=False)]
    )
    if (name, args) == ("verify_token", "uuid"):
        result.append(
            dict(grantee=INITIAL_AUTH_VERIFIER, privilege="EXECUTE", grantable=False)
        )
    return result


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
    ("observe_rate_limit_counters", ""): "pitchlog_management_fn_owner",
    ("password_policy_ok", "text"): None,
    ("setting_positive_integer", "text"): None,
    ("record_failure", "text, bigint, bigint, bigint, boolean"): None,
}
AUTHN_SCHEMA_USERS = {
    "authn": frozenset(
        {
            "pitchlog_app",
            "pitchlog_management_fn_owner",
            AUTHN_OWNER,
            INITIAL_AUTH_VERIFIER,
        }
    ),
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
    validate_initial_verifier_declarations(asset)
    functions = {
        (row.get("function_name"), row.get("identity_args")): row
        for row in asset["functions"]
        if row.get("schema_name") == "authn"
    }
    if set(functions) != set(AUTHN_FUNCTION_GRANTEES):
        raise ValueError("認証関数の署名が独立の期待集合と不一致")
    for key in AUTHN_FUNCTION_GRANTEES:
        row = functions[key]
        grants = row.get("acl_expectations")
        expected_grants = authn_function_grants(*key)
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


def _verifier_rows(asset: dict[str, Any], key: str) -> list[dict[str, Any]]:
    """新主体の閉宣言検査へ渡すobject配列だけを受け付ける。"""
    rows = asset.get(key)
    if type(rows) is not list or any(type(r) is not dict for r in rows):
        raise ValueError("専用verifier metadata配列の形が不正")
    return rows


def validate_initial_verifier_declarations(asset: dict[str, Any]) -> None:
    """新主体のmetadata全fieldを閉じ、実観測の代替にはしない。"""
    from pitchlog.authz.initial_start_sql import _exact_value

    role = INITIAL_AUTH_VERIFIER
    verify_rows = [
        r
        for r in _verifier_rows(asset, "functions")
        if r.get("function_id") == "FUNCTION:authn:verify_token(uuid)"
    ]
    expected_verify = dict(
        function_id="FUNCTION:authn:verify_token(uuid)",
        schema_name="authn",
        function_name="verify_token",
        identity_args="uuid",
        function_kind="definer",
        owner_role_id=AUTHN_OWNER,
        language="plpgsql",
        returns="record",
        security_mode="definer",
        volatility="volatile",
        search_path=["pg_catalog", "pg_temp"],
        acl_expectations=authn_function_grants("verify_token", "uuid"),
        revoked_acl_expectations=[
            dict(grantee="PUBLIC", privilege="EXECUTE", grantable=False)
        ],
    )
    if not _exact_value(verify_rows, [expected_verify]):
        raise ValueError("専用verifierのverify_token署名/宣言全field/exact集合が不一致")
    from pitchlog.authz.product_role_contract import expected_product_roles

    roles = [r for r in _verifier_rows(asset, "roles") if r.get("role_id") == role]
    if not _exact_value(
        roles, [dict(role_id=role, **expected_product_roles(asset)[role])]
    ):
        raise ValueError("専用verifierのrole全属性/exact集合が不一致")
    for row in _verifier_rows(asset, "membership_edges"):
        if role in row.values():
            raise ValueError("専用verifierのmembershipは0が必要")
    for group in ("acl_expectations", "column_acl_expectations"):
        if any(
            row.get("grantee_role_id") == role for row in _verifier_rows(asset, group)
        ):
            raise ValueError("専用verifierの表列ACLは0が必要")
    for row in _verifier_rows(asset, "policies"):
        if role in row.get("role_ids", []):
            raise ValueError("専用verifierのpolicyは0が必要")
    for row in _verifier_rows(asset, "functions"):
        grants = _verifier_rows(row, "acl_expectations")
        revoked = _verifier_rows(row, "revoked_acl_expectations")
        selected = [g for g in grants if g.get("grantee") == role]
        deny = [g for g in revoked if g.get("grantee") == role]
        expected = (
            [dict(grantee=role, privilege="EXECUTE", grantable=False)]
            if row.get("function_id") == "FUNCTION:authn:verify_token(uuid)"
            else []
        )
        if (
            row.get("owner_role_id") == role
            or not _exact_value(selected, expected)
            or deny
        ):
            raise ValueError("専用verifierの関数ACL/所有が不一致")
    for row in _verifier_rows(asset, "schemas"):
        selected = [
            g
            for g in _verifier_rows(row, "acl_expectations")
            if g.get("grantee") == role
        ]
        denied = [
            g
            for g in _verifier_rows(row, "revoked_acl_expectations")
            if g.get("grantee") == role
        ]
        is_authn = row.get("schema_id") == "authn"
        if (
            row.get("owner") == role
            or not _exact_value(
                selected,
                [dict(grantee=role, privilege="USAGE", grantable=False)]
                if is_authn
                else [],
            )
            or not _exact_value(
                denied,
                [dict(grantee=role, privilege="CREATE", grantable=False)]
                if is_authn
                else [],
            )
        ):
            raise ValueError("専用verifierのschema ACL/所有が不一致")
    for row in _verifier_rows(asset, "tables"):
        if row.get("owner") == role or row.get("owner_role_id") == role:
            raise ValueError("専用verifierの表所有は0が必要")
    for row in _verifier_rows(asset, "databases"):
        grants = [
            g
            for g in _verifier_rows(row, "acl_expectations")
            if g.get("grantee") == role
        ]
        denied = [
            g
            for g in _verifier_rows(row, "revoked_acl_expectations")
            if g.get("grantee") == role
        ]
        if (
            row.get("owner") == role
            or not _exact_value(
                grants, [dict(grantee=role, privilege="CONNECT", grantable=False)]
            )
            or not _exact_value(
                denied,
                [
                    dict(grantee=role, privilege=p, grantable=False)
                    for p in ("CREATE", "TEMPORARY")
                ],
            )
        ):
            raise ValueError("専用verifierのdatabase ACL/所有が不一致")
    if role not in AUTHN_SCHEMA_USERS["authn"]:
        raise ValueError("専用verifierの単一認証宣言が不整合")
