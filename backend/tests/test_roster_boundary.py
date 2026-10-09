"""選手の HTTP 入口と発行境界を外部要求から検証する。"""

from __future__ import annotations

import ast
import base64
import secrets
import unicodedata
from collections.abc import Iterator
from contextlib import contextmanager
from importlib.util import resolve_name
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import fastapi.dependencies.utils
import fastapi.routing
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
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import IntegrityError

from pitchlog.api.app import create_app
from pitchlog.api.routers import players, team_records
from pitchlog.authz.token_presentation import TokenPresentation
from pitchlog.repositories import tenant_context_issuance
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.roster import (
    GameTeamLinkReadToken,
    PlayerCreateToken,
    PlayerReadToken,
    PlayerUpdateToken,
    RosterReferenceUnavailable,
    TeamRecordCreateToken,
    TeamRecordDeleteToken,
    TeamRecordReadToken,
    TeamRecordUpdateToken,
)
from pitchlog.repositories.tokens import ImmutableValue, TenantOperationResult

_SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src" / "pitchlog"
_ORIGIN = "https://roster.example"
_TEAM_A = UUID("11111111-1111-4111-8111-111111111111")
_PLAYER_A = UUID("22222222-2222-4222-8222-222222222222")
_PLAYER_B = UUID("33333333-3333-4333-8333-333333333333")
_TENANT_A = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
_TENANT_B = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
__all__ = ("disposable_postgres_cluster", "provisioned_product_catalog")


class _FakeEngine:
    """発行処理に渡した資源の解放を記録する。"""

    def __init__(self) -> None:
        self.disposed = False

    def dispose(self) -> None:
        """解放を記録する。"""
        self.disposed = True


class _PlayerStore:
    """テナントごとの結果を返す境界テスト用の実行器。"""

    def __init__(self) -> None:
        self.rows: dict[tuple[UUID, UUID], tuple[Any, ...]] = {
            (_TENANT_A, _PLAYER_A): (
                _PLAYER_A,
                _TEAM_A,
                "甲",
                None,
                None,
                None,
                "active",
                None,
                None,
            )
        }
        self.operations: list[tuple[UUID, object]] = []

    def run(self, tenant_id: UUID, operation: object) -> TenantOperationResult:
        """文脈で指定されたテナントの行だけを返す。"""
        self.operations.append((tenant_id, operation))
        if isinstance(operation, PlayerReadToken):
            rows = [
                row
                for (owner, player_id), row in self.rows.items()
                if owner == tenant_id
                and (operation.record_id is None or player_id == operation.record_id)
                and (
                    operation.team_record_id is None
                    or row[1] == operation.team_record_id
                )
                and (
                    operation.roster_status_key is None
                    or row[6] == operation.roster_status_key
                )
                and (
                    operation.uniform_number is None
                    or row[5] == operation.uniform_number
                )
                and (operation.exclude_id is None or player_id != operation.exclude_id)
                and (operation.include_hidden or row[8] is None)
            ]
            rows.sort(key=lambda row: (row[1], row[0]))
            if (
                operation.cursor_team_record_id is not None
                and operation.cursor_id is not None
            ):
                position = (operation.cursor_team_record_id, operation.cursor_id)
                rows = [row for row in rows if (row[1], row[0]) > position]
            return TenantOperationResult(tuple(rows[: operation.limit + 1]))
        if isinstance(operation, PlayerUpdateToken):
            key = (tenant_id, operation.id)
            row = self.rows.get(key)
            if row is None:
                return TenantOperationResult(((0,),))
            values = list(row)
            fields = {
                "name": 2,
                "throws": 3,
                "bats": 4,
                "uniform_number": 5,
                "roster_status_key": 6,
                "roster_label_key": 7,
            }
            for name, value in operation.changes:
                values[fields[name]] = value
            self.rows[key] = tuple(values)
            return TenantOperationResult(((1,),))
        raise AssertionError("未登録の操作")

    def create(self, context: TenantContext, operation: PlayerCreateToken) -> None:
        """他テナントのチーム参照を拒否して行を追加する。"""
        if context.tenant_id != _TENANT_A or operation.team_record_id != _TEAM_A:
            raise RosterReferenceUnavailable
        self.operations.append((context.tenant_id, operation))
        self.rows[(context.tenant_id, operation.id)] = (
            operation.id,
            operation.team_record_id,
            operation.name,
            operation.throws,
            operation.bats,
            operation.uniform_number,
            operation.roster_status_key,
            operation.roster_label_key,
            None,
        )


def _client_app(monkeypatch: pytest.MonkeyPatch, store: _PlayerStore) -> FastAPI:
    """公開アプリを作り、外部資源だけをテスト用に置き換える。"""

    async def inline_call(function: Any, *args: Any, **kwargs: Any) -> Any:
        """Sandbox で停止する worker thread 経路を迂回する。"""
        return function(*args, **kwargs)

    monkeypatch.setattr(fastapi.dependencies.utils, "run_in_threadpool", inline_call)
    monkeypatch.setattr(fastapi.routing, "run_in_threadpool", inline_call)
    monkeypatch.setenv(
        "PITCHLOG_TOKEN_SIGNING_KEY_B64",
        base64.b64encode(b"r" * 32).decode("ascii"),
    )
    monkeypatch.setenv("PITCHLOG_ALLOWED_ORIGINS", _ORIGIN)
    app = create_app()
    monkeypatch.setattr(tenant_context_issuance, "create_database_engine", _FakeEngine)
    monkeypatch.setattr(
        tenant_context_issuance,
        "verify_tenant_id",
        lambda value, presentation, engine: {
            "token-a": _TENANT_A,
            "token-b": _TENANT_B,
        }.get(value),
    )

    @contextmanager
    def scope(context: TenantContext) -> Iterator[object]:
        class Handle:
            def run(self, operation: object) -> TenantOperationResult:
                return store.run(context.tenant_id, operation)

        yield Handle()

    monkeypatch.setattr(players, "tenant_transaction_scope", scope)
    monkeypatch.setattr(players, "create_roster_player", store.create)
    return app


def _headers() -> dict[str, str]:
    return {"X-Pitchlog-Request": "1", "Origin": _ORIGIN}


def _body() -> dict[str, str]:
    return {"team_record_id": str(_TEAM_A), "name": "乙", "roster_status_key": "active"}


class _TeamStore:
    """対戦相手の入口を外から検査するための記録器。"""

    def __init__(self) -> None:
        self.rows: dict[tuple[UUID, UUID], tuple[object, ...]] = {
            (_TENANT_A, _TEAM_A): (_TEAM_A, "opponent", "東京", None),
        }
        self.games: set[tuple[UUID, UUID]] = set()
        self.players: set[tuple[UUID, UUID]] = set()

    def run(self, tenant_id: UUID, operation: object) -> TenantOperationResult:
        """登録 token の結果をテナントごとに返す。"""
        if isinstance(operation, TeamRecordReadToken):
            rows = [
                row
                for (owner, record_id), row in self.rows.items()
                if owner == tenant_id
                and (operation.record_id is None or record_id == operation.record_id)
                and (operation.cursor_id is None or record_id > operation.cursor_id)
                and (operation.exclude_id is None or record_id != operation.exclude_id)
                and (operation.include_hidden or row[3] is None)
                and (
                    operation.similar_name is None
                    or unicodedata.normalize("NFKC", str(row[2])).strip().lower()
                    == unicodedata.normalize("NFKC", operation.similar_name)
                    .strip()
                    .lower()
                )
            ]
            return TenantOperationResult(
                cast(
                    tuple[tuple[ImmutableValue, ...], ...],
                    tuple(sorted(rows)[: operation.limit + 1]),
                )
            )
        if isinstance(operation, TeamRecordCreateToken):
            self.rows[(tenant_id, operation.id)] = (
                operation.id,
                "opponent",
                operation.name,
                None,
            )
            return TenantOperationResult(((1,),))
        if isinstance(operation, (TeamRecordUpdateToken, TeamRecordDeleteToken)):
            key = (tenant_id, operation.id)
            row = self.rows.get(key)
            if row is None or row[3] is not None:
                return TenantOperationResult(((0,),))
            self.rows[key] = (
                row[0],
                row[1],
                operation.name
                if isinstance(operation, TeamRecordUpdateToken)
                else row[2],
                operation.hidden_at
                if isinstance(operation, TeamRecordDeleteToken)
                else None,
            )
            return TenantOperationResult(((1,),))
        if isinstance(operation, GameTeamLinkReadToken):
            return TenantOperationResult(
                ((uuid4(),),)
                if (tenant_id, operation.team_record_id) in self.games
                else ()
            )
        if isinstance(operation, PlayerReadToken):
            return TenantOperationResult(
                ((uuid4(),),)
                if (tenant_id, operation.team_record_id) in self.players
                else ()
            )
        raise AssertionError("未登録の操作")


def _team_client_app(monkeypatch: pytest.MonkeyPatch, store: _TeamStore) -> FastAPI:
    """公開アプリに対戦相手の記録器を接続する。"""
    app = _client_app(monkeypatch, _PlayerStore())

    @contextmanager
    def scope(context: TenantContext) -> Iterator[object]:
        class Handle:
            def run(self, operation: object) -> TenantOperationResult:
                return store.run(context.tenant_id, operation)

        yield Handle()

    monkeypatch.setattr(team_records, "tenant_transaction_scope", scope)
    return app


@pytest.mark.anyio
async def test_team_record_http_routes_warn_and_guard_deletion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """外部要求で警告と試合・選手別の削除拒否を確認する。"""
    store = _TeamStore()
    app = _team_client_app(monkeypatch, store)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        client.cookies.set("__Host-pitchlog_token", "token-a")
        created = await client.post(
            "/team-records", json={"name": "東京"}, headers=_headers()
        )
        assert created.status_code == 201
        created_id = UUID(created.json()["id"])
        assert created.json()["similar_names"] == ["東京"]
        assert "tenant_id" not in created.json()
        listed = await client.get("/team-records", params={"limit": 1})
        assert listed.status_code == 200
        assert len(listed.json()["items"]) == 1
        assert listed.json()["next_cursor"] is not None
        renamed = await client.patch(
            f"/team-records/{created_id}", json={"name": "大阪"}, headers=_headers()
        )
        assert renamed.status_code == 200
        assert renamed.json()["name"] == "大阪"
        store.games.add((_TENANT_A, created_id))
        blocked_game = await client.delete(
            f"/team-records/{created_id}", headers=_headers()
        )
        assert blocked_game.status_code == 409
        assert "試合" in blocked_game.json()["error"]["message"]
        store.games.clear()
        store.players.add((_TENANT_A, created_id))
        blocked_player = await client.delete(
            f"/team-records/{created_id}", headers=_headers()
        )
        assert blocked_player.status_code == 409
        assert "選手" in blocked_player.json()["error"]["message"]
        store.players.clear()
        deleted = await client.delete(f"/team-records/{created_id}", headers=_headers())
        assert deleted.status_code == 200
        assert deleted.json()["hidden_at"] is not None
        missing = await client.delete(f"/team-records/{created_id}", headers=_headers())
        assert missing.status_code == 404
        client.cookies.set("__Host-pitchlog_token", "token-b")
        foreign = await client.delete(f"/team-records/{_TEAM_A}", headers=_headers())
        absent = await client.delete(f"/team-records/{uuid4()}", headers=_headers())
        assert foreign.status_code == absent.status_code == 404
        assert foreign.content == absent.content


@pytest.mark.anyio
async def test_team_record_http_routes_apply_request_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cookie と状態変更要求の門を外部要求で確認する。"""
    app = _team_client_app(monkeypatch, _TeamStore())
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        requests = (
            ("POST", "/team-records", {"name": "東京"}),
            ("GET", "/team-records?limit=1", None),
            ("PATCH", f"/team-records/{_TEAM_A}", {"name": "変更"}),
            ("DELETE", f"/team-records/{_TEAM_A}", None),
        )
        for method, path, body in requests:
            missing = await client.request(method, path, json=body, headers=_headers())
            assert missing.status_code == 401
            client.cookies.set("__Host-pitchlog_token", "token-a")
            if method != "GET":
                no_header = await client.request(method, path, json=body)
                assert no_header.status_code == 403
            client.cookies.clear()


@pytest.mark.requires_db
@pytest.mark.anyio
async def test_real_player_http_boundary_enforces_tenant_and_request_gates(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """実 DB と公開 HTTP 入口で二つのテナントの閲覧・変更境界を検証する。"""
    catalog = cast(
        ProvisionedProductCatalog,
        request.getfixturevalue("provisioned_product_catalog"),
    )
    _seed_settings(catalog)
    app_dsn = _app_dsn(catalog)
    tenant_a = _seed_identity(catalog, app_dsn)
    tenant_b = _seed_identity(catalog, app_dsn)
    token_a = _login(tenant_a)
    token_b = _login(tenant_b)
    assert isinstance(token_a, UUID)
    assert isinstance(token_b, UUID)

    team_a, team_b = uuid4(), uuid4()
    player_a, player_b = uuid4(), uuid4()
    with catalog.applicator.cursor() as cursor:
        for identity, team_id, player_id, name in (
            (tenant_a, team_a, player_a, "甲"),
            (tenant_b, team_b, player_b, "丙"),
        ):
            cursor.execute(
                "INSERT INTO public.team_records (tenant_id, id, kind, name) "
                "VALUES (%s, %s, %s, %s)",
                (identity.tenant_id, team_id, "self", f"{name}チーム"),
            )
            cursor.execute(
                "INSERT INTO public.players "
                "(tenant_id, id, team_record_id, name, uniform_number, "
                "roster_status_key) VALUES (%s, %s, %s, %s, %s, %s)",
                (identity.tenant_id, player_id, team_id, name, "7", "active"),
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
    presented_a = signer.encode(token_a)
    presented_b = signer.encode(token_b)
    body_a = {
        "team_record_id": str(team_a),
        "name": "乙",
        "roster_status_key": "active",
        "uniform_number": "7",
    }
    unknown_id = uuid4()
    expected_404 = {"error": {"message": "対象が見つかりません"}}

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        client.cookies.set("__Host-pitchlog_token", presented_a)
        own = await client.get(f"/players/{player_a}")
        assert own.status_code == 200
        assert own.json()["id"] == str(player_a)
        assert "tenant_id" not in own.json()

        own_list = await client.get("/players", params={"limit": 1})
        assert own_list.status_code == 200
        assert [row["id"] for row in own_list.json()["items"]] == [str(player_a)]
        assert own_list.json()["next_cursor"] is None

        with catalog.applicator.cursor() as cursor:
            cursor.execute(
                "INSERT INTO public.players "
                "(tenant_id, id, team_record_id, name, uniform_number, "
                "roster_status_key) VALUES (%s, %s, %s, %s, %s, %s)",
                (tenant_a.tenant_id, uuid4(), team_a, "OB", "7", "ob"),
            )
            cursor.execute(
                "INSERT INTO public.players "
                "(tenant_id, id, team_record_id, name, uniform_number, "
                "roster_status_key, hidden_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, pg_catalog.clock_timestamp())",
                (tenant_a.tenant_id, uuid4(), team_a, "非表示", "7", "active"),
            )
        catalog.applicator.commit()

        created = await client.post("/players", json=body_a, headers=_headers())
        assert created.status_code == 201
        created_id = UUID(created.json()["id"])
        assert created.json()["name"] == "乙"
        assert [row["id"] for row in created.json()["same_number_players"]] == [
            str(player_a)
        ]
        assert "tenant_id" not in created.json()
        assert (await client.get(f"/players/{created_id}")).status_code == 200

        updated = await client.patch(
            f"/players/{player_a}", json={"name": "甲改"}, headers=_headers()
        )
        assert updated.status_code == 200
        assert updated.json()["name"] == "甲改"
        assert "tenant_id" not in updated.json()
        for field, value in (
            ("roster_status_key", "ob"),
            ("roster_label_key", None),
        ):
            blocked = await client.patch(
                f"/players/{player_a}",
                json={"name": "拒否対象", field: value},
                headers=_headers(),
            )
            assert blocked.status_code == 422

        client.cookies.set("__Host-pitchlog_token", presented_b)
        other = await client.get(f"/players/{player_b}")
        assert other.status_code == 200
        assert other.json()["id"] == str(player_b)
        foreign_list = await client.get("/players", params={"limit": 20})
        assert foreign_list.status_code == 200
        assert [row["id"] for row in foreign_list.json()["items"]] == [str(player_b)]
        assert "tenant_id" not in foreign_list.text

        missing_read = await client.get(f"/players/{unknown_id}")
        foreign_read = await client.get(f"/players/{player_a}")
        assert missing_read.status_code == foreign_read.status_code == 404
        assert missing_read.json() == foreign_read.json() == expected_404

        missing_update = await client.patch(
            f"/players/{unknown_id}", json={"name": "変更"}, headers=_headers()
        )
        foreign_update = await client.patch(
            f"/players/{player_a}", json={"name": "変更"}, headers=_headers()
        )
        assert missing_update.status_code == foreign_update.status_code == 404
        assert missing_update.json() == foreign_update.json() == expected_404

        foreign_create = await client.post("/players", json=body_a, headers=_headers())
        missing_create = await client.post(
            "/players",
            json=body_a | {"team_record_id": str(uuid4())},
            headers=_headers(),
        )
        assert foreign_create.status_code == missing_create.status_code == 404
        assert foreign_create.json() == missing_create.json() == expected_404

        client.cookies.set("__Host-pitchlog_token", presented_a)
        unchanged = await client.get(f"/players/{player_a}")
        assert unchanged.status_code == 200
        assert unchanged.json()["name"] == "甲改"

        cases = (
            ("POST", "/players", body_a),
            ("GET", "/players?limit=20", None),
            ("GET", f"/players/{player_a}", None),
            ("PATCH", f"/players/{player_a}", {"name": "変更"}),
        )
        for method, path, body in cases:
            client.cookies.clear()
            missing_cookie = await client.request(
                method, path, json=body, headers=_headers()
            )
            assert missing_cookie.status_code == 401
            assert missing_cookie.json() == {
                "error": {"message": "認証情報がありません"}
            }

            client.cookies.set("__Host-pitchlog_token", presented_b + "x")
            tampered = await client.request(method, path, json=body, headers=_headers())
            assert tampered.status_code == 401
            assert tampered.json() == missing_cookie.json()

        client.cookies.set("__Host-pitchlog_token", presented_b)
        for method, path, body in cases:
            if method == "GET":
                continue
            no_header = await client.request(
                method, path, json=body, headers={"Origin": _ORIGIN}
            )
            no_origin = await client.request(
                method,
                path,
                json=body,
                headers={"X-Pitchlog-Request": "1"},
            )
            assert no_header.status_code == no_origin.status_code == 403
            assert (
                no_header.json()
                == no_origin.json()
                == {"error": {"message": "要求を確認できません"}}
            )

        with catalog.applicator.cursor() as cursor:
            cursor.execute(
                "UPDATE public.tenant_tokens "
                "SET last_used_at = "
                "pg_catalog.clock_timestamp() - interval '2 seconds', "
                "expires_at = pg_catalog.clock_timestamp() - interval '1 second' "
                "WHERE id = %s",
                (token_b,),
            )
        catalog.applicator.commit()
        for method, path, body in cases:
            expired = await client.request(method, path, json=body, headers=_headers())
            assert expired.status_code == 401
            assert expired.json() == {"error": {"message": "認証情報がありません"}}


@pytest.mark.requires_db
@pytest.mark.anyio
async def test_real_team_record_http_boundary_and_delete_guards(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """実スキーマ上の作成・一覧・更新・論理削除と越境拒否を確認する。"""
    catalog = cast(
        ProvisionedProductCatalog,
        request.getfixturevalue("provisioned_product_catalog"),
    )
    _seed_settings(catalog)
    app_dsn = _app_dsn(catalog)
    tenant_a = _seed_identity(catalog, app_dsn)
    tenant_b = _seed_identity(catalog, app_dsn)
    token_a = _login(tenant_a)
    token_b = _login(tenant_b)
    assert isinstance(token_a, UUID)
    assert isinstance(token_b, UUID)
    self_a, self_b = uuid4(), uuid4()
    team_a, team_b, team_player, team_game = uuid4(), uuid4(), uuid4(), uuid4()
    team_hidden_player, team_trashed_game = uuid4(), uuid4()
    team_spaced, team_wide, team_wide_b = uuid4(), uuid4(), uuid4()
    with catalog.applicator.cursor() as cursor:
        cursor.execute(
            "INSERT INTO public.system_vocabularies(key, category, display_name) "
            "VALUES ('roster-game-test', 'game_type', '試合') ON CONFLICT DO NOTHING"
        )
        for tenant_id, record_id, kind, name in (
            (tenant_a.tenant_id, self_a, "self", "自チーム A"),
            (tenant_b.tenant_id, self_b, "self", "自チーム B"),
            (tenant_a.tenant_id, team_a, "opponent", "東京"),
            (tenant_b.tenant_id, team_b, "opponent", "東京"),
            (tenant_a.tenant_id, team_player, "opponent", "選手あり"),
            (tenant_a.tenant_id, team_game, "opponent", "試合あり"),
            (tenant_a.tenant_id, team_hidden_player, "opponent", "非表示選手あり"),
            (tenant_a.tenant_id, team_trashed_game, "opponent", "削除済み試合あり"),
            (tenant_a.tenant_id, team_spaced, "opponent", " 東京 "),
            (tenant_a.tenant_id, team_wide, "opponent", " Ｔｏｋｙｏ "),
            (tenant_b.tenant_id, team_wide_b, "opponent", " Ｔｏｋｙｏ "),
        ):
            cursor.execute(
                "INSERT INTO public.team_records(tenant_id, id, kind, name) "
                "VALUES (%s, %s, %s, %s)",
                (tenant_id, record_id, kind, name),
            )
        cursor.execute(
            "INSERT INTO public.tenant_vocabularies "
            "(tenant_id, key, category, display_name) "
            "VALUES (%s, 'roster-game-test', 'tournament', '大会')",
            (tenant_a.tenant_id,),
        )
        cursor.execute(
            "INSERT INTO public.players "
            "(tenant_id, id, team_record_id, name, roster_status_key) "
            "VALUES (%s, %s, %s, '紐づく選手', 'active')",
            (tenant_a.tenant_id, uuid4(), team_player),
        )
        cursor.execute(
            "INSERT INTO public.players "
            "(tenant_id, id, team_record_id, name, roster_status_key, hidden_at) "
            "VALUES (%s, %s, %s, '非表示の選手', 'active', "
            "pg_catalog.clock_timestamp())",
            (tenant_a.tenant_id, uuid4(), team_hidden_player),
        )
        cursor.execute(
            "INSERT INTO public.games "
            "(tenant_id, id, scheduled_at, game_type_key, tournament_key, "
            "away_team_record_id, home_team_record_id, applied_rules) "
            "VALUES (%s, %s, pg_catalog.clock_timestamp(), 'roster-game-test', "
            "'roster-game-test', %s, %s, '{}'::jsonb)",
            (tenant_a.tenant_id, uuid4(), team_game, self_a),
        )
        cursor.execute(
            "INSERT INTO public.games "
            "(tenant_id, id, scheduled_at, game_type_key, tournament_key, "
            "away_team_record_id, home_team_record_id, applied_rules, "
            "status, trashed_at) "
            "VALUES (%s, %s, pg_catalog.clock_timestamp(), 'roster-game-test', "
            "'roster-game-test', %s, %s, '{}'::jsonb, 'trashed', "
            "pg_catalog.clock_timestamp())",
            (tenant_a.tenant_id, uuid4(), team_trashed_game, self_a),
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
    presented_a = signer.encode(token_a)
    presented_b = signer.encode(token_b)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        client.cookies.set("__Host-pitchlog_token", presented_a)
        created = await client.post(
            "/team-records", json={"name": "東京"}, headers=_headers()
        )
        assert created.status_code == 201
        assert set(created.json()["similar_names"]) == {"東京", " 東京 "}
        wide_created = await client.post(
            "/team-records", json={"name": "Tokyo"}, headers=_headers()
        )
        assert wide_created.status_code == 201
        assert wide_created.json()["similar_names"] == [" Ｔｏｋｙｏ "]
        assert "tenant_id" not in created.text
        created_id = UUID(created.json()["id"])
        listed = await client.get("/team-records", params={"limit": 1})
        assert listed.status_code == 200
        assert len(listed.json()["items"]) == 1
        assert listed.json()["next_cursor"] is not None
        updated = await client.patch(
            f"/team-records/{created_id}", json={"name": "大阪"}, headers=_headers()
        )
        assert updated.status_code == 200
        assert updated.json()["name"] == "大阪"
        game_blocked = await client.delete(
            f"/team-records/{team_game}", headers=_headers()
        )
        player_blocked = await client.delete(
            f"/team-records/{team_player}", headers=_headers()
        )
        hidden_player_blocked = await client.delete(
            f"/team-records/{team_hidden_player}", headers=_headers()
        )
        trashed_game_blocked = await client.delete(
            f"/team-records/{team_trashed_game}", headers=_headers()
        )
        assert game_blocked.status_code == player_blocked.status_code == 409
        assert hidden_player_blocked.status_code == 409
        assert trashed_game_blocked.status_code == 409
        assert "試合" in game_blocked.json()["error"]["message"]
        assert "選手" in player_blocked.json()["error"]["message"]
        assert "選手" in hidden_player_blocked.json()["error"]["message"]
        assert "試合" in trashed_game_blocked.json()["error"]["message"]
        deleted = await client.delete(f"/team-records/{created_id}", headers=_headers())
        assert deleted.status_code == 200
        assert deleted.json()["hidden_at"] is not None
        assert (
            await client.delete(f"/team-records/{created_id}", headers=_headers())
        ).status_code == 404
        client.cookies.set("__Host-pitchlog_token", presented_b)
        own_list = await client.get("/team-records", params={"limit": 20})
        assert own_list.status_code == 200
        assert {row["id"] for row in own_list.json()["items"]} == {
            str(team_b),
            str(team_wide_b),
        }
        missing_id = uuid4()
        foreign_update = await client.patch(
            f"/team-records/{team_a}", json={"name": "変更"}, headers=_headers()
        )
        absent_update = await client.patch(
            f"/team-records/{missing_id}", json={"name": "変更"}, headers=_headers()
        )
        assert foreign_update.status_code == absent_update.status_code == 404
        assert foreign_update.content == absent_update.content
        foreign_delete = await client.delete(
            f"/team-records/{team_a}", headers=_headers()
        )
        absent_delete = await client.delete(
            f"/team-records/{missing_id}", headers=_headers()
        )
        assert foreign_delete.status_code == absent_delete.status_code == 404
        assert foreign_delete.content == absent_delete.content
        client.cookies.clear()
        for method, path, body in (
            ("POST", "/team-records", {"name": "新規"}),
            ("GET", "/team-records?limit=1", None),
            ("PATCH", f"/team-records/{team_b}", {"name": "変更"}),
            ("DELETE", f"/team-records/{team_b}", None),
        ):
            response = await client.request(method, path, json=body, headers=_headers())
            assert response.status_code == 401
        client.cookies.set("__Host-pitchlog_token", presented_b)
        for method, path, body in (
            ("POST", "/team-records", {"name": "新規"}),
            ("PATCH", f"/team-records/{team_b}", {"name": "変更"}),
            ("DELETE", f"/team-records/{team_b}", None),
        ):
            missing_header = await client.request(method, path, json=body)
            missing_origin = await client.request(
                method, path, json=body, headers={"X-Pitchlog-Request": "1"}
            )
            assert missing_header.status_code == missing_origin.status_code == 403


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("POST", "/players", _body()),
        ("GET", "/players?limit=20", None),
        ("GET", f"/players/{_PLAYER_A}", None),
        ("PATCH", f"/players/{_PLAYER_A}", {"name": "乙"}),
    ],
    ids=["create", "list", "read", "update"],
)
async def test_player_entry_accepts_verified_tenant_and_rejects_missing_gate(
    method: str,
    path: str,
    body: dict[str, str] | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """4 入口を直接叩き、提示値・Cookie・CSRF の境界を確認する。"""
    store = _PlayerStore()
    app = _client_app(monkeypatch, store)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.cookies.set("__Host-pitchlog_token", "token-a")
        response = await client.request(
            method,
            path,
            json=body,
            headers=_headers(),
        )
        assert response.status_code == (201 if method == "POST" else 200)
        if method == "GET" and path.startswith("/players?"):
            assert len(response.json()["items"]) == 1
            assert response.json()["next_cursor"] is None
        else:
            assert response.json()["name"] in {"甲", "乙"}
            assert "tenant_id" not in response.json()

        client.cookies.clear()
        missing = await client.request(method, path, json=body, headers=_headers())
        assert missing.status_code == 401
        assert missing.json() == {"error": {"message": "認証情報がありません"}}

        if method in {"POST", "PATCH"}:
            client.cookies.set("__Host-pitchlog_token", "token-a")
            no_csrf = await client.request(
                method,
                path,
                json=body,
            )
            assert no_csrf.status_code == 403
            assert no_csrf.json() == {"error": {"message": "要求を確認できません"}}


@pytest.mark.anyio
@pytest.mark.parametrize("field", ("roster_status_key", "roster_label_key"))
async def test_player_patch_rejects_status_fields_before_storage(
    field: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """在籍区分と表示ラベルの変更は公開 PATCH から実行しない。"""
    store = _PlayerStore()
    app = _client_app(monkeypatch, store)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        client.cookies.set("__Host-pitchlog_token", "token-a")
        response = await client.patch(
            f"/players/{_PLAYER_A}",
            json={"name": "変更", field: "other"},
            headers=_headers(),
        )
    assert response.status_code == 422
    assert store.rows[(_TENANT_A, _PLAYER_A)][2] == "甲"
    assert not any(
        isinstance(token, PlayerUpdateToken) for _, token in store.operations
    )


@pytest.mark.anyio
async def test_player_create_reports_only_active_same_tenant_number(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """登録を成功させ、同番号の現役選手だけを警告に載せる。"""
    store = _PlayerStore()
    existing = list(store.rows[(_TENANT_A, _PLAYER_A)])
    existing[5] = "7"
    store.rows[(_TENANT_A, _PLAYER_A)] = tuple(existing)
    foreign = existing.copy()
    foreign[0] = _PLAYER_B
    store.rows[(_TENANT_B, _PLAYER_B)] = tuple(foreign)
    former_id = uuid4()
    store.rows[(_TENANT_A, former_id)] = (
        former_id,
        _TEAM_A,
        "OB",
        None,
        None,
        "7",
        "ob",
        None,
        None,
    )
    app = _client_app(monkeypatch, store)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        client.cookies.set("__Host-pitchlog_token", "token-a")
        response = await client.post(
            "/players",
            json=_body() | {"uniform_number": "7"},
            headers=_headers(),
        )
        without_number = await client.post("/players", json=_body(), headers=_headers())
    assert response.status_code == without_number.status_code == 201
    assert [row["id"] for row in response.json()["same_number_players"]] == [
        str(_PLAYER_A)
    ]
    assert without_number.json()["same_number_players"] == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("method", "path", "body", "expected"),
    [
        ("POST", "/players", _body(), 404),
        ("GET", "/players?limit=20", None, 200),
        ("GET", f"/players/{_PLAYER_A}", None, 404),
        ("PATCH", f"/players/{_PLAYER_A}", {"name": "乙"}, 404),
    ],
    ids=["create", "list", "read", "update"],
)
async def test_player_entry_does_not_expose_other_tenant_rows(
    method: str,
    path: str,
    body: dict[str, str] | None,
    expected: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """他テナントの提示値から既存の選手やチームに到達しない。"""
    app = _client_app(monkeypatch, _PlayerStore())
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        client.cookies.set("__Host-pitchlog_token", "token-b")
        response = await client.request(
            method,
            path,
            json=body,
            headers=_headers(),
        )
    assert response.status_code == expected
    if method == "GET" and path.startswith("/players?"):
        assert response.json()["items"] == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("method", "path", "expected"),
    [
        ("POST", "/players/status-preview", 404),
        ("POST", "/players/status-apply", 404),
        ("DELETE", f"/players/{_PLAYER_A}", 405),
    ],
)
async def test_future_entries_remain_closed(
    method: str, path: str, expected: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """後続 PR に送った入口は公開しない。"""
    app = _client_app(monkeypatch, _PlayerStore())
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.request(method, path, headers=_headers())
    assert response.status_code == expected


@pytest.mark.anyio
@pytest.mark.parametrize("body", [{"name": ""}, {}])
async def test_player_update_rejects_invalid_body(
    body: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """空名や変更なしを 422 で拒否する。"""
    app = _client_app(monkeypatch, _PlayerStore())
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        client.cookies.set("__Host-pitchlog_token", "token-a")
        response = await client.patch(
            f"/players/{_PLAYER_A}",
            json=body,
            headers=_headers(),
        )
    assert response.status_code == 422


@pytest.mark.anyio
async def test_player_create_rejects_empty_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """選手名の空文字を token より手前で 422 にする。"""
    app = _client_app(monkeypatch, _PlayerStore())
    body = _body() | {"name": ""}
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        client.cookies.set("__Host-pitchlog_token", "token-a")
        response = await client.post(
            "/players",
            json=body,
            headers=_headers(),
        )
    assert response.status_code == 422


@pytest.mark.anyio
async def test_non_reference_integrity_failure_uses_fixed_error_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """参照先以外の整合性違反を 404 とせず固定の内部エラーにする。"""
    app = _client_app(monkeypatch, _PlayerStore())

    def fail_create(_context: TenantContext, _operation: PlayerCreateToken) -> None:
        raise IntegrityError("INSERT", {}, Exception("pk_players"))

    monkeypatch.setattr(players, "create_roster_player", fail_create)
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        client.cookies.set("__Host-pitchlog_token", "token-a")
        response = await client.post("/players", json=_body(), headers=_headers())
    assert response.status_code == 500
    assert response.json() == {
        "error": {"message": "サーバー内部でエラーが発生しました"}
    }
    assert "pk_players" not in response.text


@pytest.mark.anyio
async def test_unverified_presentation_uses_fixed_401(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """照合できない提示値は資源の有無に依らず同じ応答にする。"""
    app = _client_app(monkeypatch, _PlayerStore())
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        client.cookies.set("__Host-pitchlog_token", "unknown-token")
        listed = await client.get("/players?limit=20")
        read = await client.get(f"/players/{_PLAYER_A}")
    expected = {"error": {"message": "認証情報がありません"}}
    assert listed.status_code == read.status_code == 401
    assert listed.json() == read.json() == expected


@pytest.mark.anyio
async def test_player_list_uses_cursor_and_limit_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """一覧を上限付きで取得し、不透明な位置から次ページへ進む。"""
    store = _PlayerStore()
    store.rows[(_TENANT_A, _PLAYER_B)] = (
        _PLAYER_B,
        _TEAM_A,
        "乙",
        None,
        None,
        None,
        "active",
        None,
        None,
    )
    app = _client_app(monkeypatch, store)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        client.cookies.set("__Host-pitchlog_token", "token-a")
        first = await client.get("/players?limit=1")
        assert first.status_code == 200
        assert [item["id"] for item in first.json()["items"]] == [str(_PLAYER_A)]
        cursor = first.json()["next_cursor"]
        assert cursor and str(_PLAYER_A) not in cursor
        second = await client.get("/players", params={"limit": 1, "cursor": cursor})
        assert second.status_code == 200
        assert [item["id"] for item in second.json()["items"]] == [str(_PLAYER_B)]
        assert second.json()["next_cursor"] is None
        assert (await client.get("/players?limit=201")).status_code == 422
        assert (await client.get("/players?limit=1&cursor=bad!")).status_code == 422


def test_issuer_rejects_raw_identifiers(monkeypatch: pytest.MonkeyPatch) -> None:
    """発行関数は生の ID やその文字列化を受け付けない。"""
    monkeypatch.setenv(
        "PITCHLOG_TOKEN_SIGNING_KEY_B64",
        base64.b64encode(b"r" * 32).decode("ascii"),
    )
    presentation: TokenPresentation = create_app().state.token_presentation
    engine = _FakeEngine()
    monkeypatch.setattr(
        tenant_context_issuance, "create_database_engine", lambda: engine
    )
    assert (
        tenant_context_issuance.issue_tenant_context_from_presented_token(
            cast(str, _TENANT_A), presentation
        )
        is None
    )
    assert not engine.disposed
    assert (
        tenant_context_issuance.issue_tenant_context_from_presented_token(
            str(_TENANT_A), presentation
        )
        is None
    )
    assert engine.disposed


_ISSUER_TARGET = (
    "pitchlog.repositories.tenant_context_issuance."
    "issue_tenant_context_from_presented_token"
)
_VERIFIER_TARGET = "pitchlog.authz.verified_tenant.verify_tenant_id"


def _import_bindings(nodes: Iterator[ast.AST], module: str) -> dict[str, str]:
    """Import の別名を完全修飾名へ解決する。"""
    bindings: dict[str, str] = {}
    for node in nodes:
        if isinstance(node, ast.Import):
            for item in node.names:
                if item.asname:
                    bindings[item.asname] = item.name
                else:
                    bindings[item.name.split(".")[0]] = item.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom):
            imported_module = node.module or ""
            if node.level:
                imported_module = resolve_name(
                    "." * node.level + imported_module, module
                )
            for item in node.names:
                bindings[item.asname or item.name] = f"{imported_module}.{item.name}"
    return bindings


def _called_symbol(node: ast.expr, bindings: dict[str, str]) -> str | None:
    """呼び出し対象を import の別名を含めて解決する。"""
    if isinstance(node, ast.Name):
        return bindings.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        parent = _called_symbol(node.value, bindings)
        return None if parent is None else f"{parent}.{node.attr}"
    return None


def _callers(tree: ast.Module, module: str) -> dict[str, set[str]]:
    """発行と照合の呼び出し元を全関数から列挙する。"""
    targets = {_ISSUER_TARGET, _VERIFIER_TARGET}
    callers: dict[str, set[str]] = {name: set() for name in targets}
    module_bindings = _import_bindings(iter(tree.body), module)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        bindings = module_bindings | _import_bindings(ast.walk(node), module)
        for call in ast.walk(node):
            if not isinstance(call, ast.Call):
                continue
            target = _called_symbol(call.func, bindings)
            if target in callers:
                callers[target].add(f"{module}.{node.name}")
    return callers


def test_issuance_and_verification_callers_are_exact_sets() -> None:
    """発行入口と照合入口の製品コード内呼び出し元を固定する。"""
    targets = {
        _ISSUER_TARGET: {"pitchlog.api.tenant_access.require_tenant_access"},
        _VERIFIER_TARGET: {_ISSUER_TARGET},
    }
    callers: dict[str, set[str]] = {name: set() for name in targets}
    for path in _SOURCE_ROOT.rglob("*.py"):
        parts = path.relative_to(_SOURCE_ROOT.parent).with_suffix("").parts
        module = ".".join(parts[:-1] if parts[-1] == "__init__" else parts)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for target, found in _callers(tree, module).items():
            callers[target].update(found)
    assert callers == targets


def test_issuance_caller_scan_resolves_import_aliases() -> None:
    """別名 import の呼び出しも exact-set に現れることを確かめる。"""
    source = """\
from pitchlog.repositories.tenant_context_issuance import (
    issue_tenant_context_from_presented_token as mint,
)

def rogue():
    mint('opaque', object())
"""
    callers = _callers(ast.parse(source), "pitchlog.api.rogue")
    assert callers[_ISSUER_TARGET] == {"pitchlog.api.rogue.rogue"}
