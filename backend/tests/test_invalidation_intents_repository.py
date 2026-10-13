"""無効化意図の語彙と、製品 DB への記録境界を検査する。"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4

import psycopg
import pytest
from db.test_product_authz_authn_app import _app_dsn
from db_fixtures import (
    ProvisionedProductCatalog,
    _product_migration_url,
    disposable_postgres_cluster,
    provisioned_product_catalog,
)
from test_authz_tenant_context import make_tenant_context

from pitchlog.repositories.cache_invalidation import (
    CacheInvalidationRequest,
    CacheInvalidationTrigger,
    CachePeriod,
    CachePropagationMode,
    CacheScope,
    SharedAggregateCacheKey,
    SharedAggregateTargetSelector,
    build_cache_invalidation_request,
)
from pitchlog.repositories.invalidation_intents import (
    _SCOPE_KIND_BY_SCOPE,
    InvalidationIntentInsertToken,
    record_invalidation_intent,
)
from pitchlog.repositories.transaction import (
    _TenantTransaction,
    tenant_transaction_scope,
)

__all__ = ("disposable_postgres_cluster", "provisioned_product_catalog")

_ROOT = Path(__file__).resolve().parents[2]


def _request(tenant_id: UUID) -> CacheInvalidationRequest:
    """対象テナント単位の検証済み要求を作る。"""
    return build_cache_invalidation_request(
        CacheInvalidationTrigger.ROSTER_STATUS_CHANGE,
        (SharedAggregateTargetSelector(tenant_id),),
    )


def _scope_check_values(checks: list[str]) -> set[str]:
    """scope_kind の CHECK が 1 件あることと列挙値を確かめる。"""
    scope_checks = [
        check
        for check in checks
        if re.fullmatch(
            r"scope_kind\s+IN\s*\(\s*'[^']+'(?:\s*,\s*'[^']+')*\s*\)",
            check,
        )
    ]
    assert len(scope_checks) == 1
    return set(re.findall(r"'([^']+)'", scope_checks[0]))


def test_scope_kind_mapping_is_bijective_with_contract_and_ddl() -> None:
    """契約の 5 範囲と migration・manifest の CHECK を全単射で覆う。"""
    asset = json.loads(
        (
            _ROOT / "contracts/tenant_boundary/cache-invalidation-contract.json"
        ).read_text(encoding="utf-8")
    )
    migration = ast.parse(
        (_ROOT / "backend/migrations/versions/0015_invalidation_intents.py").read_text(
            encoding="utf-8"
        )
    )
    migration_checks = [
        ast.literal_eval(node.args[0])
        for node in ast.walk(migration)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "CheckConstraint"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "sa"
    ]
    schema_manifest = json.loads(
        (_ROOT / "contracts/db/schema-manifest.json").read_text(encoding="utf-8")
    )
    intent_tables = [
        table
        for table in schema_manifest["tables"]
        if table["name"] == "invalidation_intents"
    ]
    assert len(intent_tables) == 1
    contract_scopes = {CacheScope(item["id"]) for item in asset["scopes"]}
    assert len(asset["scopes"]) == len(contract_scopes) == len(CacheScope) == 5
    assert set(_SCOPE_KIND_BY_SCOPE) == contract_scopes
    assert len(set(_SCOPE_KIND_BY_SCOPE.values())) == len(_SCOPE_KIND_BY_SCOPE)
    assert set(_SCOPE_KIND_BY_SCOPE.values()) == _scope_check_values(migration_checks)
    assert set(_SCOPE_KIND_BY_SCOPE.values()) == _scope_check_values(
        intent_tables[0]["checks"]
    )


def test_intent_token_derives_only_defined_identity() -> None:
    """Token から任意の ID や未定義のトリガー・行を作れない。"""
    operation_id = uuid4()
    token = InvalidationIntentInsertToken(
        CacheInvalidationTrigger.ROSTER_STATUS_CHANGE,
        operation_id,
        CacheScope.SHARED_AGGREGATE,
    )
    assert token.intent_id == (
        f"{CacheInvalidationTrigger.ROSTER_STATUS_CHANGE.value}:"
        f"{operation_id}:{CacheScope.SHARED_AGGREGATE.value}"
    )
    unchecked_constructor = cast(Any, InvalidationIntentInsertToken)
    with pytest.raises(TypeError):
        unchecked_constructor(intent_id="invalid")
    with pytest.raises(ValueError, match="在籍区分変更トリガー"):
        InvalidationIntentInsertToken(
            CacheInvalidationTrigger.GRANT_FLAG_CHANGE,
            operation_id,
            CacheScope.SHARED_AGGREGATE,
        )
    with pytest.raises(ValueError, match="operation_id は UUID"):
        InvalidationIntentInsertToken(
            CacheInvalidationTrigger.ROSTER_STATUS_CHANGE,
            cast(UUID, "not-a-uuid"),
            CacheScope.SHARED_AGGREGATE,
        )
    with pytest.raises(ValueError, match="行の識別子"):
        InvalidationIntentInsertToken(
            CacheInvalidationTrigger.ROSTER_STATUS_CHANGE,
            operation_id,
            CacheScope.MATCH,
        )


def test_intent_recording_rejects_other_tenant_trigger_and_key_shape() -> None:
    """未定義の行規則と実行テナントに帰属しない選択子を拒否する。"""
    tenant_id, other_tenant_id = uuid4(), uuid4()

    def unexpected_run(_operation: object) -> None:
        raise AssertionError("拒否した要求から token を実行してはならない")

    scope = cast(
        _TenantTransaction,
        SimpleNamespace(_bound_tenant_id=tenant_id, run=unexpected_run),
    )
    operation_id = uuid4()
    with pytest.raises(ValueError, match="実行中のテナント文脈"):
        record_invalidation_intent(scope, _request(other_tenant_id), operation_id)

    other_trigger = build_cache_invalidation_request(
        CacheInvalidationTrigger.GRANT_FLAG_CHANGE,
        (
            SharedAggregateCacheKey(
                uuid4(), tenant_id, tenant_id, CachePeriod(None, None)
            ),
        ),
    )
    with pytest.raises(ValueError, match="選択子 1 件"):
        record_invalidation_intent(scope, other_trigger, operation_id)

    physical_key_request = CacheInvalidationRequest._create(
        trigger=CacheInvalidationTrigger.ROSTER_STATUS_CHANGE,
        keys=(
            SharedAggregateCacheKey(
                uuid4(), tenant_id, tenant_id, CachePeriod(None, None)
            ),
        ),
        propagation_mode=CachePropagationMode.BY_SCOPE,
        affected_tenant_ids=None,
    )
    with pytest.raises(ValueError, match="選択子 1 件"):
        record_invalidation_intent(scope, physical_key_request, operation_id)


@pytest.mark.requires_db
def test_roster_status_intent_is_one_tenant_scoped_pending_row(
    provisioned_product_catalog: ProvisionedProductCatalog,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """製品 DB で 1 行の列値と他テナントへの RLS 拒否を確認する。"""
    catalog = provisioned_product_catalog
    app_dsn = _app_dsn(catalog)
    monkeypatch.setenv(
        "PITCHLOG_DATABASE_URL", f"{_product_migration_url(app_dsn)}?sslmode=disable"
    )
    monkeypatch.setenv("PITCHLOG_DATABASE_POOLED", "false")
    tenant_id, other_tenant_id, operation_id = uuid4(), uuid4(), uuid4()
    request = _request(tenant_id)
    with tenant_transaction_scope(make_tenant_context(tenant_id)) as scope:
        # INSERT の更新件数は -1(不明)で返るので、行は下の SELECT で確かめる。
        record_invalidation_intent(scope, request, operation_id)

    intent_id = (
        f"{CacheInvalidationTrigger.ROSTER_STATUS_CHANGE.value}:"
        f"{operation_id}:{CacheScope.SHARED_AGGREGATE.value}"
    )
    with catalog.applicator.cursor() as cursor:
        cursor.execute(
            "SELECT tenant_id, intent_id, scope_kind, target_tenant_id, game_id, "
            "player_id, group_id, requesting_tenant_id, period, chart_kind, "
            "delivery_status FROM public.invalidation_intents "
            "WHERE tenant_id = %s AND intent_id = %s",
            (tenant_id, intent_id),
        )
        rows = cursor.fetchall()
        cursor.execute(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conrelid = 'public.invalidation_intents'::regclass "
            "AND contype = 'c' "
            "AND pg_get_constraintdef(oid) LIKE '%scope_kind%'"
        )
        scope_checks = [row[0] for row in cursor.fetchall()]
    assert len(scope_checks) == 1
    assert set(re.findall(r"'([^']+)'", scope_checks[0])) == set(
        _SCOPE_KIND_BY_SCOPE.values()
    )
    assert rows == [
        (
            tenant_id,
            intent_id,
            "shared_total",
            tenant_id,
            None,
            None,
            None,
            None,
            None,
            None,
            "pending",
        )
    ]

    with psycopg.connect(app_dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),)
            )
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cursor.execute(
                    "INSERT INTO public.invalidation_intents "
                    "(tenant_id, intent_id, scope_kind, target_tenant_id) "
                    "VALUES (%s, %s, 'shared_total', %s)",
                    (other_tenant_id, f"foreign:{uuid4()}", other_tenant_id),
                )
