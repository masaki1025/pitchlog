"""1 球同期の縦スライスを実 DB で検査する。"""

from __future__ import annotations

import base64
import secrets
from typing import Any, LiteralString, cast
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from test_authz_tenant_context import make_tenant_context

from db.test_sync_apply_prefix_path_boundary import (
    _SyncDatabase as SyncDatabase,
)
from db.test_sync_apply_prefix_path_boundary import (
    prefix_database,  # noqa: F401 — module scope に置いて fixture 引数を解決する
    sync_database,  # noqa: F401 — prefix_database の引数解決のために転用する
)
from pitchlog.api.app import create_app
from pitchlog.api.tenant_access import require_tenant_access
from pitchlog.sync import ports, spike_http, spike_ports

pytestmark = pytest.mark.requires_db


@pytest.fixture
def one_ball_database(prefix_database: SyncDatabase) -> SyncDatabase:  # noqa: F811
    """Prefix 試験の使い捨て試合スロットを spike の 1 球検証に再利用する。"""
    return prefix_database


@pytest.fixture
def no_generation_database(
    sync_database: SyncDatabase,  # noqa: F811
) -> SyncDatabase:  # noqa: F811
    """`games` 行だけを持ち、`recording_generations` 行を持たない試合を作る。

    世代行の発行は未実装の U-R1（要求境界で行う）。よって現実の試合は、
    一度も同期適用していない間は世代行が 0 件であり、認可済みの `games` 行
    だけが存在する。fixture は `prefix_database` の `games` の複製だけを行い、
    世代の INSERT を行わない。
    """
    game_id = uuid4()
    with sync_database.catalog.applicator.cursor() as cursor:
        cursor.execute(
            "INSERT INTO games (tenant_id, id, scheduled_at, game_type_key, "
            "tournament_key, away_team_record_id, home_team_record_id, applied_rules) "
            "SELECT tenant_id, %s, scheduled_at, game_type_key, "
            "tournament_key, away_team_record_id, home_team_record_id, applied_rules "
            "FROM games WHERE tenant_id = %s AND id = %s",
            (game_id, sync_database.tenant_a, sync_database.game_a),
        )
    sync_database.catalog.applicator.commit()
    return SyncDatabase(
        sync_database.catalog,
        sync_database.tenant_a,
        sync_database.tenant_b,
        game_id,
        sync_database.game_b,
    )


@pytest.fixture(autouse=True)
def _register_spike_ports(monkeypatch: pytest.MonkeyPatch) -> None:
    """Spike のスタブポートだけをテスト中に登録し、製品の空表は保つ。"""
    monkeypatch.setattr(
        ports,
        "PORT_IMPLEMENTATIONS",
        frozenset(
            (cls.__module__, cls.__name__)
            for cls in (
                spike_ports.SpikeRights,
                spike_ports.SpikeProjection,
                spike_ports.SpikeValidator,
            )
        ),
    )


@pytest.fixture(autouse=True)
def _configure_signing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Spike 入口の ASGI 試験へ CSPRNG 由来の署名鍵を与える。"""
    encoded_key = base64.b64encode(secrets.token_bytes(32)).decode("ascii")
    monkeypatch.setenv("PITCHLOG_TOKEN_SIGNING_KEY_B64", encoded_key)


def _read_rows(
    db: SyncDatabase, query: LiteralString, values: tuple[object, ...]
) -> list[tuple[object, ...]]:
    """同期適用のスコープ外の独立 SQL で行を読む。"""
    with db.catalog.applicator.cursor() as cursor:
        cursor.execute(query, values)
        rows = list(cursor.fetchall())
    db.catalog.applicator.rollback()
    return cast(list[tuple[object, ...]], rows)


def _snapshot(
    db: SyncDatabase, tenant: UUID, game: UUID
) -> tuple[int, int, int, int]:
    """確定水位・操作イベント・台帳・拒否原本の件数を独立 SQL で読む。"""
    watermark_rows = _read_rows(
        db,
        "SELECT confirmed_watermark FROM recording_generations "
        "WHERE tenant_id = %s AND game_id = %s AND generation = 1",
        (tenant, game),
    )
    events_count = _read_rows(
        db,
        "SELECT count(*) FROM operation_events "
        "WHERE tenant_id = %s AND game_id = %s",
        (tenant, game),
    )
    ledger_count = _read_rows(
        db,
        "SELECT count(*) FROM idempotency_ledger WHERE tenant_id = %s",
        (tenant,),
    )
    originals_count = _read_rows(
        db,
        "SELECT count(*) FROM rejected_event_originals WHERE tenant_id = %s",
        (tenant,),
    )
    if not watermark_rows:
        # 他テナントの試合など、まだ確定水位を持たない試合のための既定。
        watermarks: tuple[object, ...] = (0,)
    else:
        watermarks = watermark_rows[0]
    watermark = watermarks[0]
    assert type(watermark) is int
    counts = (
        events_count[0][0],
        ledger_count[0][0],
        originals_count[0][0],
    )
    assert all(type(value) is int for value in counts), repr(counts)
    return cast(tuple[int, int, int, int], (watermark, *counts))


def _event_row(db: SyncDatabase, game: UUID) -> tuple[object, ...]:
    """保存済みの操作イベントの確定列を独立 SQL で読む。"""
    rows = _read_rows(
        db,
        "SELECT event_kind, d1, d2, (state_diff IS NOT NULL), "
        "(payload IS NULL), is_tombstone, ledger_kind, generation, d5 "
        "FROM operation_events WHERE tenant_id = %s AND game_id = %s",
        (db.tenant_a, game),
    )
    assert len(rows) == 1
    return rows[0]


def _ledger_kinds(db: SyncDatabase) -> tuple[object, ...]:
    """台帳で確定した区分の列を独立 SQL で読む。"""
    rows = _read_rows(
        db,
        "SELECT kind FROM idempotency_ledger WHERE tenant_id = %s "
        "ORDER BY d5",
        (db.tenant_a,),
    )
    return tuple(row[0] for row in rows)


def _one_ball_body(
    game_id: UUID,
    d5: UUID,
    *,
    d1: int = 1,
    d4: str = "1",
    d2: int = 0,
    event_kind: object = "1",
    proof: object = "spike-proof",
    payload: dict[str, object] | None = None,
) -> dict[str, object]:
    """計画の最小本文を 1 球分だけ組み立てる。"""
    event: dict[str, object] = {
        "d5": str(d5),
        "d1": d1,
        "d4": d4,
        "game_id": str(game_id),
        "event_kind": event_kind,
        "d2": d2,
        "payload": payload or {},
        "state_diff": {},
    }
    return {"recording_right_proof": proof, "events": [event]}


async def _post_one_ball(
    client: AsyncClient,
    game_id: UUID,
    body: dict[str, object],
) -> Any:
    """Spike 入口へ 1 要求だけ送る。"""
    response = await client.post(
        f"/games/{game_id}/sync/events",
        json=body,
    )
    return cast(Any, response)


@pytest.mark.anyio
async def test_one_ball_slice_persists_once_and_replays_as_duplicate(
    one_ball_database: SyncDatabase,
) -> None:
    """1 球の送信 → 原子保存 → 再送の重複を、独立 SQL で検証する。"""
    db = one_ball_database
    app = create_app()
    spike_http.install(app, tenant_access=require_tenant_access)
    app.dependency_overrides[require_tenant_access] = lambda: make_tenant_context(
        db.tenant_a
    )
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    d5 = uuid4()
    async with AsyncClient(transport=transport, base_url="https://test") as client:
        not_found = await client.get("/missing")
        first = await _post_one_ball(client, db.game_a, _one_ball_body(db.game_a, d5))
        assert first.status_code == 200
        ack = first.json()
        assert ack["boundary_result"] == "B1"
        assert ack["advanced_d3"] == 1
        assert ack["event_results"] == [
            {"d4": "1", "d1": 1, "d5": str(d5), "state": "受理", "reason": None}
        ]

        watermark, events, ledger, originals = _snapshot(db, db.tenant_a, db.game_a)
        assert watermark == 1
        assert events == 1
        assert ledger == 1
        assert originals == 0
        saved = _event_row(db, db.game_a)
        assert saved == ("play_input", 1, 0, True, False, False, "accepted", 1, d5)
        assert _ledger_kinds(db) == ("accepted",)

        state = await client.get(f"/games/{db.game_a}/sync/state")
        assert state.status_code == 200
        state_body = state.json()
        game_state = state_body.pop("game_state")
        # 再 POST せずに GET だけで適用済みの水位と受理済みの 1 球が見える。
        # 再読込の 1 件は墓標除外（is_tombstone = False）と現行世代
        # （generation = 1）の絞り込みを通過して残り、打ち切りは起きない。
        # payload が空の 1 球は T1 の入力にならないため、畳み込みは 0 件。
        assert game_state["appliedEvents"] == 0
        assert game_state["stateFields"]["state.runners"] == "empty"
        assert state_body == {
            "confirmed_watermark": 1,
            "events": [
                {
                    "d5": str(d5),
                    "d1": 1,
                    "d2": 0,
                    "generation": 1,
                    "event_kind": "play_input",
                    "state_diff": {},
                }
            ],
            "truncated": False,
        }
        assert state_body["events"][0]["generation"] == 1
        assert state_body["truncated"] is False

        second = await _post_one_ball(client, db.game_a, _one_ball_body(db.game_a, d5))
        assert second.status_code == 200
        replay = second.json()
        assert replay["boundary_result"] == "B1"
        assert replay["advanced_d3"] == 1
        assert replay["event_results"] == [
            {"d4": "1", "d1": 1, "d5": str(d5), "state": "重複", "reason": None}
        ]
        watermark_after, events_after, ledger_after, originals_after = _snapshot(
            db, db.tenant_a, db.game_a
        )
        assert watermark_after == watermark
        assert events_after == events
        assert ledger_after == ledger
        assert originals_after == originals
        assert _ledger_kinds(db) == ("accepted",)

        stranger_game = uuid4()
        unknown = await _post_one_ball(
            client, stranger_game, _one_ball_body(stranger_game, uuid4())
        )
        assert unknown.status_code == 404
        assert unknown.content == not_found.content

        violation = await _post_one_ball(
            client,
            db.game_a,
            _one_ball_body(db.game_a, uuid4(), event_kind="8"),
        )
        assert violation.status_code == 422
        watermark_last, events_last, ledger_last, originals_last = _snapshot(
            db, db.tenant_a, db.game_a
        )
        assert watermark_last == watermark
        assert events_last == events
        assert ledger_last == ledger
        assert originals_last == originals
        assert _ledger_kinds(db) == ("accepted",)


@pytest.mark.anyio
async def test_state_before_any_apply_reports_zero_watermark_and_empty_events(
    no_generation_database: SyncDatabase,
) -> None:
    """世代行が無い（まだ一度も同期適用していない）試合は 200 の水位 0・イベント空。

    試合は認可後という前提のため 404 にせず、`GET /missing` と同一の固定封筒
    と混ぜない。列挙防止の意味を濁らせない。
    """
    db = no_generation_database
    app = create_app()
    spike_http.install(app, tenant_access=require_tenant_access)
    app.dependency_overrides[require_tenant_access] = lambda: make_tenant_context(
        db.tenant_a
    )
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="https://test") as client:
        state = await client.get(f"/games/{db.game_a}/sync/state")
        assert state.status_code == 200
        state_body = state.json()
        game_state = state_body.pop("game_state")
        # 応答形は既存形（水位 0・イベント空）に打ち切りがないことを足した形。
        assert state_body == {
            "confirmed_watermark": 0,
            "events": [],
            "truncated": False,
        }
        # 状態は先頭（初期状態）で、適用できたイベントは 0 件。
        assert game_state["appliedEvents"] == 0
        assert game_state["stateFields"]["state.inning"] == 1
        assert state_body["confirmed_watermark"] == 0
        assert state_body["events"] == []


@pytest.mark.anyio
async def test_other_tenant_game_is_identical_404_and_writes_nothing(
    one_ball_database: SyncDatabase,
) -> None:
    """他テナントの試合は自テナント文脈では経路不存在と同一の 404 で、行を書かない。"""
    db = one_ball_database
    app = create_app()
    spike_http.install(app, tenant_access=require_tenant_access)
    app.dependency_overrides[require_tenant_access] = lambda: make_tenant_context(
        db.tenant_a
    )
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    before = _snapshot(db, db.tenant_b, db.game_b)
    async with AsyncClient(transport=transport, base_url="https://test") as client:
        not_found = await client.get("/missing")
        response = await _post_one_ball(
            client, db.game_b, _one_ball_body(db.game_b, uuid4())
        )
        assert response.status_code == 404
        assert response.content == not_found.content
    after = _snapshot(db, db.tenant_b, db.game_b)
    assert after == before


@pytest.mark.anyio
async def test_saved_ball_is_folded_into_state_on_ack_and_reload(
    one_ball_database: SyncDatabase,
) -> None:
    """1 球保存の応答と再読込が同じ T1 の畳み込み結果を返す。"""
    db = one_ball_database
    app = create_app()
    spike_http.install(app, tenant_access=require_tenant_access)
    app.dependency_overrides[require_tenant_access] = lambda: make_tenant_context(
        db.tenant_a
    )
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="https://test") as client:
        first = await _post_one_ball(
            client,
            db.game_a,
            _one_ball_body(
                db.game_a,
                uuid4(),
                d1=1,
                payload={
                    "resultId": "batting-result.single",
                    "pitchEventKind": "pitch-event",
                },
            ),
        )
        assert first.status_code == 200
        state = first.json()["game_state"]
        assert state["appliedEvents"] == 1
        assert state["stateFields"]["state.runners"] == "first"
        assert state["stateFields"]["state.battingOrder"] == 2
        assert state["stateFields"]["state.count.strikes"] == 0
        assert state["stateFields"]["state.outs"] == 0

        reload = await client.get(f"/games/{db.game_a}/sync/state")
        assert reload.status_code == 200
        assert reload.json()["game_state"] == state

        second = await _post_one_ball(
            client,
            db.game_a,
            _one_ball_body(
                db.game_a,
                uuid4(),
                d1=2,
                d2=1,
                payload={
                    "resultId": "batting-result.home-run",
                    "pitchEventKind": "pitch-event",
                },
            ),
        )
        assert second.status_code == 200
        state2 = second.json()["game_state"]
        assert state2["appliedEvents"] == 2
        assert state2["stateFields"]["state.runners"] == "empty"
        # 単打で出た一塁走者と打者の 2 人が生還する（付録E-2 本塁打）。
        assert state2["stateFields"]["state.score"] == {"home": 0, "away": 2}
        assert state2["stateFields"]["state.battingOrder"] == 3

        reload2 = await client.get(f"/games/{db.game_a}/sync/state")
        assert reload2.status_code == 200
        assert reload2.json()["game_state"] == state2
