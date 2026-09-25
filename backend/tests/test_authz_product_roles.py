"""製品認可DDLのロール属性とmembership閉包を検査する。"""

from __future__ import annotations

import copy
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

import pytest

from pitchlog.authz.asset_spec import PRODUCT_SPEC
from pitchlog.authz.ddl import DDLStatement, generate_authz_ddl

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_BODY_CHECKER = _REPOSITORY_ROOT / "scripts/check_authz_function_bodies.py"
_CATALOG_CHECKER = _REPOSITORY_ROOT / "scripts/check_authz_catalog.py"
_ATTRIBUTE_ORDER = (
    "superuser",
    "bypass_rls",
    "login",
    "create_role",
    "create_db",
    "replication",
    "inherit",
)
_SQL_ATTRIBUTE_TOKENS = {
    "superuser": ("SUPERUSER", "NOSUPERUSER"),
    "bypass_rls": ("BYPASSRLS", "NOBYPASSRLS"),
    "login": ("LOGIN", "NOLOGIN"),
    "create_role": ("CREATEROLE", "NOCREATEROLE"),
    "create_db": ("CREATEDB", "NOCREATEDB"),
    "replication": ("REPLICATION", "NOREPLICATION"),
    "inherit": ("INHERIT", "NOINHERIT"),
}
_EXPECTED_ROLES: dict[str, dict[str, object]] = {
    "pitchlog_owner": {
        "creation": "external_applicator",
        "superuser": False,
        "bypass_rls": False,
        "login": True,
        "create_role": False,
        "create_db": False,
        "replication": False,
        "inherit": False,
    },
    "pitchlog_app": {
        "creation": "product_ddl",
        "superuser": False,
        "bypass_rls": False,
        "login": True,
        "create_role": False,
        "create_db": False,
        "replication": False,
        "inherit": False,
    },
    "pitchlog_shared_fn_owner": {
        "creation": "product_ddl",
        "superuser": False,
        "bypass_rls": True,
        "login": False,
        "create_role": False,
        "create_db": False,
        "replication": False,
        "inherit": False,
    },
    "pitchlog_management_fn_owner": {
        "creation": "product_ddl",
        "superuser": False,
        "bypass_rls": True,
        "login": False,
        "create_role": False,
        "create_db": False,
        "replication": False,
        "inherit": False,
    },
}
_CONNECTION_STRING_RE = re.compile(
    r"(?:[a-z][a-z0-9+.-]*://|\b(?:host|dbname|user|port)=)",
    re.IGNORECASE,
)


def _load_catalog_checker() -> Any:
    """静的検査を独立したモジュール名で読み込む。"""
    module_spec = importlib.util.spec_from_file_location(
        "check_authz_catalog_product_roles_under_test",
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


def _run_checker(script: Path) -> subprocess.CompletedProcess[str]:
    """製品specを指定して静的検査CLIを実行する。"""
    return subprocess.run(
        [sys.executable, str(script), "--asset-spec", "product"],
        cwd=_REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _statement_by_role(
    statements: tuple[DDLStatement, ...],
) -> dict[str, DDLStatement]:
    """生成結果をロールIDで一意に引ける形へ変換する。"""
    role_statements = tuple(
        statement for statement in statements if statement.element_type == "role"
    )
    result = {statement.element_id: statement for statement in role_statements}
    assert len(result) == len(role_statements)
    return result


def _mutate_app_bypass_rls(asset: dict[str, Any]) -> None:
    """アプリ用ロールへBYPASSRLSを付ける。"""
    next(row for row in asset["roles"] if row["role_id"] == "pitchlog_app")[
        "bypass_rls"
    ] = True


def _mutate_function_owner_login(asset: dict[str, Any]) -> None:
    """共有関数所有ロールへLOGINを付ける。"""
    next(row for row in asset["roles"] if row["role_id"] == "pitchlog_shared_fn_owner")[
        "login"
    ] = True


def _mutate_missing_attribute(asset: dict[str, Any]) -> None:
    """アプリ用ロールから7属性の1つを除く。"""
    del next(row for row in asset["roles"] if row["role_id"] == "pitchlog_app")[
        "inherit"
    ]


def _mutate_membership_edge(asset: dict[str, Any]) -> None:
    """製品ロールへoption付きmembershipの辺を足す。"""
    asset["membership_edges"].append(
        {
            "role_id": "pitchlog_shared_fn_owner",
            "member_id": "pitchlog_app",
            "admin_option": False,
            "set_option": True,
            "inherit_option": False,
        }
    )


def test_product_role_assets_match_design_and_all_readers_accept_them() -> None:
    """4ロールの宣言とSQLが設計の属性表へ完全一致する。"""
    asset = _read_product_asset()
    assert _validate_product_asset(asset) == {
        "scope_status": "product_configuration",
        "product_role_count": 4,
    }
    role_rows = asset["roles"]
    assert isinstance(role_rows, list)
    actual_roles = {
        str(row["role_id"]): {
            key: value for key, value in row.items() if key != "role_id"
        }
        for row in role_rows
    }
    assert actual_roles == _EXPECTED_ROLES
    assert asset["permanent_privileged_role_ids"] == ["pitchlog_owner"]
    assert asset["membership_edges"] == []

    statements = generate_authz_ddl(_REPOSITORY_ROOT, PRODUCT_SPEC)
    statements_by_role = _statement_by_role(statements)
    assert set(statements_by_role) == set(_EXPECTED_ROLES)
    for role_id, expected in _EXPECTED_ROLES.items():
        sql = statements_by_role[role_id].sql
        matches = re.findall(
            rf"ALTER ROLE {re.escape(role_id)} WITH\s+([^;]+);",
            sql,
            flags=re.DOTALL,
        )
        assert len(matches) == 1
        assert tuple(matches[0].split()) == tuple(
            _SQL_ATTRIBUTE_TOKENS[attribute][not bool(expected[attribute])]
            for attribute in _ATTRIBUTE_ORDER
        )
        create_count = len(re.findall(rf"\bCREATE ROLE {re.escape(role_id)};", sql))
        assert create_count == (0 if role_id == "pitchlog_owner" else 1)
        if role_id != "pitchlog_owner":
            assert "END;\n$authz$;" in sql

    body_result = _run_checker(_BODY_CHECKER)
    catalog_result = _run_checker(_CATALOG_CHECKER)
    assert body_result.returncode == 0, body_result.stderr
    assert catalog_result.returncode == 0, catalog_result.stderr


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(_mutate_app_bypass_rls, id="app-bypassrls"),
        pytest.param(_mutate_function_owner_login, id="function-owner-login"),
        pytest.param(_mutate_missing_attribute, id="missing-attribute"),
        pytest.param(_mutate_membership_edge, id="membership-edge"),
    ],
)
def test_product_role_mutations_are_rejected(
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    """正常資産を確認後、ロールとmembershipの各変異を拒否する。"""
    asset = _read_product_asset()
    _validate_product_asset(asset)
    mutated = copy.deepcopy(asset)
    mutate(mutated)

    with pytest.raises(_catalog_checker.CatalogError):
        _validate_product_asset(mutated)


def test_product_role_assets_contain_no_secrets_or_connection_strings() -> None:
    """DDL宣言と全bodyにpasswordや接続文字列を含めない。"""
    paths = [_REPOSITORY_ROOT / PRODUCT_SPEC.ddl_elements_path]
    paths.extend(
        path
        for path in (_REPOSITORY_ROOT / PRODUCT_SPEC.body_directory).rglob("*")
        if path.is_file()
    )
    assert paths
    for path in paths:
        text = path.read_text(encoding="utf-8")
        assert "password" not in text.casefold(), path
        assert _CONNECTION_STRING_RE.search(text) is None, path
