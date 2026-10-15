"""試合状態変更の5行意図と製品RLS境界を検査する。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4

import db_fixtures
import psycopg
import pytest
from alembic import command
from alembic.config import Config
from db.test_product_authz_authn_app import _app_dsn
from db_fixtures import (
    ProvisionedProductCatalog,
    _product_migration_url,
    disposable_postgres_cluster,
    provisioned_product_catalog,
)
from psycopg.types.json import Jsonb
from sqlalchemy.exc import IntegrityError
from test_authz_tenant_context import make_tenant_context

from pitchlog.authz.product_catalog import inspect_product_authz_catalog
from pitchlog.db.sync_protocol.models import InvalidationIntent
from pitchlog.repositories.cache_invalidation import (
    AnalyticsChartTargetSelector,
    CacheInvalidationRequest,
    CacheInvalidationTrigger,
    CacheScope,
    MatchCacheKey,
    PlayerCareerTargetSelector,
    SharedAggregateTargetSelector,
    TeamAggregateTargetSelector,
    build_cache_invalidation_request,
)
from pitchlog.repositories.invalidation_intents import (
    InvalidationIntentInsertToken,
    StoredIntentTargetKind,
    classify_stored_intent_target,
    record_game_invalidation_intents,
)
from pitchlog.repositories.transaction import (
    _TenantTransaction,
    tenant_transaction_scope,
)

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_SCOPES = (
    CacheScope.MATCH,
    CacheScope.PLAYER_CAREER,
    CacheScope.TEAM_AGGREGATE,
    CacheScope.SHARED_AGGREGATE,
    CacheScope.ANALYTICS_CHART,
)

__all__ = ("disposable_postgres_cluster", "provisioned_product_catalog")


def _game_request(tenant_id: UUID, game_id: UUID) -> CacheInvalidationRequest:
    """試合の具体鍵と4つの明示選択子を生成する。"""
    return build_cache_invalidation_request(
        CacheInvalidationTrigger.GAME_DELETE_RESTORE_OR_RESUME,
        (
            MatchCacheKey(tenant_id, game_id),
            PlayerCareerTargetSelector(tenant_id),
            TeamAggregateTargetSelector(tenant_id),
            SharedAggregateTargetSelector(tenant_id),
            AnalyticsChartTargetSelector(tenant_id),
        ),
    )


def _use_app_db(
    catalog: ProvisionedProductCatalog,
    monkeypatch: pytest.MonkeyPatch,
) -> str:
    """専用DBの製品利用ロールを既存transaction境界へ渡す。"""
    app_dsn = _app_dsn(catalog)
    monkeypatch.setenv(
        "PITCHLOG_DATABASE_URL", f"{_product_migration_url(app_dsn)}?sslmode=disable"
    )
    monkeypatch.setenv("PITCHLOG_DATABASE_POOLED", "false")
    return app_dsn


def test_game_intent_token_and_request_reject_invalid_inputs() -> None:
    """5行のID、変更試合の一致、範囲外入力を事前に拒否する。"""
    tenant_id, game_id, operation_id = uuid4(), uuid4(), uuid4()
    request = _game_request(tenant_id, game_id)
    seen: list[InvalidationIntentInsertToken] = []

    def run(token: object) -> object:
        assert type(token) is InvalidationIntentInsertToken
        seen.append(token)
        return token

    scope = cast(
        _TenantTransaction, SimpleNamespace(_bound_tenant_id=tenant_id, run=run)
    )
    assert record_game_invalidation_intents(scope, request, operation_id, game_id) == (
        tuple(seen)
    )
    assert [token.row_discriminator for token in seen] == list(_SCOPES)
    assert [token.intent_id for token in seen] == [
        f"game_delete_restore_or_resume:{operation_id}:{game_id}:{scope_id.value}"
        for scope_id in _SCOPES
    ]
    with pytest.raises(ValueError, match="変更済み試合"):
        record_game_invalidation_intents(scope, request, operation_id, uuid4())
    with pytest.raises(ValueError, match="変更済み試合"):
        foreign_scope = cast(
            _TenantTransaction,
            SimpleNamespace(_bound_tenant_id=uuid4(), run=run),
        )
        record_game_invalidation_intents(foreign_scope, request, operation_id, game_id)
    with pytest.raises(ValueError, match="試合状態変更トリガー"):
        record_game_invalidation_intents(
            scope,
            build_cache_invalidation_request(
                CacheInvalidationTrigger.ROSTER_STATUS_CHANGE,
                (SharedAggregateTargetSelector(tenant_id),),
            ),
            operation_id,
            game_id,
        )
    with pytest.raises(ValueError, match="試合IDを渡せない"):
        InvalidationIntentInsertToken(
            CacheInvalidationTrigger.ROSTER_STATUS_CHANGE,
            operation_id,
            CacheScope.SHARED_AGGREGATE,
            game_id,
        )
    with pytest.raises(ValueError, match="試合IDが必要"):
        InvalidationIntentInsertToken(
            CacheInvalidationTrigger.GAME_DELETE_RESTORE_OR_RESUME,
            operation_id,
            CacheScope.MATCH,
        )
    with pytest.raises(ValueError, match="だけを記録できる"):
        InvalidationIntentInsertToken(
            CacheInvalidationTrigger.GRANT_FLAG_CHANGE,
            operation_id,
            CacheScope.SHARED_AGGREGATE,
        )


def test_legacy_target_classification_holds_ambiguous_rows() -> None:
    """旧14選択子・5種の物理鍵を分け、不正NULL行を配信保留にする。"""
    tenant_id = uuid4()
    shared = InvalidationIntent(
        tenant_id=tenant_id,
        intent_id=f"roster_status_change:{uuid4()}:shared_aggregate",
        scope_kind="shared_total",
        target_tenant_id=tenant_id,
    )
    assert classify_stored_intent_target(shared) is (
        StoredIntentTargetKind.LEGACY_SHARED_SELECTOR
    )
    shared.intent_id = "roster_status_change:not-a-uuid:shared_aggregate"
    assert classify_stored_intent_target(shared) is StoredIntentTargetKind.DELIVERY_HOLD
    shared.intent_id = f"roster_status_change:{uuid4()}:shared_aggregate"
    shared.target_tenant_id = uuid4()
    assert classify_stored_intent_target(shared) is StoredIntentTargetKind.DELIVERY_HOLD

    physical_rows = (
        InvalidationIntent(
            tenant_id=tenant_id,
            intent_id="old-game",
            scope_kind="game",
            game_id=uuid4(),
        ),
        InvalidationIntent(
            tenant_id=tenant_id,
            intent_id="old-player",
            scope_kind="player_total",
            player_id=uuid4(),
            period={"season": 2026},
        ),
        InvalidationIntent(
            tenant_id=tenant_id,
            intent_id="old-team",
            scope_kind="team_total",
            period={"season": 2026},
        ),
        InvalidationIntent(
            tenant_id=tenant_id,
            intent_id="old-shared",
            scope_kind="shared_total",
            group_id=uuid4(),
            requesting_tenant_id=uuid4(),
            target_tenant_id=tenant_id,
            period={"season": 2026},
        ),
        InvalidationIntent(
            tenant_id=tenant_id,
            intent_id="old-chart",
            scope_kind="chart",
            player_id=uuid4(),
            chart_kind="pitch_location",
        ),
    )
    for physical in physical_rows:
        assert classify_stored_intent_target(physical) is (
            StoredIntentTargetKind.LEGACY_PHYSICAL_KEY
        )
    physical_rows[3].target_tenant_id = uuid4()
    assert classify_stored_intent_target(physical_rows[3]) is (
        StoredIntentTargetKind.DELIVERY_HOLD
    )
    physical_rows[0].player_id = uuid4()
    assert classify_stored_intent_target(physical_rows[0]) is (
        StoredIntentTargetKind.DELIVERY_HOLD
    )
    physical_rows[-1].game_id = uuid4()
    assert classify_stored_intent_target(physical_rows[-1]) is (
        StoredIntentTargetKind.DELIVERY_HOLD
    )
    explicit = InvalidationIntent(
        tenant_id=tenant_id,
        intent_id="explicit",
        scope_kind="chart",
        target_selector_kind="tenant_scope",
    )
    assert classify_stored_intent_target(explicit) is (
        StoredIntentTargetKind.EXPLICIT_SELECTOR
    )


@pytest.mark.requires_db
def test_game_intents_five_rows_rls_immutability_and_rollback(
    provisioned_product_catalog: ProvisionedProductCatalog,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """製品RLSの専用DBで5行・越境拒否・不変性・失敗時取消を検査する。"""
    catalog = provisioned_product_catalog
    app_dsn = _use_app_db(catalog, monkeypatch)
    with catalog.applicator.cursor() as cursor:
        cursor.execute(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
            "WHERE oid = 'public.invalidation_intents'::regclass"
        )
        assert cursor.fetchone() == (True, True)
        cursor.execute(
            "SELECT policyname, permissive, cmd FROM pg_policies "
            "WHERE schemaname = 'public' AND tablename = 'invalidation_intents'"
        )
        assert cursor.fetchall() == [("pitchlog_app_tenant_owned", "PERMISSIVE", "ALL")]
        cursor.execute(
            "SELECT has_table_privilege('pitchlog_app', "
            "'public.invalidation_intents', 'SELECT'), "
            "has_table_privilege('pitchlog_app', "
            "'public.invalidation_intents', 'INSERT'), "
            "has_table_privilege('pitchlog_app', "
            "'public.invalidation_intents', 'UPDATE'), "
            "has_table_privilege('pitchlog_app', "
            "'public.invalidation_intents', 'DELETE')"
        )
        assert cursor.fetchone() == (True, True, True, False)
    catalog.applicator.rollback()
    tenant_id, other_tenant_id = uuid4(), uuid4()
    game_id, operation_id = uuid4(), uuid4()
    with tenant_transaction_scope(make_tenant_context(tenant_id)) as scope:
        record_game_invalidation_intents(
            scope, _game_request(tenant_id, game_id), operation_id, game_id
        )

    with psycopg.connect(app_dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),)
            )
            cursor.execute(
                "SELECT scope_kind, target_selector_kind, game_id, target_tenant_id "
                "FROM public.invalidation_intents WHERE tenant_id = %s "
                "ORDER BY intent_id",
                (tenant_id,),
            )
            rows = cursor.fetchall()
            assert len(rows) == 5
            assert set(rows) == {
                ("game", "concrete_game", game_id, None),
                ("player_total", "tenant_scope", None, None),
                ("team_total", "tenant_scope", None, None),
                ("shared_total", "shared_target_tenant", None, tenant_id),
                ("chart", "tenant_scope", None, None),
            }
    with psycopg.connect(app_dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT set_config('app.tenant_id', %s, true)",
                (str(other_tenant_id),),
            )
            cursor.execute("SELECT count(*) FROM public.invalidation_intents")
            assert cursor.fetchone() == (0,)
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cursor.execute(
                    "INSERT INTO public.invalidation_intents "
                    "(tenant_id, intent_id, scope_kind) VALUES (%s, %s, 'game')",
                    (tenant_id, "foreign-write"),
                )

    intent_id = f"game_delete_restore_or_resume:{operation_id}:{game_id}:match"
    with psycopg.connect(app_dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),)
            )
            with pytest.raises(psycopg.errors.CheckViolation, match="immutable"):
                cursor.execute(
                    "UPDATE public.invalidation_intents "
                    "SET target_selector_kind = 'tenant_scope' "
                    "WHERE tenant_id = %s AND intent_id = %s",
                    (tenant_id, intent_id),
                )

    failed_operation = uuid4()
    duplicate_id = (
        f"game_delete_restore_or_resume:{failed_operation}:{game_id}:analytics_chart"
    )
    with psycopg.connect(app_dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),)
            )
            cursor.execute(
                "INSERT INTO public.invalidation_intents "
                "(tenant_id, intent_id, scope_kind, target_selector_kind) "
                "VALUES (%s, %s, 'chart', 'tenant_scope')",
                (tenant_id, duplicate_id),
            )
    with pytest.raises(IntegrityError):
        with tenant_transaction_scope(make_tenant_context(tenant_id)) as scope:
            record_game_invalidation_intents(
                scope, _game_request(tenant_id, game_id), failed_operation, game_id
            )
    with psycopg.connect(app_dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),)
            )
            cursor.execute(
                "SELECT intent_id FROM public.invalidation_intents "
                "WHERE intent_id LIKE %s",
                (f"game_delete_restore_or_resume:{failed_operation}:%",),
            )
            assert cursor.fetchall() == [(duplicate_id,)]


@pytest.mark.requires_db
def test_selector_check_rejects_malformed_rows(
    provisioned_product_catalog: ProvisionedProductCatalog,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ID・列形・他テナント共有指定の抜け道をDBで拒否する。"""
    app_dsn = _use_app_db(provisioned_product_catalog, monkeypatch)
    tenant_id, game_id, foreign_tenant = uuid4(), uuid4(), uuid4()
    operation_id = uuid4()
    valid_id = f"game_delete_restore_or_resume:{operation_id}:{game_id}:match"
    cases: tuple[tuple[str, str, str | None, UUID | None, UUID | None], ...] = (
        (valid_id, "game", None, game_id, None),
        ("game_delete_restore_or_resume:bad", "game", "concrete_game", game_id, None),
        (valid_id, "game", "concrete_game", uuid4(), None),
        (valid_id, "chart", "concrete_game", game_id, None),
        (valid_id, "game", "tenant_scope", game_id, None),
        (
            f"game_delete_restore_or_resume:{operation_id}:{game_id}:shared_aggregate",
            "shared_total",
            "shared_target_tenant",
            None,
            foreign_tenant,
        ),
    )
    for intent_id, scope_kind, selector_kind, row_game_id, target_tenant_id in cases:
        with psycopg.connect(app_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT set_config('app.tenant_id', %s, true)",
                    (str(tenant_id),),
                )
                with pytest.raises(psycopg.errors.CheckViolation):
                    cursor.execute(
                        "INSERT INTO public.invalidation_intents "
                        "(tenant_id, intent_id, scope_kind, target_selector_kind, "
                        "game_id, target_tenant_id) VALUES (%s, %s, %s, %s, %s, %s)",
                        (
                            tenant_id,
                            intent_id,
                            scope_kind,
                            selector_kind,
                            row_game_id,
                            target_tenant_id,
                        ),
                    )


@pytest.mark.requires_db
def test_selector_migration_preserves_legacy_rows_under_force_rls(
    provisioned_product_catalog: ProvisionedProductCatalog,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FORCE RLSのまま往復し、旧行保持と新行のdowngrade拒否を確認する。"""
    if db_fixtures._external_product_catalog is not None:
        pytest.skip("DDL往復は使い捨て製品DBに限る")
    catalog = provisioned_product_catalog
    app_dsn = _use_app_db(catalog, monkeypatch)
    tenant_id = uuid4()
    with psycopg.connect(app_dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),)
            )
            cursor.execute(
                "INSERT INTO public.invalidation_intents "
                "(tenant_id, intent_id, scope_kind, target_tenant_id) "
                "VALUES (%s, %s, 'shared_total', %s)",
                (
                    tenant_id,
                    f"roster_status_change:{uuid4()}:shared_aggregate",
                    tenant_id,
                ),
            )
            cursor.execute(
                "INSERT INTO public.invalidation_intents "
                "(tenant_id, intent_id, scope_kind, game_id) "
                "VALUES (%s, 'legacy-physical-game', 'game', %s)",
                (tenant_id, uuid4()),
            )
            cursor.execute(
                "INSERT INTO public.invalidation_intents "
                "(tenant_id, intent_id, scope_kind, group_id, "
                "requesting_tenant_id, target_tenant_id, period) "
                "VALUES (%s, 'legacy-physical-shared', 'shared_total', "
                "%s, %s, %s, %s)",
                (tenant_id, uuid4(), uuid4(), tenant_id, Jsonb({"season": 2026})),
            )
    config = Config(str(_BACKEND_ROOT / "alembic.ini"))
    command.downgrade(config, "0030_seed_game_type")
    with psycopg.connect(catalog.owner_dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_get_triggerdef(t.oid) "
                "FROM pg_trigger t "
                "WHERE t.tgrelid = 'public.invalidation_intents'::regclass "
                "AND t.tgname = 'trg_invalidation_intents_target_immutable'"
            )
            old_trigger = cursor.fetchone()
            assert old_trigger is not None
            assert "target_selector_kind" not in old_trigger[0]
            assert "chart_kind" in old_trigger[0]
            cursor.execute(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_schema = 'public' "
                "AND table_name = 'invalidation_intents' "
                "AND column_name = 'target_selector_kind'"
            )
            assert cursor.fetchone() == (0,)
    command.upgrade(config, "0031_intent_selectors")
    with psycopg.connect(catalog.owner_dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT relrowsecurity, relforcerowsecurity "
                "FROM pg_class WHERE oid = 'public.invalidation_intents'::regclass"
            )
            assert cursor.fetchone() == (True, True)
            cursor.execute(
                "SELECT conname FROM pg_constraint "
                "WHERE conrelid = 'public.invalidation_intents'::regclass "
                "AND conname LIKE 'ck_invalidation_intents_selector_%'"
            )
            assert {row[0] for row in cursor.fetchall()} == {
                "ck_invalidation_intents_selector_values",
                "ck_invalidation_intents_selector_identity",
                "ck_invalidation_intents_selector_shape",
            }
            cursor.execute(
                "SELECT pg_get_triggerdef(t.oid) "
                "FROM pg_trigger t "
                "WHERE t.tgrelid = 'public.invalidation_intents'::regclass "
                "AND t.tgname = 'trg_invalidation_intents_target_immutable'"
            )
            new_trigger = cursor.fetchone()
            assert new_trigger is not None
            assert "target_selector_kind" in new_trigger[0]
    with psycopg.connect(app_dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),)
            )
            cursor.execute(
                "SELECT count(*), count(target_selector_kind) "
                "FROM public.invalidation_intents WHERE tenant_id = %s",
                (tenant_id,),
            )
            assert cursor.fetchone() == (3, 0)
    with tenant_transaction_scope(make_tenant_context(tenant_id)) as scope:
        game_id = uuid4()
        record_game_invalidation_intents(
            scope, _game_request(tenant_id, game_id), uuid4(), game_id
        )
    with pytest.raises(IntegrityError):
        command.downgrade(config, "0030_seed_game_type")


@pytest.mark.requires_db
def test_extra_permissive_policy_is_rejected_by_catalog(
    provisioned_product_catalog: ProvisionedProductCatalog,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """追加PERMISSIVEのOR越境を専用DBだけで再現し、カタログを赤にする。"""
    if db_fixtures._external_product_catalog is not None:
        pytest.skip("追加policyの負例は使い捨て製品DBに限る")
    catalog = provisioned_product_catalog
    app_dsn = _use_app_db(catalog, monkeypatch)
    tenant_id, other_tenant_id = uuid4(), uuid4()
    with psycopg.connect(app_dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),)
            )
            cursor.execute(
                "INSERT INTO public.invalidation_intents "
                "(tenant_id, intent_id, scope_kind) VALUES (%s, %s, 'game')",
                (tenant_id, "legacy-game"),
            )
    with catalog.applicator.cursor() as cursor:
        cursor.execute(
            "CREATE POLICY test_extra_permissive ON public.invalidation_intents "
            "AS PERMISSIVE FOR SELECT TO pitchlog_app USING (true)"
        )
        cursor.execute("SELECT oid FROM pg_roles WHERE rolname = current_user")
        row = cursor.fetchone()
    catalog.applicator.commit()
    assert row is not None and type(row[0]) is int
    try:
        with psycopg.connect(app_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT set_config('app.tenant_id', %s, true)",
                    (str(other_tenant_id),),
                )
                cursor.execute("SELECT count(*) FROM public.invalidation_intents")
                assert cursor.fetchone() == (1,)
        report = inspect_product_authz_catalog(
            catalog.observer, privileged_role_oids=frozenset({row[0]})
        )
        assert not report.ok
        assert "PRODUCT-CATALOG:POLICIES" in {
            violation.check_id for violation in report.violations
        }
    finally:
        catalog.observer.rollback()
        with catalog.applicator.cursor() as cursor:
            cursor.execute(
                "DROP POLICY test_extra_permissive ON public.invalidation_intents"
            )
        catalog.applicator.commit()
