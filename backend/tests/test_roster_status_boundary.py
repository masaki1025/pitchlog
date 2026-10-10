"""在籍区分の HTTP 入口と無効化意図の発火境界を実 DB で検査する。"""

from __future__ import annotations

import base64
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Protocol, cast
from uuid import UUID, uuid4

import pytest
from db.test_product_authz_authn_app import (
    _app_dsn,
    _login,
    _seed_identity,
    _seed_settings,
)
from db_fixtures import (
    ProvisionedProductCatalog,
    _product_migration_url,
    disposable_postgres_cluster,
    provisioned_product_catalog,
)
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import IntegrityError

from pitchlog.api.app import create_app
from pitchlog.api.routers import players
from pitchlog.api.schemas.roster import PlayerStatusBulkRequest
from pitchlog.authz.token_presentation import TokenPresentation
from pitchlog.repositories.cache_invalidation import (
    CacheInvalidationTrigger,
    CacheScope,
)
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.invalidation_intents import InvalidationIntentInsertToken
from pitchlog.repositories.roster import (
    PlayerReadToken,
    PlayerRosterLabelUpdateToken,
    PlayerRosterStatusUpdateToken,
)
from pitchlog.repositories.tokens import TenantOperationResult, TenantOperationToken

__all__ = ("disposable_postgres_cluster", "provisioned_product_catalog")

_ORIGIN = "https://roster-status.example"
_STATUSES = ("active", "other", "ob")


class _OperationScope(Protocol):
    """競合テストで包む実トランザクションの最小操作面。"""

    def run(self, operation: TenantOperationToken) -> TenantOperationResult:
        """登録済み操作を実行する。"""


def _body(
    player_ids: list[UUID], status: str, label: str | None = None
) -> dict[str, object]:
    """在籍区分の一括要求を作る。"""
    return {
        "player_ids": [str(player_id) for player_id in player_ids],
        "roster_status_key": status,
        "roster_label_key": label,
    }


def _headers() -> dict[str, str]:
    """既存の状態変更入口と同じ CSRF 条件を付ける。"""
    return {"X-Pitchlog-Request": "1", "Origin": _ORIGIN}


def _player_state(
    catalog: ProvisionedProductCatalog, tenant_id: UUID, player_id: UUID
) -> tuple[str, str | None]:
    """DB の区分とラベルを直接確認する。"""
    with catalog.applicator.cursor() as cursor:
        cursor.execute(
            "SELECT roster_status_key, roster_label_key FROM public.players "
            "WHERE tenant_id = %s AND id = %s",
            (tenant_id, player_id),
        )
        row = cursor.fetchone()
    catalog.applicator.rollback()
    assert row is not None
    return cast(tuple[str, str | None], row)


def _intents(
    catalog: ProvisionedProductCatalog, tenant_id: UUID
) -> list[tuple[str, str, UUID, str]]:
    """DB に確定した無効化意図の対象と状態を読む。"""
    with catalog.applicator.cursor() as cursor:
        cursor.execute(
            "SELECT intent_id, scope_kind, target_tenant_id, delivery_status "
            "FROM public.invalidation_intents WHERE tenant_id = %s "
            "ORDER BY intent_id",
            (tenant_id,),
        )
        rows = cursor.fetchall()
    catalog.applicator.rollback()
    return cast(list[tuple[str, str, UUID, str]], rows)


def test_status_entry_emits_only_for_changed_rows_without_db(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """入口が区分の更新件数で意図を発火し、ラベルだけでは発火しない。"""
    tenant_id, team_id, player_id = uuid4(), uuid4(), uuid4()
    status = "active"
    label: str | None = None
    intent_ids: list[str] = []

    class Handle:
        _bound_tenant_id = tenant_id

        def run(self, operation: TenantOperationToken) -> TenantOperationResult:
            """1 行の token と意図 token の結果を記録する。"""
            nonlocal status, label
            if isinstance(operation, PlayerReadToken):
                assert operation.record_id == player_id
                return TenantOperationResult(
                    ((player_id, team_id, "甲", None, None, None, status, label, None),)
                )
            if isinstance(operation, PlayerRosterStatusUpdateToken):
                if status == operation.roster_status_key:
                    return TenantOperationResult(((0,),))
                status = operation.roster_status_key
                if operation.update_label:
                    label = operation.roster_label_key
                return TenantOperationResult(((1,),))
            if isinstance(operation, PlayerRosterLabelUpdateToken):
                label = operation.roster_label_key
                return TenantOperationResult(((1,),))
            if isinstance(operation, InvalidationIntentInsertToken):
                intent_ids.append(operation.intent_id)
                return TenantOperationResult(((-1,),))
            raise AssertionError("未登録の操作")

    @contextmanager
    def scope(_context: TenantContext) -> Iterator[Handle]:
        """同一の模擬トランザクションハンドルを渡す。"""
        yield Handle()

    monkeypatch.setattr(players, "tenant_transaction_scope", scope)
    context = cast(TenantContext, SimpleNamespace(tenant_id=tenant_id))
    before = players.preview_player_status(
        PlayerStatusBulkRequest.model_validate(_body([player_id], "other")), context
    )
    assert before.changes[0].before_status_key == "active"
    assert status == "active" and intent_ids == []

    changed = players.apply_player_status(
        PlayerStatusBulkRequest.model_validate(_body([player_id], "other")), context
    )
    assert changed.applied[0].roster_status_key == "other"
    assert len(intent_ids) == 1
    label_only = players.apply_player_status(
        PlayerStatusBulkRequest.model_validate(
            _body([player_id], "other", "status-label")
        ),
        context,
    )
    assert label_only.applied[0].roster_label_key == "status-label"
    assert status == "other" and len(intent_ids) == 1
    players.apply_player_status(
        PlayerStatusBulkRequest.model_validate(_body([player_id], "ob")), context
    )
    assert status == "ob" and label is None
    assert len(intent_ids) == len(set(intent_ids)) == 2


@pytest.mark.parametrize(
    ("constraint_name", "sqlstate", "expected_status"),
    (
        ("fk_players_roster_status", "23503", 404),
        ("fk_players_roster_label", "23503", 404),
        ("fk_players_team", "23503", None),
        ("other_constraint", "23503", None),
        ("fk_players_roster_status", "23505", None),
    ),
)
def test_status_entry_maps_only_status_and_label_reference_errors_without_db(
    monkeypatch: pytest.MonkeyPatch,
    constraint_name: str,
    sqlstate: str,
    expected_status: int | None,
) -> None:
    """区分・ラベルの外部キー違反だけを選手作成と同じ 404 に写す。"""

    class OriginError(Exception):
        def __init__(self) -> None:
            super().__init__("参照先を利用できない")
            self.sqlstate = sqlstate
            self.diag = SimpleNamespace(constraint_name=constraint_name)

    error = IntegrityError("UPDATE players", {}, OriginError())

    def fail(*_args: object) -> None:
        raise error

    monkeypatch.setattr(players, "_apply_player_status_in_transaction", fail)
    body = PlayerStatusBulkRequest.model_validate(_body([uuid4()], "other"))
    context = cast(TenantContext, SimpleNamespace(tenant_id=uuid4()))
    if expected_status is None:
        with pytest.raises(IntegrityError) as raised:
            players.apply_player_status(body, context)
        assert raised.value is error
    else:
        with pytest.raises(HTTPException) as raised:
            players.apply_player_status(body, context)
        assert raised.value.status_code == expected_status


@pytest.mark.requires_db
@pytest.mark.anyio
async def test_real_roster_status_http_boundary_and_atomic_intents(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """可逆性・越境拒否・発火条件・失敗時の巻き戻しを検査する。"""
    catalog = cast(
        ProvisionedProductCatalog,
        request.getfixturevalue("provisioned_product_catalog"),
    )
    _seed_settings(catalog)
    app_dsn = _app_dsn(catalog)
    tenant_a = _seed_identity(catalog, app_dsn)
    tenant_b = _seed_identity(catalog, app_dsn)
    token_a, token_b = _login(tenant_a), _login(tenant_b)
    assert isinstance(token_a, UUID)
    assert isinstance(token_b, UUID)
    self_team, opponent_team, foreign_team = uuid4(), uuid4(), uuid4()
    main_player, opponent_player, hidden_player, foreign_player = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    matrix_players = {
        (before, after): uuid4() for before in _STATUSES for after in _STATUSES
    }
    with catalog.applicator.cursor() as cursor:
        for status, display_name in (
            ("active", "現役"),
            ("other", "その他"),
            ("ob", "OB"),
        ):
            cursor.execute(
                "INSERT INTO public.system_vocabularies "
                "(key, category, display_name) VALUES (%s, 'roster_status', %s) "
                "ON CONFLICT DO NOTHING",
                (status, display_name),
            )
        cursor.execute(
            "INSERT INTO public.tenant_vocabularies "
            "(tenant_id, key, category, display_name) "
            "VALUES (%s, 'status-label', 'roster_label', '表示ラベル')",
            (tenant_a.tenant_id,),
        )
        cursor.execute(
            "INSERT INTO public.tenant_vocabularies "
            "(tenant_id, key, category, display_name) "
            "VALUES (%s, 'foreign-label', 'roster_label', '別テナントのラベル')",
            (tenant_b.tenant_id,),
        )
        for tenant_id, team_id, kind in (
            (tenant_a.tenant_id, self_team, "self"),
            (tenant_a.tenant_id, opponent_team, "opponent"),
            (tenant_b.tenant_id, foreign_team, "self"),
        ):
            cursor.execute(
                "INSERT INTO public.team_records (tenant_id, id, kind, name) "
                "VALUES (%s, %s, %s, %s)",
                (tenant_id, team_id, kind, f"{kind}-{team_id}"),
            )
        for tenant_id, player_id, team_id, status, hidden in (
            (tenant_a.tenant_id, main_player, self_team, "active", False),
            (tenant_a.tenant_id, opponent_player, opponent_team, "active", False),
            (tenant_a.tenant_id, hidden_player, self_team, "active", True),
            (tenant_b.tenant_id, foreign_player, foreign_team, "active", False),
            *(
                (tenant_a.tenant_id, player_id, self_team, before, False)
                for (before, _), player_id in matrix_players.items()
            ),
        ):
            cursor.execute(
                "INSERT INTO public.players "
                "(tenant_id, id, team_record_id, name, roster_status_key, hidden_at) "
                "VALUES (%s, %s, %s, %s, %s, "
                "CASE WHEN %s THEN pg_catalog.clock_timestamp() ELSE NULL END)",
                (tenant_id, player_id, team_id, f"選手-{player_id}", status, hidden),
            )
    catalog.applicator.commit()

    monkeypatch.setenv(
        "PITCHLOG_DATABASE_URL", f"{_product_migration_url(app_dsn)}?sslmode=disable"
    )
    monkeypatch.setenv("PITCHLOG_DATABASE_POOLED", "false")
    monkeypatch.setenv("PITCHLOG_ALLOWED_ORIGINS", _ORIGIN)
    monkeypatch.setenv(
        "PITCHLOG_TOKEN_SIGNING_KEY_B64",
        base64.b64encode(secrets.token_bytes(32)).decode("ascii"),
    )
    app = create_app()
    signer: TokenPresentation = app.state.token_presentation
    presented_a, presented_b = signer.encode(token_a), signer.encode(token_b)
    missing_player = uuid4()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        client.cookies.set("__Host-pitchlog_token", presented_a)
        preview = await client.post(
            "/players/status-preview",
            json=_body([main_player], "other"),
            headers=_headers(),
        )
        assert preview.status_code == 200
        assert preview.json()["changes"][0]["player_id"] == str(main_player)
        assert preview.json()["changes"][0]["before_status_key"] == "active"
        assert preview.json()["changes"][0]["after_status_key"] == "other"
        assert preview.json()["unchanged_player_ids"] == []
        assert preview.json()["not_found_player_ids"] == []
        unchanged_preview = await client.post(
            "/players/status-preview",
            json=_body([main_player], "active"),
            headers=_headers(),
        )
        assert unchanged_preview.status_code == 200
        assert unchanged_preview.json()["changes"] == []
        assert unchanged_preview.json()["unchanged_player_ids"] == [str(main_player)]
        assert _player_state(catalog, tenant_a.tenant_id, main_player) == (
            "active",
            None,
        )
        assert _intents(catalog, tenant_a.tenant_id) == []

        for status, label in (
            ("missing-status", None),
            ("active", "foreign-label"),
            ("other", "missing-label"),
        ):
            invalid_reference = await client.post(
                "/players/status-apply",
                json=_body([main_player], status, label),
                headers=_headers(),
            )
            assert invalid_reference.status_code == 404
            assert invalid_reference.json() == {
                "error": {"message": "対象が見つかりません"}
            }
            assert _player_state(catalog, tenant_a.tenant_id, main_player) == (
                "active",
                None,
            )
            assert _intents(catalog, tenant_a.tenant_id) == []

        for (before, after), player_id in matrix_players.items():
            result = await client.post(
                "/players/status-apply",
                json=_body([player_id], after),
                headers=_headers(),
            )
            assert result.status_code == 200
            assert result.json()["applied"][0]["roster_status_key"] == after
            assert result.json()["not_found_player_ids"] == []
            assert _player_state(catalog, tenant_a.tenant_id, player_id)[0] == after
            if before == after:
                assert result.json()["applied"][0]["id"] == str(player_id)
        assert len(_intents(catalog, tenant_a.tenant_id)) == 6

        for player_id in (foreign_player, missing_player, hidden_player):
            body = _body([player_id], "other")
            for path in ("/players/status-preview", "/players/status-apply"):
                response = await client.post(path, json=body, headers=_headers())
                assert response.status_code == 200
                assert response.json()["not_found_player_ids"] == [str(player_id)]
                assert (
                    response.json().get("applied", response.json().get("changes")) == []
                )
        assert len(_intents(catalog, tenant_a.tenant_id)) == 6
        assert _player_state(catalog, tenant_b.tenant_id, foreign_player)[0] == "active"

        label_only = await client.post(
            "/players/status-apply",
            json=_body([main_player], "active", "status-label"),
            headers=_headers(),
        )
        assert label_only.status_code == 200
        assert label_only.json()["applied"][0]["roster_label_key"] == "status-label"
        assert _player_state(catalog, tenant_a.tenant_id, main_player) == (
            "active",
            "status-label",
        )
        assert len(_intents(catalog, tenant_a.tenant_id)) == 6
        clear_label = await client.post(
            "/players/status-apply",
            json=_body([main_player], "active"),
            headers=_headers(),
        )
        assert clear_label.status_code == 200
        assert clear_label.json()["applied"][0]["roster_label_key"] is None
        assert len(_intents(catalog, tenant_a.tenant_id)) == 6

        first_change = await client.post(
            "/players/status-apply",
            json=_body([main_player], "other"),
            headers=_headers(),
        )
        assert first_change.status_code == 200
        assert first_change.json()["applied"][0]["roster_status_key"] == "other"
        assert len(_intents(catalog, tenant_a.tenant_id)) == 7
        no_change = await client.post(
            "/players/status-apply",
            json=_body([main_player], "other"),
            headers=_headers(),
        )
        assert no_change.status_code == 200
        assert len(_intents(catalog, tenant_a.tenant_id)) == 7
        second_change = await client.post(
            "/players/status-apply",
            json=_body([main_player], "ob"),
            headers=_headers(),
        )
        assert second_change.status_code == 200
        intents = _intents(catalog, tenant_a.tenant_id)
        assert len(intents) == 8
        assert len({intent_id for intent_id, _, _, _ in intents}) == 8
        for intent_id, scope_kind, target_tenant_id, delivery_status in intents:
            trigger, operation_id, row_discriminator = intent_id.split(":")
            assert trigger == CacheInvalidationTrigger.ROSTER_STATUS_CHANGE.value
            assert isinstance(UUID(operation_id), UUID)
            assert row_discriminator == CacheScope.SHARED_AGGREGATE.value
            assert (scope_kind, target_tenant_id, delivery_status) == (
                "shared_total",
                tenant_a.tenant_id,
                "pending",
            )

        opponent = await client.post(
            "/players/status-apply",
            json=_body([opponent_player], "ob"),
            headers=_headers(),
        )
        assert opponent.status_code == 200
        assert opponent.json()["applied"][0]["roster_status_key"] == "ob"
        assert len(_intents(catalog, tenant_a.tenant_id)) == 9

        bulk = await client.post(
            "/players/status-apply",
            json=_body(
                [
                    matrix_players[("active", "active")],
                    matrix_players[("other", "active")],
                ],
                "ob",
            ),
            headers=_headers(),
        )
        assert bulk.status_code == 200
        assert len(bulk.json()["applied"]) == 2
        assert len(_intents(catalog, tenant_a.tenant_id)) == 10

        fifty = await client.post(
            "/players/status-preview",
            json=_body([uuid4() for _ in range(50)], "active"),
            headers=_headers(),
        )
        fifty_one = await client.post(
            "/players/status-apply",
            json=_body([uuid4() for _ in range(51)], "active"),
            headers=_headers(),
        )
        assert fifty.status_code == 200
        assert len(fifty.json()["not_found_player_ids"]) == 50
        assert fifty_one.status_code == 422

        for path in ("/players/status-preview", "/players/status-apply"):
            client.cookies.clear()
            no_cookie = await client.post(
                path, json=_body([main_player], "active"), headers=_headers()
            )
            assert no_cookie.status_code == 401
            client.cookies.set("__Host-pitchlog_token", presented_a)
            no_csrf = await client.post(path, json=_body([main_player], "active"))
            assert no_csrf.status_code == 403

        client.cookies.set("__Host-pitchlog_token", presented_b)
        foreign_response = await client.post(
            "/players/status-apply",
            json=_body([main_player], "active"),
            headers=_headers(),
        )
        absent_response = await client.post(
            "/players/status-apply",
            json=_body([missing_player], "active"),
            headers=_headers(),
        )
        assert foreign_response.status_code == absent_response.status_code == 200
        assert foreign_response.json() == {
            "applied": [],
            "not_found_player_ids": [str(main_player)],
        }
        assert absent_response.json() == {
            "applied": [],
            "not_found_player_ids": [str(missing_player)],
        }

        client.cookies.set("__Host-pitchlog_token", presented_a)

        def failed_intent(*_args: object) -> None:
            raise RuntimeError("意図の記録に失敗")

        monkeypatch.setattr(players, "record_invalidation_intent", failed_intent)
        with pytest.raises(RuntimeError, match="意図の記録に失敗"):
            await client.post(
                "/players/status-apply",
                json=_body([main_player], "active"),
                headers=_headers(),
            )
        assert _player_state(catalog, tenant_a.tenant_id, main_player)[0] == "ob"
        assert len(_intents(catalog, tenant_a.tenant_id)) == 10


@pytest.mark.requires_db
@pytest.mark.anyio
async def test_real_roster_status_stale_read_does_not_emit_intent(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """読み取り後に更新件数が 0 ならラベルだけを更新し意図を残さない。"""
    catalog = cast(
        ProvisionedProductCatalog,
        request.getfixturevalue("provisioned_product_catalog"),
    )
    _seed_settings(catalog)
    app_dsn = _app_dsn(catalog)
    tenant = _seed_identity(catalog, app_dsn)
    token = _login(tenant)
    assert isinstance(token, UUID)
    team_id, player_id = uuid4(), uuid4()
    with catalog.applicator.cursor() as cursor:
        for status, display_name in (("active", "現役"), ("other", "その他")):
            cursor.execute(
                "INSERT INTO public.system_vocabularies "
                "(key, category, display_name) VALUES (%s, 'roster_status', %s) "
                "ON CONFLICT DO NOTHING",
                (status, display_name),
            )
        cursor.execute(
            "INSERT INTO public.tenant_vocabularies "
            "(tenant_id, key, category, display_name) "
            "VALUES (%s, 'status-label', 'roster_label', '表示ラベル')",
            (tenant.tenant_id,),
        )
        cursor.execute(
            "INSERT INTO public.team_records (tenant_id, id, kind, name) "
            "VALUES (%s, %s, 'self', '自チーム')",
            (tenant.tenant_id, team_id),
        )
        cursor.execute(
            "INSERT INTO public.players "
            "(tenant_id, id, team_record_id, name, roster_status_key) "
            "VALUES (%s, %s, %s, '選手', 'other')",
            (tenant.tenant_id, player_id, team_id),
        )
    catalog.applicator.commit()

    monkeypatch.setenv(
        "PITCHLOG_DATABASE_URL", f"{_product_migration_url(app_dsn)}?sslmode=disable"
    )
    monkeypatch.setenv("PITCHLOG_DATABASE_POOLED", "false")
    monkeypatch.setenv("PITCHLOG_ALLOWED_ORIGINS", _ORIGIN)
    monkeypatch.setenv(
        "PITCHLOG_TOKEN_SIGNING_KEY_B64",
        base64.b64encode(secrets.token_bytes(32)).decode("ascii"),
    )
    app = create_app()
    signer: TokenPresentation = app.state.token_presentation
    real_scope = players.tenant_transaction_scope
    stale_read_count = 0

    class StaleReadHandle:
        def __init__(self, scope: _OperationScope) -> None:
            self.scope = scope

        def run(self, operation: TenantOperationToken) -> TenantOperationResult:
            """最初の読み取りだけ実際より古い区分に差し替える。"""
            nonlocal stale_read_count
            actual = self.scope.run(operation)
            if (
                isinstance(operation, PlayerReadToken)
                and operation.record_id == player_id
                and stale_read_count == 0
            ):
                stale_read_count += 1
                assert len(actual.rows) == 1
                row = actual.rows[0]
                return TenantOperationResult((row[:6] + ("active",) + row[7:],))
            return actual

    @contextmanager
    def stale_scope(context: TenantContext) -> Iterator[StaleReadHandle]:
        """実 DB のスコープに最初の読み取りの差し替えを重ねる。"""
        with real_scope(context) as scope:
            yield StaleReadHandle(scope)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        client.cookies.set("__Host-pitchlog_token", signer.encode(token))
        with monkeypatch.context() as patcher:
            patcher.setattr(players, "tenant_transaction_scope", stale_scope)
            response = await client.post(
                "/players/status-apply",
                json=_body([player_id], "other", "status-label"),
                headers=_headers(),
            )
    assert response.status_code == 200
    assert stale_read_count == 1
    assert response.json()["applied"][0]["roster_status_key"] == "other"
    assert response.json()["applied"][0]["roster_label_key"] == "status-label"
    assert _player_state(catalog, tenant.tenant_id, player_id) == (
        "other",
        "status-label",
    )
    assert _intents(catalog, tenant.tenant_id) == []
