"""実 PostgreSQL の認可カタログ構成を検証する。"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import psycopg
import pytest
from psycopg import sql

from pitchlog.authz.catalog import (
    CatalogCheckError,
    inspect_authz_catalog,
)
from pitchlog.authz.ddl import DDLStatement

from .conftest import (
    ProvisionedCatalog,
    _asset_rows,
    _load_ddl_asset,
    _role_id,
)

pytestmark = pytest.mark.requires_db

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_BODY_CHECKER_PATH = _REPOSITORY_ROOT / "scripts/check_authz_function_bodies.py"
_STATIC_CATALOG_PATH = _REPOSITORY_ROOT / "scripts/check_authz_catalog.py"
_REVOKE_TARGET_RE = re.compile(
    r"(?is)\bREVOKE\s+ALL\s+PRIVILEGES\s+ON\s+FUNCTION\s+(.+?)\s+FROM\s+PUBLIC"
)


@dataclass(frozen=True, slots=True)
class _NegativeCase:
    """単独のカタログ故障と期待する検査 ID を表す。"""

    case_id: str
    mutation: Callable[[ProvisionedCatalog, Path], Path]
    expected_check_ids: frozenset[str]


def _function(asset: dict[str, object], function_class: str) -> dict[str, object]:
    """Function class から一意な関数資産を導出する。"""
    functions = [
        row
        for row in _asset_rows(asset, "functions")
        if row.get("function_class") == function_class
    ]
    assert len(functions) == 1
    return functions[0]


def _statement(
    catalog: ProvisionedCatalog, element_type: str, element_id: str
) -> DDLStatement:
    """生成済み SQL から資産要素を一意に選ぶ。"""
    matches = [
        statement
        for statement in catalog.statements
        if statement.element_type == element_type and statement.element_id == element_id
    ]
    assert len(matches) == 1
    return matches[0]


def _expected_check_ids(asset: dict[str, object]) -> set[str]:
    """資産の全対象から実行される検査 ID 集合を導出する。"""
    expected = {
        "CATALOG:POLICY:EXACT-SET",
        "CATALOG:FUNCTION-DIGEST:EXACT-SET",
        "CATALOG:REACHABILITY:SET",
        "CATALOG:REACHABILITY:USAGE",
        "CATALOG:ACL:DEFAULT",
        "CATALOG:ACL:PUBLIC",
        "CATALOG:OWNED-OBJECTS:BYPASSRLS",
        "CATALOG:OWNED-OBJECTS:SECURITY-DEFINER",
    }
    for policy in _asset_rows(asset, "policies"):
        expected.add(f"CATALOG:{policy['policy_id']}")
    for function in _asset_rows(asset, "functions"):
        function_id = function["function_id"]
        expected.update(
            {
                f"CATALOG:FUNCTION-DIGEST:{function_id}",
                f"CATALOG:FUNCTION-STRUCTURE:{function_id}:SQL-ATOMIC",
                f"CATALOG:FUNCTION-STRUCTURE:{function_id}:NO-DYNAMIC-SQL",
                f"CATALOG:FUNCTION-STRUCTURE:{function_id}:DEPENDENCY-RELATIONS",
                f"CATALOG:SEARCH-PATH:{function_id}",
                f"CATALOG:ACL:FUNCTION:{function_id}",
            }
        )
    for table in _asset_rows(asset, "tables"):
        expected.add(f"CATALOG:ACL:TABLE:{table['table_id']}")
    for schema in _asset_rows(asset, "schemas"):
        expected.add(f"CATALOG:ACL:SCHEMA:{schema['schema_id']}")
    for expectation in _asset_rows(asset, "column_acl_expectations"):
        expected.add(f"CATALOG:ACL:COLUMN:{expectation['expectation_id']}")
    claim = asset["provisioning_claim"]
    assert isinstance(claim, dict)
    completion = claim["completion_catalog_expectations"]
    assert isinstance(completion, list)
    expected.update(
        str(expectation["catalog_check_id"])
        for expectation in completion
        if isinstance(expectation, dict)
    )
    return expected


def _commit(catalog: ProvisionedCatalog) -> None:
    """単独故障を他接続からも観測可能にする。"""
    catalog.admin.commit()


def _create_forbidden_relation(catalog: ProvisionedCatalog) -> tuple[str, str]:
    """資産の依存集合にない relation を保護 schema 内へ作る。"""
    first_table = _asset_rows(catalog.asset, "tables")[0]
    schema_id = first_table["schema_id"]
    assert isinstance(schema_id, str)
    relation_id = "catalog_forbidden_relation"
    with catalog.admin.cursor() as cursor:
        cursor.execute(
            sql.SQL("CREATE TABLE {}.{} (marker INTEGER)").format(
                sql.Identifier(schema_id),
                sql.Identifier(relation_id),
            )
        )
    return schema_id, relation_id


def _replace_sql_function(
    catalog: ProvisionedCatalog,
    function: dict[str, object],
    inserted_statement: str,
) -> None:
    """封印済み CREATE へ 1 文だけ挿入して関数を置換する。"""
    function_id = function["function_id"]
    assert isinstance(function_id, str)
    statement = _statement(catalog, "function", function_id)
    trailer = statement.sql.index("\nALTER FUNCTION")
    create_source = statement.sql[:trailer].replace(
        "CREATE FUNCTION",
        "CREATE OR REPLACE FUNCTION",
        1,
    )
    create_source = create_source.replace(
        "BEGIN ATOMIC",
        f"BEGIN ATOMIC\n    {inserted_statement}",
        1,
    )
    with catalog.admin.cursor() as cursor:
        cursor.execute(create_source.encode("utf-8"))
    _commit(catalog)


def _mutate_forbidden_select(catalog: ProvisionedCatalog, tmp_path: Path) -> Path:
    """読み取り関数へ dependency 外 relation の SELECT を加える。"""
    del tmp_path
    schema_id, relation_id = _create_forbidden_relation(catalog)
    function = _function(catalog.asset, "shared_read")
    _replace_sql_function(
        catalog,
        function,
        f"SELECT marker FROM {schema_id}.{relation_id};",
    )
    return _REPOSITORY_ROOT


def _mutate_forbidden_dml(catalog: ProvisionedCatalog, tmp_path: Path) -> Path:
    """更新関数へ dependency 外 relation の DML を加える。"""
    del tmp_path
    schema_id, relation_id = _create_forbidden_relation(catalog)
    function = _function(catalog.asset, "representative_management_operation")
    _replace_sql_function(
        catalog,
        function,
        f"INSERT INTO {schema_id}.{relation_id} DEFAULT VALUES;",
    )
    return _REPOSITORY_ROOT


def _mutate_dynamic_sql(catalog: ProvisionedCatalog, tmp_path: Path) -> Path:
    """関数を動的 SQL を含む PL/pgSQL 定義へ差し替える。"""
    del tmp_path
    function = _function(catalog.asset, "representative_management_operation")
    schema_id = function["schema_id"]
    function_id = function["function_id"]
    assert isinstance(schema_id, str) and isinstance(function_id, str)
    with catalog.admin.cursor() as cursor:
        cursor.execute(
            sql.SQL(
                """
                CREATE OR REPLACE FUNCTION {}.{}(
                    p_group_id BIGINT,
                    p_tenant_id BIGINT,
                    p_effect_kind TEXT
                )
                RETURNS TABLE (
                    applied BOOLEAN,
                    group_id BIGINT,
                    tenant_id BIGINT,
                    effect_kind TEXT
                )
                LANGUAGE plpgsql
                VOLATILE
                SECURITY DEFINER
                SET search_path = pg_catalog, {}, pg_temp
                AS $body$
                BEGIN
                    EXECUTE 'SELECT 1';
                    RETURN;
                END;
                $body$
                """
            ).format(
                sql.Identifier(schema_id),
                sql.Identifier(function_id),
                sql.Identifier(schema_id),
            )
        )
    _commit(catalog)
    return _REPOSITORY_ROOT


def _load_module(name: str, path: Path) -> ModuleType:
    """公開 digest 関数をコピーせずファイル位置から import する。"""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _mutate_later_body_commit(catalog: ProvisionedCatalog, tmp_path: Path) -> Path:
    """現 digest だけ追随させ、source commit の封印と不一致にする。"""
    del catalog
    copied_root = tmp_path / "repository"
    result = subprocess.run(
        [
            "git",
            "clone",
            "--quiet",
            "--shared",
            "--no-checkout",
            str(_REPOSITORY_ROOT),
            str(copied_root),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    shutil.copytree(
        _REPOSITORY_ROOT / "contracts/authz",
        copied_root / "contracts/authz",
    )
    scripts = copied_root / "scripts"
    scripts.mkdir()
    shutil.copy2(_BODY_CHECKER_PATH, scripts / _BODY_CHECKER_PATH.name)
    shutil.copy2(_STATIC_CATALOG_PATH, scripts / _STATIC_CATALOG_PATH.name)

    manifest_path = copied_root / "contracts/authz/function-bodies/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = manifest["entries"]
    assert isinstance(entries, list)
    entry = next(item for item in entries if item["element_type"] == "function")
    body_path = copied_root / entry["path"]
    body_path.write_bytes(body_path.read_bytes() + b"\n-- later replacement\n")
    digest_module = _load_module("step6_static_catalog", _STATIC_CATALOG_PATH)
    entry["blob_digest"] = digest_module.git_blob_digest(body_path.read_bytes())
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    changed_paths = [
        str(body_path.relative_to(copied_root)),
        str(manifest_path.relative_to(copied_root)),
    ]
    add_result = subprocess.run(
        ["git", "add", "--", *changed_paths],
        cwd=copied_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert add_result.returncode == 0, add_result.stderr
    commit_result = subprocess.run(
        [
            "git",
            "-c",
            "user.name=Catalog Negative Test",
            "-c",
            "user.email=catalog-negative@example.invalid",
            "commit",
            "--quiet",
            "--message",
            "test: body replacement",
        ],
        cwd=copied_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert commit_result.returncode == 0, commit_result.stderr
    head_result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=copied_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert head_result.returncode == 0, head_result.stderr
    assert head_result.stdout.strip() != manifest["source_commit"]
    return copied_root


def _mutate_indirect_superuser(catalog: ProvisionedCatalog, tmp_path: Path) -> Path:
    """Caller から superuser へ二段の SET・USAGE 経路を作る。"""
    del tmp_path
    app_role = _role_id(catalog.asset, "tested_caller")
    bridge = "catalog_super_bridge"
    endpoint = "catalog_super_endpoint"
    with catalog.admin.cursor() as cursor:
        cursor.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(bridge)))
        cursor.execute(
            sql.SQL("CREATE ROLE {} NOLOGIN SUPERUSER").format(sql.Identifier(endpoint))
        )
        cursor.execute(
            sql.SQL("GRANT {} TO {} WITH INHERIT TRUE, SET TRUE").format(
                sql.Identifier(endpoint),
                sql.Identifier(bridge),
            )
        )
        cursor.execute(
            sql.SQL("GRANT {} TO {} WITH INHERIT TRUE, SET TRUE").format(
                sql.Identifier(bridge),
                sql.Identifier(app_role),
            )
        )
    _commit(catalog)
    return _REPOSITORY_ROOT


def _mutate_table_owner_membership(catalog: ProvisionedCatalog, tmp_path: Path) -> Path:
    """App caller から保護表 owner への直接経路を作る。"""
    del tmp_path
    app_role = _role_id(catalog.asset, "tested_caller")
    table_owner = _role_id(catalog.asset, "object_owner")
    with catalog.admin.cursor() as cursor:
        cursor.execute(
            sql.SQL("GRANT {} TO {} WITH INHERIT TRUE, SET TRUE").format(
                sql.Identifier(table_owner),
                sql.Identifier(app_role),
            )
        )
    _commit(catalog)
    return _REPOSITORY_ROOT


def _mutate_app_superuser(catalog: ProvisionedCatalog, tmp_path: Path) -> Path:
    """App caller 自身を危険終点に変える。"""
    del tmp_path
    app_role = _role_id(catalog.asset, "tested_caller")
    with catalog.admin.cursor() as cursor:
        cursor.execute(
            sql.SQL("ALTER ROLE {} SUPERUSER").format(sql.Identifier(app_role))
        )
    _commit(catalog)
    return _REPOSITORY_ROOT


def _mutate_extra_function(catalog: ProvisionedCatalog, tmp_path: Path) -> Path:
    """採用関数 schema へ資産外 SECURITY DEFINER 関数を増やす。"""
    del tmp_path
    function = _function(catalog.asset, "shared_read")
    schema_id = function["schema_id"]
    owner_id = function["owner_role_id"]
    assert isinstance(schema_id, str) and isinstance(owner_id, str)
    extra_id = "catalog_extra_function"
    with catalog.admin.cursor() as cursor:
        cursor.execute(
            sql.SQL(
                """
                CREATE FUNCTION {}.{}()
                RETURNS INTEGER
                LANGUAGE SQL
                SECURITY DEFINER
                SET search_path = pg_catalog, {}, pg_temp
                RETURN 1
                """
            ).format(
                sql.Identifier(schema_id),
                sql.Identifier(extra_id),
                sql.Identifier(schema_id),
            )
        )
        cursor.execute(
            sql.SQL("ALTER FUNCTION {}.{}() OWNER TO {}").format(
                sql.Identifier(schema_id),
                sql.Identifier(extra_id),
                sql.Identifier(owner_id),
            )
        )
    _commit(catalog)
    return _REPOSITORY_ROOT


def _mutate_public_execute(catalog: ProvisionedCatalog, tmp_path: Path) -> Path:
    """越境関数の全 overload のうち 1 本へ PUBLIC EXECUTE を戻す。"""
    del tmp_path
    function = _function(catalog.asset, "shared_read")
    function_id = function["function_id"]
    assert isinstance(function_id, str)
    statement = _statement(catalog, "function", function_id)
    target = _REVOKE_TARGET_RE.search(statement.sql)
    assert target is not None
    with catalog.admin.cursor() as cursor:
        cursor.execute(
            f"GRANT EXECUTE ON FUNCTION {target.group(1)} TO PUBLIC".encode("utf-8")
        )
    _commit(catalog)
    return _REPOSITORY_ROOT


def _negative_cases(asset: dict[str, object]) -> tuple[_NegativeCase, ...]:
    """資産の関数 ID と検査規則から負例の期待差分集合を導出する。"""
    shared_function_id = _function(asset, "shared_read")["function_id"]
    management_function_id = _function(asset, "representative_management_operation")[
        "function_id"
    ]
    assert isinstance(shared_function_id, str)
    assert isinstance(management_function_id, str)

    shared_digest = f"CATALOG:FUNCTION-DIGEST:{shared_function_id}"
    shared_dependency = (
        f"CATALOG:FUNCTION-STRUCTURE:{shared_function_id}:DEPENDENCY-RELATIONS"
    )
    management_digest = f"CATALOG:FUNCTION-DIGEST:{management_function_id}"
    management_structure = f"CATALOG:FUNCTION-STRUCTURE:{management_function_id}"
    reachability = frozenset({"CATALOG:REACHABILITY:SET", "CATALOG:REACHABILITY:USAGE"})
    return (
        _NegativeCase(
            "forbidden-select",
            _mutate_forbidden_select,
            frozenset({shared_digest, shared_dependency}),
        ),
        _NegativeCase(
            "forbidden-dml",
            _mutate_forbidden_dml,
            frozenset(
                {
                    management_digest,
                    f"{management_structure}:DEPENDENCY-RELATIONS",
                }
            ),
        ),
        _NegativeCase(
            "dynamic-sql",
            _mutate_dynamic_sql,
            frozenset(
                {
                    management_digest,
                    f"{management_structure}:SQL-ATOMIC",
                    f"{management_structure}:NO-DYNAMIC-SQL",
                    f"{management_structure}:DEPENDENCY-RELATIONS",
                }
            ),
        ),
        _NegativeCase(
            "later-body-commit",
            _mutate_later_body_commit,
            frozenset({"CATALOG:FUNCTION-DIGEST:SOURCE-SEAL"}),
        ),
        _NegativeCase(
            "indirect-superuser",
            _mutate_indirect_superuser,
            reachability,
        ),
        _NegativeCase(
            "table-owner-membership",
            _mutate_table_owner_membership,
            reachability,
        ),
        _NegativeCase(
            "app-superuser",
            _mutate_app_superuser,
            reachability,
        ),
        _NegativeCase(
            "extra-function",
            _mutate_extra_function,
            frozenset(
                {
                    "CATALOG:FUNCTION-DIGEST:EXACT-SET",
                    "CATALOG:OWNED-OBJECTS:BYPASSRLS",
                    "CATALOG:OWNED-OBJECTS:SECURITY-DEFINER",
                }
            ),
        ),
        _NegativeCase(
            "public-execute",
            _mutate_public_execute,
            frozenset(
                {
                    shared_digest,
                    f"CATALOG:ACL:FUNCTION:{shared_function_id}",
                    "CATALOG:ACL:PUBLIC",
                }
            ),
        ),
    )


_NEGATIVE_CASES = _negative_cases(_load_ddl_asset())


def _violation_ids(
    catalog: ProvisionedCatalog,
    root: Path,
) -> frozenset[str]:
    """Catalog report と入力検査エラーを同じ検査 ID 集合へ正規化する。"""
    try:
        report = inspect_authz_catalog(
            catalog.admin,
            root,
            reference_connection=catalog.reference_admin,
        )
    except CatalogCheckError as error:
        return frozenset({error.check_id})
    return frozenset(violation.check_id for violation in report.violations)


def test_applied_catalog_matches_assets_and_uses_all_login_role_fixtures(
    provisioned_catalog: ProvisionedCatalog,
    table_owner_connection: psycopg.Connection[Any],
    app_role_connection: psycopg.Connection[Any],
    management_caller_connection: psycopg.Connection[Any],
    outsider_role_connection: psycopg.Connection[Any],
) -> None:
    """適用済み構成を合格させ、4 ロール fixture の実接続も要求する。"""
    assert all(
        isinstance(connection, psycopg.Connection)
        for connection in (
            table_owner_connection,
            app_role_connection,
            management_caller_connection,
            outsider_role_connection,
        )
    )
    report = inspect_authz_catalog(
        provisioned_catalog.admin,
        _REPOSITORY_ROOT,
        reference_connection=provisioned_catalog.reference_admin,
    )

    assert report.ok, report.violations
    assert len(report.checked_ids) == len(set(report.checked_ids))
    assert set(report.checked_ids) == _expected_check_ids(provisioned_catalog.asset)


@pytest.mark.parametrize(
    "case",
    _NEGATIVE_CASES,
    ids=lambda case: case.case_id,
)
def test_catalog_negative_cases_are_red(
    provisioned_catalog: ProvisionedCatalog,
    tmp_path: Path,
    case: _NegativeCase,
) -> None:
    """定義集合の各単独故障を対応するカタログ検査で red にする。"""
    baseline_violations = _violation_ids(
        provisioned_catalog,
        _REPOSITORY_ROOT,
    )
    assert baseline_violations == frozenset()

    root = case.mutation(provisioned_catalog, tmp_path)
    mutated_violations = _violation_ids(provisioned_catalog, root)
    introduced_violations = mutated_violations - baseline_violations

    assert introduced_violations == case.expected_check_ids
