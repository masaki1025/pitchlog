"""開始済み試合の再取得HTTPを、C2・DTO・非開示・固定外形で検査する。

組立器と0球readerは実物を使い、合成rowだけを既executorのmaterializationへ通す。
実DB・実Cookie・実worker経由の受入ではない(それは別の受入試験の範囲)。
"""

from __future__ import annotations

import base64
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any, get_args
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient, Response
from test_authz_tenant_context import make_tenant_context
from test_recorded_snapshot import RecordedBundle
from test_recorded_snapshot import recorded_bundle as recorded_bundle  # noqa: F401
from test_roster_boundary import (
    _TENANT_A,
    _TENANT_B,
    _client_app,
    _metadata_headers,
    _PlayerStore,
)
from test_started_snapshot import Bundle

from pitchlog.api import app as api_app
from pitchlog.api import tenant_access
from pitchlog.api.routers import games, started_games
from pitchlog.api.schemas.started_games import (
    StartedGameRead,
    StartedGameReadResponse,
    StartedPlayPrefixGameRead,
    StartedPlayRow,
    StartedRecordedGameRead,
    StartedRecordedPrefixGameRead,
)
from pitchlog.domainrt import host as domainrt_host
from pitchlog.repositories import started_read
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.tokens import TenantOperationResult
from pitchlog.repositories.transaction import _TenantTransaction
from pitchlog.sync.d4_reference import encode_d4_reference

_ACK = "x-pitchlog-tenant-match"
_CHALLENGE = "x-pitchlog-tenant-challenge"
_FIXED_REQUEST_ERROR = {"error": {"message": "リクエストを処理できません"}}


def _route() -> APIRoute:
    """登録済みの開始済み再取得routeを1件だけ取り出す。"""
    routes = [
        route
        for router in api_app.ROUTERS
        for route in router.routes
        if isinstance(route, APIRoute) and route.operation_id == "started_game_detail"
    ]
    assert len(routes) == 1
    return routes[0]


def _bundle_for(tenant: UUID, monkeypatch: pytest.MonkeyPatch) -> Bundle:
    """合成rowのtenantを認証済みtenantへ合わせ、同handleの読取だけを置き換える。"""
    value = Bundle()
    value.tenant = tenant
    value.game["tenant_id"] = tenant
    value.game.update(
        scheduled_at=value.game["started_at"],
        game_type_key="game_official",
        tournament_key="spring",
        plate_umpire="審判",
    )
    value.generation["tenant_id"] = tenant
    for lineup in value.lineups:
        lineup["tenant_id"] = tenant
    value.handle._bound_tenant_id = tenant
    monkeypatch.setattr(
        _TenantTransaction, "run", lambda handle, token: value.run(handle, token)
    )
    return value


def _app(
    monkeypatch: pytest.MonkeyPatch, bundle: Bundle | None
) -> tuple[FastAPI, list]:
    """認証・C2は実物、transaction境界だけを合成handleへ置き換えたアプリを作る。"""
    app = _client_app(monkeypatch, _PlayerStore())
    entered: list[TenantContext] = []

    @contextmanager
    def scope(context: TenantContext) -> Iterator[object]:
        entered.append(context)
        if bundle is None:
            raise AssertionError("transactionを開始してはならない")
        yield bundle.handle

    monkeypatch.setattr(started_games, "tenant_transaction_scope", scope)
    return app, entered


async def _get(
    app: FastAPI,
    game_id: UUID,
    *,
    tenant: UUID = _TENANT_A,
    cookie: str | None = "token-a",
    headers: dict[str, str] | None = None,
    path: str = "/games/{}/started",
) -> Response:
    """実HTTPでGETし、C2の正規metadataを既定で付ける。"""
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        if cookie is not None:
            client.cookies.set("__Host-pitchlog_token", cookie)
        sent = _metadata_headers(tenant) if headers is None else headers
        return await client.get(path.format(game_id), headers=sent)


def test_route_is_registered_as_a_tenant_matched_get() -> None:
    """GET 1本・固定operation_id・C2対象・response_modelが記録前後のunionである。"""
    route = _route()
    assert route.path == "/games/{game_id}/started"
    assert set(route.methods or ()) == {"GET"}
    assert isinstance(route, tenant_access.TenantMatchedRoute)
    assert "started_game_detail" in tenant_access._MATCH_OPERATIONS
    assert route.response_model == StartedGameReadResponse
    union, discriminator = get_args(route.response_model)
    assert set(get_args(union)) == {
        StartedGameRead,
        StartedRecordedGameRead,
        StartedRecordedPrefixGameRead,
        StartedPlayPrefixGameRead,
    }
    assert discriminator.discriminator == "read_kind"


def test_dto_key_set_is_exactly_the_confirmed_state() -> None:
    """応答のkey集合は確定状態とcurrent_d4だけで、記録権の値を持たない。"""
    assert set(StartedGameRead.model_fields) == {
        "read_kind",
        "id",
        "scheduled_at",
        "game_type_key",
        "tournament_key",
        "away_team_record_id",
        "home_team_record_id",
        "plate_umpire",
        "section_label",
        "week_label",
        "day_label",
        "game_number_label",
        "status",
        "started_at",
        "applied_rules",
        "lineups",
        "roster",
        "state",
        "current_d4",
    }
    assert StartedGameRead.model_config["extra"] == "forbid"
    assert StartedGameRead.model_config["frozen"] is True


@pytest.mark.anyio
async def test_success_returns_confirmed_state_with_c2_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """実の組立器・0球readerを通した200で、非開示と応答headerを確かめる。"""
    bundle = _bundle_for(_TENANT_A, monkeypatch)
    app, entered = _app(monkeypatch, bundle)
    headers = _metadata_headers(_TENANT_A)
    response = await _get(app, bundle.game_id, headers=headers)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers[_ACK] == "1"
    assert response.headers[_CHALLENGE] == headers["X-Pitchlog-Tenant-Challenge"]
    body = response.json()
    assert set(body) == set(StartedGameRead.model_fields)
    assert body["read_kind"] == "initial" and body["status"] == "in_progress"
    assert body["id"] == str(bundle.game_id)
    assert body["current_d4"] == encode_d4_reference(_TENANT_A, bundle.game_id, 1)
    state = body["state"]["stateFields"]
    assert (state["state.count.balls"], state["state.count.strikes"]) == ("0", "0")
    assert (state["state.outs"], state["state.inning"], state["state.half"]) == (
        "0",
        "1",
        "top",
    )
    assert [side["team_id"] for side in body["roster"]["teams"]] == [
        str(bundle.game["away_team_record_id"]),
        str(bundle.game["home_team_record_id"]),
    ]
    assert set(body["lineups"]) == {"away", "home"}
    first = body["lineups"]["away"]["entries"][0]
    assert set(first) == {
        "player_id",
        "batting_order",
        "fielding_position",
        "uniform_number_snapshot",
    }
    assert [c.tenant_id for c in entered] == [_TENANT_A]


@pytest.mark.anyio
async def test_success_body_never_contains_recording_right_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """保持者・資格・証明・watermark・prefix・tenantを本文のbytesに含めない。"""
    bundle = _bundle_for(_TENANT_A, monkeypatch)
    app, _ = _app(monkeypatch, bundle)
    response = await _get(app, bundle.game_id)
    assert response.status_code == 200
    text = response.text
    assert bundle.generation["holder_device"] not in text
    assert str(_TENANT_A) not in text
    lowered = text.lower()
    for word in (
        "holder_device",
        "device_id",
        "credential",
        "recording_right_proof",
        "recovery_generation",
        "watermark",
        "prefix",
        "tenant_id",
        "issuance_order",
        "granted_at",
    ):
        assert word not in lowered


async def _preparing_404_bytes(monkeypatch: pytest.MonkeyPatch) -> bytes:
    """preparing詳細が0行のときの404を、同じ実HTTP経路で得る。"""
    preparing_app = _client_app(monkeypatch, _PlayerStore())

    @contextmanager
    def empty_scope(context: TenantContext) -> Iterator[object]:
        class Handle:
            def run(self, operation: object) -> TenantOperationResult:
                return TenantOperationResult(())

        yield Handle()

    monkeypatch.setattr(games, "tenant_transaction_scope", empty_scope)
    response = await _get(preparing_app, uuid4(), path="/games/{}")
    assert response.status_code == 404
    return response.content


async def _get_with(
    monkeypatch: pytest.MonkeyPatch, change: Callable[[Bundle], None]
) -> Response:
    """新しい合成rowへchangeを適用し、開始済み再取得をGETする。"""
    bundle = _bundle_for(_TENANT_A, monkeypatch)
    change(bundle)
    app, _ = _app(monkeypatch, bundle)
    return await _get(app, bundle.game_id)


def _absent(bundle: Bundle) -> None:
    """lockもreadも0行にする(別tenantまたは不存在)。"""
    bundle.override[started_read.GameLockToken] = TenantOperationResult(())
    bundle.override[started_read.GameReadToken] = TenantOperationResult(())


@pytest.mark.anyio
async def test_invisible_games_return_the_preparing_404_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """不可視・不存在は、preparing詳細の404と同じbytesで、match headerが無い。"""
    changes: list[Callable[[Bundle], None]] = [
        lambda b: b.game.update(status="preparing"),
        lambda b: b.game.update(status="finished"),
        lambda b: b.game.update(hidden_at=b.game["started_at"]),
        lambda b: b.game.update(trashed_at=b.game["started_at"]),
        lambda b: b.game.update(import_batch_id=uuid4()),
        _absent,
    ]
    bodies = []
    for change in changes:
        response = await _get_with(monkeypatch, change)
        assert response.status_code == 404
        assert _ACK not in response.headers and _CHALLENGE not in response.headers
        bodies.append(response.content)
    expected = await _preparing_404_bytes(monkeypatch)
    assert len({*bodies, expected}) == 1


@pytest.mark.anyio
async def test_recorded_game_returns_fixed_409_without_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """1球目として閉じられない記録は固定の409で、値を含まない。"""
    response = await _get_with(
        monkeypatch,
        lambda b: setattr(b, "nonempty", started_read.StartedPlayRowsExistenceToken),
    )
    assert response.status_code == 409
    assert response.json() == _FIXED_REQUEST_ERROR
    assert (
        _ACK not in response.headers and response.headers["cache-control"] == "no-store"
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    "change",
    [
        lambda b: b.game.update(started_at=None),
        lambda b: b.generation.update(kind="migration"),
        lambda b: b.generation.update(revoked_at=b.game["started_at"]),
        lambda b: b.generation.update(retired_at=b.game["started_at"]),
        lambda b: b.lineups.pop(),
        lambda b: b.override.update(
            {started_read.RecordingGenerationReadToken: TenantOperationResult(())}
        ),
    ],
)
async def test_corrupt_original_returns_the_fixed_503(
    monkeypatch: pytest.MonkeyPatch, change: Callable[[Bundle], None]
) -> None:
    """破損は固定の503で、SQLの語もDBの値も本文へ出さない。"""
    response = await _get_with(monkeypatch, change)
    assert response.status_code == 503
    assert response.json() == _FIXED_REQUEST_ERROR
    assert _ACK not in response.headers
    assert "game_id" not in response.text and "SELECT" not in response.text


@pytest.mark.anyio
async def test_unexpected_error_and_invalid_dto_are_the_same_503(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """原例外の文言とDTO検証の失敗は、公開本文にも記録にも出ない。"""
    secret = "secret-db-value-9f3a"
    bundle = _bundle_for(_TENANT_A, monkeypatch)
    app, _ = _app(monkeypatch, bundle)

    def boom(*_: Any) -> Any:
        raise RuntimeError(secret)

    monkeypatch.setattr(started_games, "read_started_game", boom)
    raised = await _get(app, bundle.game_id)
    monkeypatch.undo()
    bundle = _bundle_for(_TENANT_A, monkeypatch)
    app, _ = _app(monkeypatch, bundle)
    bundle.game.update(tournament_key="")
    invalid = await _get(app, bundle.game_id)
    assert raised.status_code == invalid.status_code == 503
    assert raised.content == invalid.content
    assert secret not in raised.text and secret not in caplog.text


@pytest.mark.anyio
async def test_c2_rejection_precedes_any_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """別tenantの期待値・不正challenge・未認証は、transactionを開始する前に拒否する。"""
    app, entered = _app(monkeypatch, None)
    game = uuid4()
    other = await _get(app, game, headers=_metadata_headers(_TENANT_B))
    bad = _metadata_headers(_TENANT_A)
    bad["X-Pitchlog-Tenant-Challenge"] = "not-a-uuid"
    challenge = await _get(app, game, headers=bad)
    anonymous = await _get(app, game, cookie=None)
    assert other.status_code == challenge.status_code == 404
    assert other.content == challenge.content
    assert anonymous.status_code == 401
    assert entered == []


@pytest.mark.anyio
async def test_other_tenant_cookie_cannot_read_the_game(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """別tenantとして認証した利用者は、同じ404になる(合成handleは0行を返す)。"""
    bundle = _bundle_for(_TENANT_A, monkeypatch)
    _absent(bundle)
    app, _ = _app(monkeypatch, bundle)
    response = await _get(app, bundle.game_id, tenant=_TENANT_B, cookie="token-b")
    assert response.status_code == 404
    assert response.content == await _preparing_404_bytes(monkeypatch)


def test_create_app_does_not_start_node(monkeypatch: pytest.MonkeyPatch) -> None:
    """新routeを足してもアプリ生成でNodeを起動しない。"""
    monkeypatch.setenv(
        "PITCHLOG_TOKEN_SIGNING_KEY_B64", base64.b64encode(b"r" * 32).decode("ascii")
    )

    def reject_node_start(_host: domainrt_host.NodeDomainHost) -> None:
        pytest.fail("create_appはNodeを起動しない")

    monkeypatch.setattr(domainrt_host.NodeDomainHost, "_start", reject_node_start)
    assert api_app.create_app().title == "Pitchlog API"


def _recorded_for_tenant(
    monkeypatch: pytest.MonkeyPatch, bundle: RecordedBundle
) -> RecordedBundle:
    """合成rowと認証済みtenant・scopeを一致させる（読取値そのものは変えない）。"""
    context = make_tenant_context(_TENANT_A)
    bundle.tenant = _TENANT_A
    for row in (
        bundle.game,
        bundle.generation,
        bundle.ledger,
        *bundle.events,
        *bundle.slots,
        *bundle.plays,
    ):
        row["tenant_id"] = _TENANT_A
    for lineup in bundle.lineups:
        lineup["tenant_id"] = _TENANT_A
    bundle.nonempty = started_read.StartedPlayRowsExistenceToken
    bundle.handle._bound_tenant_id = _TENANT_A
    bundle.handle._context = context
    bundle.handle._bound_integrity_proof = context._integrity_proof
    bundle.game.update(
        scheduled_at=bundle.game["started_at"],
        game_type_key="game_official",
        tournament_key="spring",
        plate_umpire="審判",
    )
    return bundle


@pytest.mark.anyio
async def test_recorded_first_ball_is_returned_with_public_values(
    monkeypatch: pytest.MonkeyPatch, recorded_bundle: RecordedBundle
) -> None:
    """実reader・実artifactを通した初球1件の200を、公開値だけで確かめる。"""
    bundle = _recorded_for_tenant(monkeypatch, recorded_bundle)
    app, entered = _app(monkeypatch, bundle)
    response = await _get(app, bundle.game_id)
    assert response.status_code == 200
    assert response.headers[_ACK] == "1"
    body = response.json()
    assert body["read_kind"] == "recorded" and body["status"] == "in_progress"
    assert body["id"] == str(bundle.game_id)
    assert body["current_d4"] == encode_d4_reference(_TENANT_A, bundle.game_id, 2**40)
    # `state` は initial と同じ before（0-0）で、記録後は after に分かれる。
    assert body["state"]["stateFields"]["state.count.balls"] == "0"
    after = body["after"]["stateFields"]
    assert (
        after["state.count.balls"],
        after["state.count.strikes"],
        after["state.outs"],
        after["state.inning"],
        after["state.half"],
    ) == ("1", "0", "0", "1", "top")
    (history,) = body["history"]
    assert history["kind"] == "confirmed-play"
    assert history["difference"]["stateFields"]["state.count.balls"] == {
        "before": "0",
        "after": "1",
    }
    assert len(body["stat_flags"]) == 23
    assert all(type(flag) is bool for flag in body["stat_flags"].values())
    assert body["stat_flags"]["投球数"] is True
    assert sorted(body["t2"]) == ["basis", "evaluation_point", "kind"]
    (play,) = body["play_rows"]
    assert set(play) == set(StartedPlayRow.model_fields)
    assert play["id"] == str(bundle.row_id)
    assert play["game_id"] == str(bundle.game_id)
    assert play["source_event_id"] == str(bundle.event_id)
    assert (play["play_number"], play["batting_order"], play["version"]) == (1, 1, 1)
    assert play["event_kind"] == "pitch"
    assert play["course"] == {"unit": "1/263", "x": "132", "y": "131"}
    assert play["pitch_type_key"] == "synthetic-only"
    assert play["batting_result_key"] == "batting-result.ball"
    assert (play["pitch_speed"], play["stance"], play["batting_side"]) == (
        None,
        None,
        None,
    )
    assert (play["press"], play["fake_run"]) == (None, None)
    assert len(play) == 35
    for leaked in (
        "tenant_id",
        "hidden_at",
        "import_batch_id",
        "legacy_row_identifier",
        "migration_unverified",
        "course_x",
        "course_y",
    ):
        assert leaked not in play
    assert [context.tenant_id for context in entered] == [_TENANT_A]


@pytest.mark.anyio
async def test_recorded_body_never_contains_recording_right_values(
    monkeypatch: pytest.MonkeyPatch, recorded_bundle: RecordedBundle
) -> None:
    """記録後200の本文bytesにも、保持者・資格・証明・tenantを出さない。"""
    bundle = _recorded_for_tenant(monkeypatch, recorded_bundle)
    app, _ = _app(monkeypatch, bundle)
    response = await _get(app, bundle.game_id)
    assert response.status_code == 200
    assert bundle.generation["holder_device"] not in response.text
    assert str(_TENANT_A) not in response.text
    lowered = response.text.lower()
    for word in (
        "holder_device",
        "device_id",
        "credential",
        "recording_right_proof",
        "recovery_generation",
        "watermark",
        "prefix",
        "tenant_id",
        "issuance_order",
        "granted_at",
    ):
        assert word not in lowered


def _second_ball(bundle: RecordedBundle) -> None:
    """保存初球の写しを2球目として1行足す。"""
    bundle.plays.append({**bundle.plays[0], "id": uuid4(), "play_number": 2})


def _tombstone(bundle: RecordedBundle) -> None:
    """保存イベントを墓標にする。"""
    bundle.events[0]["is_tombstone"] = True


def _revoked(bundle: RecordedBundle) -> None:
    """記録権世代を失効させる。"""
    bundle.generation["revoked_at"] = bundle.game["started_at"]


def _migration(bundle: RecordedBundle) -> None:
    """記録権世代を非normal（migration）にする。"""
    bundle.generation["kind"] = "migration"


@pytest.mark.anyio
@pytest.mark.parametrize("change", [_second_ball, _tombstone, _revoked, _migration])
async def test_recorded_that_is_not_exactly_one_first_ball_is_the_fixed_409(
    monkeypatch: pytest.MonkeyPatch, recorded_bundle: RecordedBundle, change: Any
) -> None:
    """2球目・墓標・失効世代・非normal世代は、initialの409と同じ外形へ閉じる。"""
    bundle = _recorded_for_tenant(monkeypatch, recorded_bundle)
    change(bundle)
    app, _ = _app(monkeypatch, bundle)
    response = await _get(app, bundle.game_id)
    assert response.status_code == 409
    assert response.json() == _FIXED_REQUEST_ERROR
    assert _ACK not in response.headers


@pytest.mark.anyio
async def test_corrupt_saved_play_row_is_the_fixed_503(
    monkeypatch: pytest.MonkeyPatch, recorded_bundle: RecordedBundle
) -> None:
    """保存値と再評価値の不一致（破損）は409へ畳まず503へ閉じる。"""
    bundle = _recorded_for_tenant(monkeypatch, recorded_bundle)
    bundle.plays[0]["course_x"] = 0.123
    app, _ = _app(monkeypatch, bundle)
    response = await _get(app, bundle.game_id)
    assert response.status_code == 503
    assert response.json() == _FIXED_REQUEST_ERROR
    assert _ACK not in response.headers
