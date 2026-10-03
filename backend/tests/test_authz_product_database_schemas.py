"""製品認可DDLのDB・スキーマ所有者とACL閉包を検査する。"""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pitchlog.authz.asset_spec import PRODUCT_SPEC
from pitchlog.authz.ddl import DDLStatement, generate_authz_ddl

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_BODY_CHECKER = _REPOSITORY_ROOT / "scripts/check_authz_function_bodies.py"
_CATALOG_CHECKER = _REPOSITORY_ROOT / "scripts/check_authz_catalog.py"
_EXPECTED_DATABASE = {
    "name_expression": "current_database()",
    "owner": "pitchlog_owner",
    "acl_expectations": {("pitchlog_app", "CONNECT", False)},
    "revoked_acl_expectations": {
        ("PUBLIC", "CONNECT", False),
        ("PUBLIC", "TEMPORARY", False),
        ("pitchlog_app", "CREATE", False),
        ("pitchlog_app", "TEMPORARY", False),
    },
}
_EXPECTED_SCHEMAS = {
    "public": {
        "schema_name": "public",
        "creation": "existing",
        "owner": "pitchlog_owner",
        "ownership_path": "pg_database_owner",
        "acl_expectations": {
            ("pitchlog_app", "USAGE", False),
            ("pitchlog_shared_fn_owner", "USAGE", False),
        },
        "revoked_acl_expectations": {
            ("PUBLIC", "USAGE", False),
            ("PUBLIC", "CREATE", False),
            ("pitchlog_app", "CREATE", False),
            ("pitchlog_shared_fn_owner", "CREATE", False),
        },
    },
    "authz_private": {
        "schema_name": "authz_private",
        "creation": "product_ddl",
        "owner": "pitchlog_shared_fn_owner",
        "ownership_path": "direct",
        "acl_expectations": set(),
        "revoked_acl_expectations": {
            ("PUBLIC", "USAGE", False),
            ("PUBLIC", "CREATE", False),
            ("pitchlog_app", "USAGE", False),
            ("pitchlog_app", "CREATE", False),
        },
    },
}


def _load_catalog_checker() -> Any:
    """静的検査を独立したモジュール名で読み込む。"""
    module_spec = importlib.util.spec_from_file_location(
        "check_authz_catalog_product_database_schemas_under_test",
        _CATALOG_CHECKER,
    )
    assert module_spec is not None and module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    sys.modules[module_spec.name] = module
    module_spec.loader.exec_module(module)
    return module


_catalog_checker = _load_catalog_checker()


def _read_product_asset() -> dict[str, Any]:
    """製品DDL資産をJSON objectとして読む。"""
    value = json.loads(
        (_REPOSITORY_ROOT / PRODUCT_SPEC.ddl_elements_path).read_text(encoding="utf-8")
    )
    assert isinstance(value, dict)
    return value


def _validate_product_asset(asset: dict[str, Any]) -> dict[str, object]:
    """製品DDL資産を静的検査へ渡す。"""
    return _catalog_checker.validate_ddl_elements(
        asset,
        _REPOSITORY_ROOT,
        PRODUCT_SPEC,
    )


def _acl_set(value: object) -> set[tuple[str, str, bool]]:
    """ACL宣言を比較用の3要素集合へ変換する。"""
    assert isinstance(value, list)
    result: set[tuple[str, str, bool]] = set()
    for row in value:
        assert isinstance(row, dict)
        assert set(row) == {"grantee", "privilege", "grantable"}
        result.add((str(row["grantee"]), str(row["privilege"]), row["grantable"]))
    return result


def _normalized_object(row: dict[str, Any], id_field: str) -> dict[str, object]:
    """ID以外の宣言をACL集合付きで正規化する。"""
    return {
        key: _acl_set(value) if key.endswith("acl_expectations") else value
        for key, value in row.items()
        if key != id_field
    }


def _statement_map(
    statements: tuple[DDLStatement, ...],
) -> dict[tuple[str, str], str]:
    """生成結果を要素種別とIDで引ける形へ変換する。"""
    result = {
        (statement.element_type, statement.element_id): statement.sql
        for statement in statements
    }
    assert len(result) == len(statements)
    return result


def _find_object(asset: dict[str, Any], section: str, object_id: str) -> dict[str, Any]:
    """指定セクションからIDが一致する宣言を返す。"""
    id_field = "database_id" if section == "databases" else "schema_id"
    return next(row for row in asset[section] if row[id_field] == object_id)


def _move_acl(
    row: dict[str, Any],
    grantee: str,
    privilege: str,
    *,
    remove_revocation: bool = True,
) -> None:
    """剥奪宣言を任意に外して同じACLの付与宣言を足す。"""
    if remove_revocation:
        row["revoked_acl_expectations"] = [
            entry
            for entry in row["revoked_acl_expectations"]
            if (entry["grantee"], entry["privilege"]) != (grantee, privilege)
        ]
    row["acl_expectations"].append(
        {"grantee": grantee, "privilege": privilege, "grantable": False}
    )


def _mutate_database_public_connect(asset: dict[str, Any]) -> None:
    """DBへPUBLICのCONNECTを戻す。"""
    _move_acl(_find_object(asset, "databases", "current_database"), "PUBLIC", "CONNECT")


def _mutate_database_app_create(asset: dict[str, Any]) -> None:
    """アプリ用ロールへDBのCREATEを与える。"""
    _move_acl(
        _find_object(asset, "databases", "current_database"),
        "pitchlog_app",
        "CREATE",
    )


def _mutate_database_app_temporary(asset: dict[str, Any]) -> None:
    """アプリ用ロールへDBのTEMPORARYを与える。"""
    _move_acl(
        _find_object(asset, "databases", "current_database"),
        "pitchlog_app",
        "TEMPORARY",
    )


def _mutate_public_usage(asset: dict[str, Any]) -> None:
    """PublicスキーマへPUBLICのUSAGEを戻す。"""
    _move_acl(_find_object(asset, "schemas", "public"), "PUBLIC", "USAGE")


def _mutate_remove_public_create_revocation(asset: dict[str, Any]) -> None:
    """PublicスキーマのCREATE剥奪宣言を消す。"""
    row = _find_object(asset, "schemas", "public")
    row["revoked_acl_expectations"] = [
        entry
        for entry in row["revoked_acl_expectations"]
        if (entry["grantee"], entry["privilege"]) != ("PUBLIC", "CREATE")
    ]


def _mutate_authz_private_create(asset: dict[str, Any]) -> None:
    """Authz_privateスキーマへPUBLICのCREATEを与える。"""
    _move_acl(
        _find_object(asset, "schemas", "authz_private"),
        "PUBLIC",
        "CREATE",
    )


def _mutate_authz_private_app_usage(asset: dict[str, Any]) -> None:
    """アプリ用ロールへauthz_privateのUSAGEを与える。"""
    _move_acl(
        _find_object(asset, "schemas", "authz_private"),
        "pitchlog_app",
        "USAGE",
    )


def test_product_database_and_schema_assets_match_design() -> None:
    """DB・2スキーマの所有者とACLがdesign.md 2-1へ完全一致する。"""
    asset = _read_product_asset()
    _validate_product_asset(asset)

    databases = asset["databases"]
    schemas = asset["schemas"]
    assert isinstance(databases, list) and len(databases) == 1
    assert isinstance(schemas, list) and len(schemas) == 2
    assert _normalized_object(databases[0], "database_id") == _EXPECTED_DATABASE
    assert {
        str(row["schema_id"]): _normalized_object(row, "schema_id") for row in schemas
    } == _EXPECTED_SCHEMAS

    sql_by_element = _statement_map(generate_authz_ddl(_REPOSITORY_ROOT, PRODUCT_SPEC))
    database_sql = sql_by_element[("database", "current_database")]
    assert "pg_catalog.current_database()" in database_sql
    assert "ALTER DATABASE %I OWNER TO pitchlog_owner" in database_sql
    assert "REVOKE ALL PRIVILEGES ON DATABASE %I" in database_sql
    assert "GRANT CONNECT ON DATABASE %I TO pitchlog_app" in database_sql
    public_sql = sql_by_element[("schema", "public")]
    assert "ALTER SCHEMA public OWNER TO pg_database_owner" in public_sql
    assert "REVOKE ALL PRIVILEGES ON SCHEMA public" in public_sql
    assert (
        "GRANT USAGE ON SCHEMA public TO pitchlog_app, pitchlog_shared_fn_owner"
        in public_sql
    )
    private_sql = sql_by_element[("schema", "authz_private")]
    assert "CREATE SCHEMA IF NOT EXISTS authz_private" in private_sql
    assert "ALTER SCHEMA authz_private OWNER TO pitchlog_shared_fn_owner" in private_sql
    assert "REVOKE ALL PRIVILEGES ON SCHEMA authz_private" in private_sql

    body_result = subprocess.run(
        [sys.executable, str(_BODY_CHECKER), "--asset-spec", "product"],
        cwd=_REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert body_result.returncode == 0, body_result.stderr


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(_mutate_database_public_connect, id="database-public-connect"),
        pytest.param(_mutate_database_app_create, id="database-app-create"),
        pytest.param(_mutate_database_app_temporary, id="database-app-temporary"),
        pytest.param(_mutate_public_usage, id="public-public-usage"),
        pytest.param(
            _mutate_remove_public_create_revocation,
            id="public-create-revocation-removed",
        ),
        pytest.param(_mutate_authz_private_create, id="authz-private-create"),
        pytest.param(
            _mutate_authz_private_app_usage,
            id="authz-private-app-usage",
        ),
    ],
)
def test_product_database_and_schema_acl_mutations_are_rejected(
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    """正常資産を確認後、DB・スキーマACLの各変異を拒否する。"""
    asset = _read_product_asset()
    _validate_product_asset(asset)
    mutated = copy.deepcopy(asset)
    mutate(mutated)

    with pytest.raises(_catalog_checker.CatalogError):
        _validate_product_asset(mutated)
