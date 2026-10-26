"""製品ロールと移行バッチ用ロールの独立した意味契約。"""

from __future__ import annotations

from typing import Any


def _role(
    creation: str,
    *,
    login: bool,
    bypass_rls: bool,
    inherit: bool = False,
) -> dict[str, object]:
    """設計書 3-2 節のロール属性を組み立てる。"""
    return {
        "creation": creation,
        "superuser": False,
        "bypass_rls": bypass_rls,
        "login": login,
        "create_role": False,
        "create_db": False,
        "replication": False,
        "inherit": inherit,
    }


_PROVISIONAL_PRODUCT_ROLES = {
    "pitchlog_owner": _role("external_applicator", login=True, bypass_rls=False),
    "pitchlog_app": _role("product_ddl", login=True, bypass_rls=False),
    "pitchlog_shared_fn_owner": _role("product_ddl", login=False, bypass_rls=True),
    "pitchlog_management_fn_owner": _role("product_ddl", login=False, bypass_rls=True),
}
_PRODUCT_ROLES = {
    **_PROVISIONAL_PRODUCT_ROLES,
    "pitchlog_initial_auth_verifier": _role(
        "product_ddl", login=True, bypass_rls=False
    ),
    "pitchlog_auth_fn_owner": _role("product_ddl", login=False, bypass_rls=True),
    "pitchlog_rg1_fn_owner": _role("product_ddl", login=False, bypass_rls=False),
    "pitchlog_rule_resolution_fn_owner": _role(
        "product_ddl", login=False, bypass_rls=True
    ),
}
_PRODUCT_ROLES.update(
    {
        "pitchlog_rg1_control_owner": _role(
            "product_ddl", login=False, bypass_rls=False
        ),
        "pitchlog_rg1_control_actor": _role(
            "product_ddl", login=True, bypass_rls=False
        ),
        "pitchlog_ledger_identity_owner": _role(
            "product_ddl",
            login=False,
            bypass_rls=False,
            inherit=True,
        ),
        "pitchlog_ledger_identity_probe": _role(
            "product_ddl", login=True, bypass_rls=False
        ),
        "pitchlog_initial_actor": _role("product_ddl", login=True, bypass_rls=False),
        "pitchlog_initial_fn_owner": _role(
            "product_ddl", login=False, bypass_rls=False
        ),
    }
)
MIGRATION_BATCH_ROLE_ATTRIBUTES = {
    "superuser": False,
    "bypass_rls": True,
    "login": True,
    "create_role": False,
    "create_db": False,
    "replication": False,
    "inherit": False,
}


def expected_product_roles(asset: dict[str, Any]) -> dict[str, dict[str, object]]:
    """既存14ロールへ完全な初球profileの追加3ロールだけを加える。

    Args:
        asset: 完全な初球profileの有無を検査する製品資産。
    """
    from pitchlog.authz.first_ball_product import ADDITIONS, validate

    result = dict(_PRODUCT_ROLES)
    if validate(asset):
        result.update(
            {
                r["role_id"]: {k: v for k, v in r.items() if k != "role_id"}
                for r in ADDITIONS["roles"]
            }
        )
    return result


def expected_provisional_product_roles() -> dict[str, dict[str, object]]:
    """過去の未発効契約を検査するための 4 ロールを返す。"""
    return dict(_PROVISIONAL_PRODUCT_ROLES)


_LIFECYCLE_ROLE_IDS = frozenset(
    {
        "pitchlog_initial_auth_verifier",
        "pitchlog_rg1_control_owner",
        "pitchlog_rg1_control_actor",
        "pitchlog_ledger_identity_owner",
        "pitchlog_ledger_identity_probe",
        "pitchlog_initial_actor",
        "pitchlog_initial_fn_owner",
    }
)
_ROLE_SQL_ATTRIBUTES = (
    ("superuser", "rolsuper", "SUPERUSER", "NOSUPERUSER"),
    ("bypass_rls", "rolbypassrls", "BYPASSRLS", "NOBYPASSRLS"),
    ("login", "rolcanlogin", "LOGIN", "NOLOGIN"),
    ("create_role", "rolcreaterole", "CREATEROLE", "NOCREATEROLE"),
    ("create_db", "rolcreatedb", "CREATEDB", "NOCREATEDB"),
    ("replication", "rolreplication", "REPLICATION", "NOREPLICATION"),
    ("inherit", "rolinherit", "INHERIT", "NOINHERIT"),
)


def generate_lifecycle_role_sql(role_id: str) -> str:
    """新6ロールだけを意味契約から厳密な再適用ガード付きで生成する。

    Args:
        role_id: 閉登録された新6ロールの識別子。

    Returns:
        不存在時だけ作成し、既存の属性と両向membershipを照合するSQL。

    Raises:
        ValueError: 閉登録外のロールを指定した場合。
    """
    if role_id not in _LIFECYCLE_ROLE_IDS:
        raise ValueError("再適用ガードの対象は閉登録された新6ロールだけです")
    role = _PRODUCT_ROLES[role_id]
    conditions = "\n".join(
        f"              AND {'' if role[attribute] else 'NOT '}r.{catalog_name}"
        for attribute, catalog_name, _, _ in _ROLE_SQL_ATTRIBUTES
    )
    attributes = " ".join(
        enabled if role[attribute] else disabled
        for attribute, _, enabled, disabled in _ROLE_SQL_ATTRIBUTES
    )
    return f"""-- ELEMENT-TYPE: role
-- ELEMENT-ID: {role_id}

DO $authz$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles
        WHERE rolname = '{role_id}'
    ) THEN
        IF NOT EXISTS (
            SELECT 1 FROM pg_catalog.pg_roles r
            WHERE r.rolname = '{role_id}'
{conditions}
              AND NOT EXISTS (
                  SELECT 1 FROM pg_catalog.pg_auth_members m
                  WHERE m.roleid = r.oid OR m.member = r.oid
              )
        ) THEN
            RAISE EXCEPTION 'lifecycle role collision: {role_id}';
        END IF;
    ELSE
        CREATE ROLE {role_id} WITH
            {attributes};
    END IF;
END;
$authz$;
"""
