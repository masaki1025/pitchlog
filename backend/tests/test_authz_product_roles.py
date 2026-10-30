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
from pitchlog.authz.product_authn_contract import validate_authn_asset
from pitchlog.authz.product_role_contract import (
    expected_product_roles,
    generate_lifecycle_role_sql,
)

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
    """製品ロール宣言と SQL が独立の意味契約へ完全一致する。"""
    asset = _read_product_asset()
    assert _validate_product_asset(asset) == {
        "scope_status": "product_configuration",
        "product_role_count": len(expected_product_roles(asset)),
    }
    role_rows = asset["roles"]
    assert isinstance(role_rows, list)
    actual_roles = {
        str(row["role_id"]): {
            key: value for key, value in row.items() if key != "role_id"
        }
        for row in role_rows
    }
    expected_roles = expected_product_roles(asset)
    assert actual_roles == expected_roles
    assert asset["permanent_privileged_role_ids"] == ["pitchlog_owner"]
    assert asset["membership_edges"] == []

    statements = generate_authz_ddl(_REPOSITORY_ROOT, PRODUCT_SPEC)
    statements_by_role = _statement_by_role(statements)
    assert set(statements_by_role) == set(expected_roles)
    for role_id, expected in expected_roles.items():
        sql = statements_by_role[role_id].sql
        attribute_statement = (
            rf"CREATE ROLE {re.escape(role_id)} WITH\s+([^;]+);"
            if role_id
            in {
                "pitchlog_rule_resolution_fn_owner",
                "pitchlog_initial_auth_verifier",
                *_LIFECYCLE_ROLE_EXPECTATIONS,
            }
            else rf"ALTER ROLE {re.escape(role_id)} WITH\s+([^;]+);"
        )
        matches = re.findall(
            attribute_statement,
            sql,
            flags=re.DOTALL,
        )
        assert len(matches) == 1
        assert tuple(matches[0].split()) == tuple(
            _SQL_ATTRIBUTE_TOKENS[attribute][not bool(expected[attribute])]
            for attribute in _ATTRIBUTE_ORDER
        )
        create_count = len(re.findall(rf"\bCREATE ROLE {re.escape(role_id)};", sql))
        assert create_count == (
            0
            if role_id
            in {
                "pitchlog_owner",
                "pitchlog_rule_resolution_fn_owner",
                "pitchlog_initial_auth_verifier",
                *_LIFECYCLE_ROLE_EXPECTATIONS,
            }
            else 1
        )
        if role_id not in {"pitchlog_owner", *_LIFECYCLE_ROLE_EXPECTATIONS}:
            assert "END;\n$authz$;" in sql

    body_result = _run_checker(_BODY_CHECKER)
    catalog_result = _run_checker(_CATALOG_CHECKER)
    assert body_result.returncode == 0, body_result.stderr
    assert catalog_result.returncode == 0, catalog_result.stderr


def test_removed_product_role_violates_independent_contract() -> None:
    """資産からロールを消しても意味上の期待集合は縮まらない。"""
    asset = _read_product_asset()
    asset["roles"] = [
        row
        for row in asset["roles"]
        if row["role_id"] != "pitchlog_management_fn_owner"
    ]
    with pytest.raises(_catalog_checker.CatalogError, match="製品ロール集合"):
        _validate_product_asset(asset)


def test_product_state_requires_authn_role_even_when_role_is_missing() -> None:
    """認証資産の宣言に依存せず所有ロールを必須にする。"""
    asset = _read_product_asset()
    asset["roles"] = [
        row for row in asset["roles"] if row["role_id"] != "pitchlog_auth_fn_owner"
    ]
    expected = expected_product_roles(asset)
    assert set(expected) == {
        "pitchlog_owner",
        "pitchlog_app",
        "pitchlog_shared_fn_owner",
        "pitchlog_management_fn_owner",
        "pitchlog_auth_fn_owner",
        "pitchlog_rg1_fn_owner",
        "pitchlog_rule_resolution_fn_owner",
        "pitchlog_initial_auth_verifier",
        *_LIFECYCLE_ROLE_EXPECTATIONS,
    }
    assert "pitchlog_auth_fn_owner" not in {row["role_id"] for row in asset["roles"]}


def test_whole_authn_bundle_removal_is_rejected() -> None:
    """ロール・スキーマ・拡張・関数を一括削除しても製品期待集合を縮めない。"""
    asset = _read_product_asset()
    asset["roles"] = [
        row for row in asset["roles"] if row["role_id"] != "pitchlog_auth_fn_owner"
    ]
    asset["schemas"] = [
        row
        for row in asset["schemas"]
        if row["schema_name"] not in {"authn", "authn_crypto"}
    ]
    asset["extensions"] = []
    asset["functions"] = [
        row for row in asset["functions"] if row["schema_name"] != "authn"
    ]
    assert len(expected_product_roles(asset)) == 14
    with pytest.raises(ValueError, match="署名"):
        validate_authn_asset(asset)
    with pytest.raises(_catalog_checker.CatalogError):
        _validate_product_asset(asset)


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
    """DDL宣言と全bodyに平文の固定パスワードや接続文字列を含めない。"""
    paths = [_REPOSITORY_ROOT / PRODUCT_SPEC.ddl_elements_path]
    paths.extend(
        path
        for path in (_REPOSITORY_ROOT / PRODUCT_SPEC.body_directory).rglob("*")
        if path.is_file()
    )
    assert paths
    for path in paths:
        text = path.read_text(encoding="utf-8")
        assert re.search(r"\bpassword\s*=\s*'[^']+'", text, re.I) is None, path
        assert _CONNECTION_STRING_RE.search(text) is None, path


# 旧7の写像を使い回して新4の期待を自己生成せず、固定SQLの7属性を明示する。
_LIFECYCLE_ROLE_EXPECTATIONS = {
    "pitchlog_rg1_control_owner": (False, False, False, False, False, False, False),
    "pitchlog_rg1_control_actor": (False, False, True, False, False, False, False),
    "pitchlog_ledger_identity_owner": (False, False, False, False, False, False, True),
    "pitchlog_ledger_identity_probe": (False, False, True, False, False, False, False),
    "pitchlog_initial_actor": (False, False, True, False, False, False, False),
    "pitchlog_initial_fn_owner": (False, False, False, False, False, False, False),
}


def _asset_with_lifecycle_roles() -> dict[str, Any]:
    """正式旧資産/追随済み資産とも同じ有限6subjectを検査入力へする。"""
    asset = copy.deepcopy(_read_product_asset())
    existing = {row["role_id"] for row in asset["roles"]}
    for name, attributes in _LIFECYCLE_ROLE_EXPECTATIONS.items():
        if name not in existing:
            asset["roles"].append(
                {
                    "role_id": name,
                    "creation": "product_ddl",
                    **dict(zip(_ATTRIBUTE_ORDER, attributes, strict=True)),
                }
            )
    return asset


def test_lifecycle_roles_keep_old_seven_and_exact_six_sql_subjects() -> None:
    """独立6主体の全7属性と、外部台帳roleを混入しない13件を照合する。"""
    current = expected_product_roles({})
    assert len(current) == 14
    assert len(set(current) - set(_LIFECYCLE_ROLE_EXPECTATIONS)) == 8
    assert not {"pitchlog_ledger_owner", "pitchlog_ledger_client"} & set(current)
    for name, attributes in _LIFECYCLE_ROLE_EXPECTATIONS.items():
        assert current[name] == {
            "creation": "product_ddl",
            **dict(zip(_ATTRIBUTE_ORDER, attributes, strict=True)),
        }
    from pitchlog.authz.product_role_contract import expected_provisional_product_roles

    assert set(expected_provisional_product_roles()) == {
        "pitchlog_owner",
        "pitchlog_app",
        "pitchlog_shared_fn_owner",
        "pitchlog_management_fn_owner",
    }


@pytest.mark.parametrize("role", tuple(_LIFECYCLE_ROLE_EXPECTATIONS))
@pytest.mark.parametrize("attribute", _ATTRIBUTE_ORDER)
def test_each_lifecycle_role_attribute_flip_is_rejected(
    role: str, attribute: str
) -> None:
    """資産側の1bit反転だけでは独立の意味契約を変更できない。"""
    asset = _asset_with_lifecycle_roles()
    row = next(row for row in asset["roles"] if row["role_id"] == role)
    row[attribute] = not row[attribute]
    with pytest.raises(_catalog_checker.CatalogError, match=role):
        _validate_product_asset(asset)


@pytest.mark.parametrize("role", tuple(_LIFECYCLE_ROLE_EXPECTATIONS))
def test_each_lifecycle_role_membership_is_rejected(role: str) -> None:
    """追加のLOGIN/NOLOGIN主体にもmembership0を継続する。"""
    asset = _asset_with_lifecycle_roles()
    asset["membership_edges"] = [
        {
            "role_id": role,
            "member_id": "pitchlog_app",
            "admin_option": False,
            "set_option": True,
            "inherit_option": False,
        }
    ]
    with pytest.raises(_catalog_checker.CatalogError, match="membership"):
        _validate_product_asset(asset)


@pytest.mark.parametrize("role", tuple(_LIFECYCLE_ROLE_EXPECTATIONS))
def test_lifecycle_role_sql_has_exact_attributes_and_no_repair(role: str) -> None:
    """新6主体だけを全7属性と両向membership0で再適用判定する。"""
    rendered = generate_lifecycle_role_sql(role)
    expected = _LIFECYCLE_ROLE_EXPECTATIONS[role]
    tokens = tuple(
        _SQL_ATTRIBUTE_TOKENS[name][not value]
        for name, value in zip(_ATTRIBUTE_ORDER, expected, strict=True)
    )
    match = re.findall(rf"CREATE ROLE {role} WITH\s+([^;]+);", rendered)
    assert len(match) == 1 and tuple(match[0].split()) == tokens
    columns = (
        "rolsuper",
        "rolbypassrls",
        "rolcanlogin",
        "rolcreaterole",
        "rolcreatedb",
        "rolreplication",
        "rolinherit",
    )
    for column, value in zip(columns, expected, strict=True):
        assert f"AND {'' if value else 'NOT '}r.{column}\n" in rendered
    assert "m.roleid = r.oid OR m.member = r.oid" in rendered
    assert "RAISE EXCEPTION 'lifecycle role collision:" in rendered
    assert "ELSE\n        CREATE ROLE" in rendered
    assert "ALTER ROLE" not in rendered and "GRANT " not in rendered
    assert rendered.count("CREATE ROLE") == 1


@pytest.mark.parametrize(
    "role",
    [
        "pitchlog_app",
        "pitchlog_owner",
        "pitchlog_rule_resolution_fn_owner",
        "unknown",
        "pitchlog_initial_actor; SELECT 1",
    ],
)
def test_lifecycle_role_sql_rejects_unknown_and_old_subjects(role: str) -> None:
    """旧7主体や任意文字列へ新生成器の権限を拡張しない。"""
    with pytest.raises(ValueError, match="新6ロール"):
        generate_lifecycle_role_sql(role)


@pytest.mark.parametrize("role", tuple(_LIFECYCLE_ROLE_EXPECTATIONS))
def test_lifecycle_role_asset_matches_strict_reapply_generator(role: str) -> None:
    """正式bodyも厳密な再適用ガードと一致し、単純CREATEを受理しない。"""
    body = _REPOSITORY_ROOT / PRODUCT_SPEC.body_directory / "roles" / f"{role}.sql"
    assert body.read_text() == generate_lifecycle_role_sql(role)


def test_b1_verifier_role_exact_and_strict_collision_sql_keeps_old_six() -> None:
    """旧13の値を保持し、新1主体にも属性/membership衝突拒否を要求する。"""
    role = expected_product_roles({})["pitchlog_initial_auth_verifier"]
    assert role == dict(
        creation="product_ddl",
        login=True,
        superuser=False,
        bypass_rls=False,
        inherit=False,
        create_role=False,
        create_db=False,
        replication=False,
    )
    sql = generate_lifecycle_role_sql("pitchlog_initial_auth_verifier")
    assert "lifecycle role collision: pitchlog_initial_auth_verifier" in sql
    assert "m.roleid = r.oid OR m.member = r.oid" in sql
    assert "ALTER ROLE" not in sql
    assert all(
        catalog in sql
        for catalog in (
            "rolsuper",
            "rolbypassrls",
            "rolcanlogin",
            "rolcreaterole",
            "rolcreatedb",
            "rolreplication",
            "rolinherit",
        )
    )
