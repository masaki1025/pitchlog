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


_PROVISIONAL_PRODUCT_ROLES = {
    "pitchlog_owner": _role("external_applicator", login=True, bypass_rls=False),
    "pitchlog_app": _role("product_ddl", login=True, bypass_rls=False),
    "pitchlog_shared_fn_owner": _role("product_ddl", login=False, bypass_rls=True),
    "pitchlog_management_fn_owner": _role("product_ddl", login=False, bypass_rls=True),
}
_PRODUCT_ROLES = {
    **_PROVISIONAL_PRODUCT_ROLES,
    "pitchlog_auth_fn_owner": _role("product_ddl", login=False, bypass_rls=True),
}
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
    """資産の有無に依存しない、製品状態の 5 ロールを返す。

    Args:
        asset: 呼出側との互換性のために受け取る製品資産。判定には使わない。
    """
    del asset
    return dict(_PRODUCT_ROLES)


def expected_provisional_product_roles() -> dict[str, dict[str, object]]:
    """過去の未発効契約を検査するための 4 ロールを返す。"""
    return dict(_PROVISIONAL_PRODUCT_ROLES)
