"""製品ロールと移行バッチ用ロールの独立した意味契約。"""

from __future__ import annotations

from typing import Any


def _role(creation: str, *, login: bool, bypass_rls: bool) -> dict[str, object]:
    """設計書 3-2 節のロール属性を組み立てる。"""
    return {
        "creation": creation,
        "superuser": False,
        "bypass_rls": bypass_rls,
        "login": login,
        "create_role": False,
        "create_db": False,
        "replication": False,
        "inherit": False,
    }


_BASE_PRODUCT_ROLES = {
    "pitchlog_owner": _role("external_applicator", login=True, bypass_rls=False),
    "pitchlog_app": _role("product_ddl", login=True, bypass_rls=False),
    "pitchlog_shared_fn_owner": _role("product_ddl", login=False, bypass_rls=True),
    "pitchlog_management_fn_owner": _role("product_ddl", login=False, bypass_rls=True),
}
_AUTH_FUNCTION_OWNER = _role("product_ddl", login=False, bypass_rls=True)
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
    """認証スキーマの導入段階に応じた製品ロールの独立集合を返す。

    ロール配列を段階判定に使わないため、認証関数所有ロールを削除しても
    旧段階へ戻らない。
    """
    schemas = asset.get("schemas")
    functions = asset.get("functions")
    auth_schema_declared = isinstance(schemas, list) and any(
        isinstance(row, dict) and row.get("schema_name") in {"authn", "authn_crypto"}
        for row in schemas
    )
    auth_function_declared = isinstance(functions, list) and any(
        isinstance(row, dict)
        and (
            row.get("schema_name") in {"authn", "authn_crypto"}
            or row.get("owner_role_id") == "pitchlog_auth_fn_owner"
        )
        for row in functions
    )
    expected = dict(_BASE_PRODUCT_ROLES)
    if auth_schema_declared or auth_function_declared:
        expected["pitchlog_auth_fn_owner"] = _AUTH_FUNCTION_OWNER
    return expected
