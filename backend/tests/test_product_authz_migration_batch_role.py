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
