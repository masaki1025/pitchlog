"""移行バッチ用ロール資産を manifest 由来の期待値で検査する。"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, cast

import psycopg
import pytest

from pitchlog.authz import product_catalog
from pitchlog.authz.product_catalog import ProductCatalogError

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_ASSET_PATH = _REPOSITORY_ROOT / "contracts/authz/product/migration-batch-role.json"
_MANIFEST_PATH = _REPOSITORY_ROOT / "contracts/db/schema-manifest.json"


def _load_object(path: Path) -> dict[str, object]:
    """JSON object を読む。"""
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _documents() -> tuple[dict[str, object], dict[str, object]]:
    """正規の移行ロール資産と manifest を返す。"""
    return _load_object(_ASSET_PATH), _load_object(_MANIFEST_PATH)


def _assert_mutated_asset_is_red_through_public_inspection(
    monkeypatch: pytest.MonkeyPatch,
    asset: dict[str, object],
    manifest: dict[str, object],
    *,
    match: str,
) -> None:
    """変異した資産を公開カタログ検査が DB 呼び出し前に拒否すると表明する。"""

    def load_document(path: Path, label: str) -> dict[str, object]:
        del label
        if path == product_catalog._MIGRATION_BATCH_ROLE_PATH:
            return asset
        if path == product_catalog._SCHEMA_MANIFEST_PATH:
            return manifest
        raise AssertionError(f"予期しない資産の読み取り: {path}")

    def fail_if_called(
        connection: psycopg.Connection[Any],
        query_id: product_catalog.CatalogQueryId,
        params: tuple[object, ...],
    ) -> list[tuple[object, ...]]:
        del connection, query_id, params
        raise AssertionError("不正な資産で DB を読んではならない")

    monkeypatch.setattr(product_catalog, "_load_json_object", load_document)
    monkeypatch.setattr(product_catalog, "_fetch_catalog_rows", fail_if_called)
    with pytest.raises(ProductCatalogError, match=match):
        product_catalog.inspect_migration_batch_role_catalog(
            cast(psycopg.Connection[Any], object()),
            role_oid=910,
        )


def test_migration_batch_role_asset_matches_manifest_derived_exact_sets() -> None:
    """19 表と 50 権限を分類資産でなく manifest から導く。"""
    asset, manifest = _documents()
    expectations = product_catalog._migration_batch_expectations_from_documents(
        asset,
        manifest,
    )

    assert len(expectations.write_targets) == 19
    assert len(expectations.permissions) == 50
    assert {
        table
        for schema, table, column, privilege, grantable in expectations.permissions
        if schema == "public"
        and column == ""
        and privilege == "INSERT"
        and grantable is False
    } == set(expectations.write_targets)
    assert {
        table
        for schema, table, column, privilege, grantable in expectations.permissions
        if schema == "public"
        and column == ""
        and privilege == "SELECT"
        and grantable is False
    } == set(expectations.write_targets)
    assert not {
        privilege
        for _, _, column, privilege, _ in expectations.permissions
        if column == "" and privilege in {"UPDATE", "DELETE"}
    }
    assert expectations.schema_acl == (("public", "USAGE", False),)
    assert expectations.database_acl == (("CONNECT", False),)
    assert expectations.function_execute == ()


def test_declared_function_execute_is_exact_and_has_a_closed_shape() -> None:
    """移行ロールの関数権限は製品関数の宣言を参照する3要素である。"""
    asset, manifest = _documents()
    product_asset = _load_object(
        _REPOSITORY_ROOT / "contracts/authz/product/ddl-elements.json"
    )
    shape = asset["active_role_shape"]
    assert isinstance(shape, dict)
    shape["function_execute"] = [
        {
            "schema_name": "authz_private",
            "function_name": "tenant_has_effective_membership",
            "identity_args": "uuid, boolean",
        }
    ]
    expectations = product_catalog._migration_batch_expectations_from_documents(
        asset, manifest, product_asset
    )
    assert expectations.function_execute == (
        ("authz_private", "tenant_has_effective_membership", "uuid, boolean"),
    )
    shape["function_execute"][0]["identity_args"] = "uuid); DROP ROLE pitchlog_app; --"
    with pytest.raises(ProductCatalogError, match="identity_args"):
        product_catalog._migration_batch_expectations_from_documents(
            asset, manifest, product_asset
        )


def test_extra_function_execute_is_red_against_nonempty_declaration() -> None:
    """宣言した1件が通り、宣言外を1件足すと exact 照合が落ちる。"""
    asset, manifest = _documents()
    product_asset = _load_object(
        _REPOSITORY_ROOT / "contracts/authz/product/ddl-elements.json"
    )
    shape = asset["active_role_shape"]
    assert isinstance(shape, dict)
    shape["function_execute"] = [
        {
            "schema_name": "authz_private",
            "function_name": "tenant_has_effective_membership",
            "identity_args": "uuid, boolean",
        }
    ]
    expected = product_catalog._migration_batch_expectations_from_documents(
        asset, manifest, product_asset
    )
    query = product_catalog.CatalogQueryId
    observations = (
        (query.MIGRATION_BATCH_ROLE, (tuple(expected.attributes),)),
        (query.MIGRATION_BATCH_MEMBERSHIPS, ()),
        (query.MIGRATION_BATCH_OWNERSHIP, ()),
        (query.MIGRATION_BATCH_TABLE_ACL, tuple(expected.permissions)),
        (query.MIGRATION_BATCH_SCHEMA_ACL, tuple(expected.schema_acl)),
        (query.MIGRATION_BATCH_DATABASE_ACL, tuple(expected.database_acl)),
        (query.MIGRATION_BATCH_FUNCTION_EXECUTE, tuple(expected.function_execute)),
    )
    assert product_catalog._migration_batch_report(observations, expected).ok
    mutated = observations[:-1] + (
        (
            query.MIGRATION_BATCH_FUNCTION_EXECUTE,
            tuple(expected.function_execute) + (("public", "unlisted", ""),),
        ),
    )
    report = product_catalog._migration_batch_report(mutated, expected)
    assert "MIGRATION-BATCH:FUNCTION-EXECUTE" in {
        violation.check_id for violation in report.violations
    }


def test_function_execute_request_covers_every_declared_product_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """検査対象スキーマを1つ外す変異を問い合わせ束縛値の比較で検出する。"""
    asset = _load_object(_REPOSITORY_ROOT / "contracts/authz/product/ddl-elements.json")
    raw_schemas = asset["schemas"]
    assert isinstance(raw_schemas, list)
    extra_schema = copy.deepcopy(raw_schemas[-1])
    extra_schema["schema_id"] = "authn_crypto"
    extra_schema["schema_name"] = "authn_crypto"
    raw_schemas.append(extra_schema)
    declared_schemas = tuple(row["schema_name"] for row in raw_schemas)
    monkeypatch.setattr(product_catalog, "_load_product_asset", lambda: asset)
    expected = product_catalog._load_migration_batch_expectations()
    query = product_catalog.CatalogQueryId
    rows_by_query: dict[product_catalog.CatalogQueryId, list[tuple[object, ...]]] = {
        query.MIGRATION_BATCH_ROLE: [tuple(expected.attributes)],
        query.MIGRATION_BATCH_MEMBERSHIPS: [],
        query.MIGRATION_BATCH_OWNERSHIP: [],
        query.MIGRATION_BATCH_TABLE_ACL: list(expected.permissions),
        query.MIGRATION_BATCH_SCHEMA_ACL: list(expected.schema_acl),
        query.MIGRATION_BATCH_DATABASE_ACL: list(expected.database_acl),
        query.MIGRATION_BATCH_FUNCTION_EXECUTE: [],
    }
    queried_schemas: list[str] = []

    def fetch(
        connection: psycopg.Connection[Any],
        query_id: product_catalog.CatalogQueryId,
        params: tuple[object, ...],
    ) -> list[tuple[object, ...]]:
        del connection
        if query_id is query.MIGRATION_BATCH_FUNCTION_EXECUTE:
            raw = params[0]
            assert isinstance(raw, list)
            queried_schemas.extend(raw)
        return rows_by_query[query_id]

    monkeypatch.setattr(product_catalog, "_fetch_catalog_rows", fetch)
    report = product_catalog.inspect_migration_batch_role_catalog(
        cast(psycopg.Connection[Any], object()), role_oid=910
    )
    assert report.ok
    assert set(queried_schemas) == set(declared_schemas)
    assert len(queried_schemas) == len(declared_schemas)


def test_adding_a_write_target_is_red(monkeypatch: pytest.MonkeyPatch) -> None:
    """Manifest の導出集合に無い表を write_targets へ足せない。"""
    asset, manifest = _documents()
    mutated = copy.deepcopy(asset)
    write_targets = mutated["write_targets"]
    assert isinstance(write_targets, list)
    write_targets.append("admin_operation_logs")

    _assert_mutated_asset_is_red_through_public_inspection(
        monkeypatch,
        mutated,
        manifest,
        match="write_targets",
    )


def test_removing_a_required_permission_is_red(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """必要な表・列権限を 1 件でも欠かせない。"""
    asset, manifest = _documents()
    mutated = copy.deepcopy(asset)
    permissions = mutated["permissions"]
    assert isinstance(permissions, list)
    permissions.pop()

    _assert_mutated_asset_is_red_through_public_inspection(
        monkeypatch,
        mutated,
        manifest,
        match="permissions",
    )


@pytest.mark.parametrize("privilege", ["UPDATE", "DELETE"])
def test_adding_a_table_level_write_permission_is_red(
    monkeypatch: pytest.MonkeyPatch,
    privilege: str,
) -> None:
    """表単位 UPDATE と DELETE を資産の権限行列へ追加できない。"""
    asset, manifest = _documents()
    mutated = copy.deepcopy(asset)
    permissions = mutated["permissions"]
    assert isinstance(permissions, list)
    permissions.append(
        {
            "table_id": "lineup_memories",
            "column_id": None,
            "privilege": privilege,
            "grantable": False,
        }
    )

    _assert_mutated_asset_is_red_through_public_inspection(
        monkeypatch,
        mutated,
        manifest,
        match="permissions",
    )


def test_active_role_public_inspection_is_green_for_exact_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OID 指定の公開経路が有効時の全 7 面を exact-set 検査する。"""
    expectations = product_catalog._load_migration_batch_expectations()
    rows_by_query: dict[
        product_catalog.CatalogQueryId,
        list[tuple[object, ...]],
    ] = {
        product_catalog.CatalogQueryId.MIGRATION_BATCH_ROLE: [
            tuple(expectations.attributes)
        ],
        product_catalog.CatalogQueryId.MIGRATION_BATCH_MEMBERSHIPS: [],
        product_catalog.CatalogQueryId.MIGRATION_BATCH_OWNERSHIP: [],
        product_catalog.CatalogQueryId.MIGRATION_BATCH_TABLE_ACL: [
            tuple(permission) for permission in expectations.permissions
        ],
        product_catalog.CatalogQueryId.MIGRATION_BATCH_SCHEMA_ACL: [
            tuple(entry) for entry in expectations.schema_acl
        ],
        product_catalog.CatalogQueryId.MIGRATION_BATCH_DATABASE_ACL: [
            tuple(entry) for entry in expectations.database_acl
        ],
        product_catalog.CatalogQueryId.MIGRATION_BATCH_FUNCTION_EXECUTE: [],
    }
    calls: list[product_catalog.CatalogQueryId] = []

    def fetch(
        connection: psycopg.Connection[Any],
        query_id: product_catalog.CatalogQueryId,
        params: tuple[object, ...],
    ) -> list[tuple[object, ...]]:
        del connection, params
        calls.append(query_id)
        return rows_by_query[query_id]

    monkeypatch.setattr(product_catalog, "_fetch_catalog_rows", fetch)
    report = product_catalog.inspect_migration_batch_role_catalog(
        cast(psycopg.Connection[Any], object()),
        role_oid=910,
    )

    assert report.ok
    assert report.violations == ()
    assert len(report.checked_ids) == 7
    assert calls == list(rows_by_query)


@pytest.mark.parametrize(
    ("query_id", "acl_column", "object_kind", "owner_column"),
    [
        pytest.param(
            product_catalog.CatalogQueryId.MIGRATION_BATCH_SCHEMA_ACL,
            "namespace.nspacl",
            "n",
            "namespace.nspowner",
            id="schema",
        ),
        pytest.param(
            product_catalog.CatalogQueryId.MIGRATION_BATCH_DATABASE_ACL,
            "database.datacl",
            "d",
            "database.datdba",
            id="database",
        ),
    ],
)
def test_active_role_acl_queries_include_public_and_postgresql_defaults(
    query_id: product_catalog.CatalogQueryId,
    acl_column: str,
    object_kind: str,
    owner_column: str,
) -> None:
    """有効時の ACL は PUBLIC と NULL ACL の既定権限を含めて観測する。"""
    query = " ".join(product_catalog._query_for_id(query_id).split())

    assert "privilege.grantee IN (0, %s::pg_catalog.oid)" in query
    assert (
        f"COALESCE( {acl_column}, "
        f"pg_catalog.acldefault('{object_kind}', {owner_column}) )"
    ) in query


def test_active_role_relation_acl_covers_every_user_defined_schema() -> None:
    """表 ACL はシステム schema だけを除き全 ACL 対象 relation を観測する。"""
    query = " ".join(
        product_catalog._query_for_id(
            product_catalog.CatalogQueryId.MIGRATION_BATCH_TABLE_ACL
        ).split()
    )

    for schema_name in ("pg_catalog", "information_schema", "pg_toast"):
        assert f"'{schema_name}'" in query
    assert "namespace.nspname !~ '^pg_temp_'" in query
    assert "namespace.nspname !~ '^pg_toast_temp_'" in query
    assert "namespace.nspname IN ('public', 'authz_private')" not in query
    assert "relation.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')" in query
    assert "pg_catalog.acldefault('s', relation.relowner)" in query
    assert "pg_catalog.acldefault('r', relation.relowner)" in query


def test_active_role_schema_acl_covers_every_user_defined_schema() -> None:
    """Schema ACL も一時・システム schema だけを母集合から除く。"""
    query = " ".join(
        product_catalog._query_for_id(
            product_catalog.CatalogQueryId.MIGRATION_BATCH_SCHEMA_ACL
        ).split()
    )

    for schema_name in ("pg_catalog", "information_schema", "pg_toast"):
        assert f"'{schema_name}'" in query
    assert "namespace.nspname !~ '^pg_temp_'" in query
    assert "namespace.nspname !~ '^pg_toast_temp_'" in query
    assert "namespace.nspname IN ('public', 'authz_private')" not in query


def test_active_role_column_acl_includes_public_without_a_column_default() -> None:
    """列 ACL は PUBLIC を数える一方、NULL を権限なしとして扱う。"""
    query = " ".join(
        product_catalog._query_for_id(
            product_catalog.CatalogQueryId.MIGRATION_BATCH_TABLE_ACL
        ).split()
    )

    assert "pg_catalog.aclexplode(attribute.attacl)" in query
    assert query.count("privilege.grantee IN (0, %s::pg_catalog.oid)") == 2
    assert "acldefault('c'" not in query
