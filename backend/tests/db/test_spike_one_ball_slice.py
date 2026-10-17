"""1 球同期の縦スライスを実 DB で検査する。"""

from __future__ import annotations

import base64
import secrets
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from test_authz_tenant_context import make_tenant_context
from db.test_sync_apply_prefix_path_boundary import (
    _SyncDatabase,
    prefix_database,
    sync_database,
)
from db.test_sync_apply_operations_boundary import _SyncDatabase as SyncDatabase

from pitchlog.api.app import create_app
from pitchlog.api.tenant_access import require_tenant_access
from pitchlog.sync import ports, spike_http, spike_ports

pytestmark = pytest.mark.requires_db


@pytest.fixture(autouse=True)
def _register_spike_ports(monkeypatch: pytest.MonkeyPatch) -> None:
    """spike のスタブポートだけをテスト中に登録し、製品の空表は保つ。"""
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
    """spike 入口の ASGI 試験へ CSPRNG 由来の署名鍵を与える。"""
    encoded_key = base64.b64encode(secrets.token_bytes(32)).decode("ascii")
    monkeypatch.setenv("PITCHLOG_TOKEN_SIGNING_KEY_B64", encoded_key)


def _read_rows(
    db: SyncDatabase, query: str, values: tuple[object, ...]
) -> list[tuple[object, ...]]:
    """同期適用のスコープ外の独立 SQL で行を読む。"""
    with db.catalog.applicator.cursor() as cursor:
        cursor.execute(query, values)
        rows = list(cursor.fetchall())
    db.catalog.applicator.rollback()
    return cast(list[tuple[object, ...]], rows)


def _snapshot(db: SyncDatabase, game: UUID) -> tuple[int, int, int, int]:
    """確定水位・操作イベント・台帳・拒否原本の件数を独立 SQL で読む。"""
    watermark_rows = _read_rows(
        db,
        "SELECT confirmed_watermark FROM recording_generations "
        "WHERE tenant_id = %s AND game_id = %s AND generation = 1",
        (db.tenant_a, game),
    )
    events_count = _read_rows(
        db,
        "SELECT count(*) FROM operation_events "
        "WHERE tenant_id = %s AND game_id = %s",
        (db.tenant_a, game),
    )
    ledger_count = _read_rows(
        db,
        "SELECT count(*) FROM idempotency_ledger WHERE tenant_id = %s",
        (db.tenant_a,),
    )
    originals_count = _read_rows(
        db,
        "SELECT count(*) FROM rejected_event_originals WHERE tenant_id = %s",
        (db.tenant_a,),
    )
    assert len(watermark_rows) == 1
    watermark = watermark_rows[0][0]
    assert type(watermark) is int
    counts = (
        events_count[0][0],
        ledger_count[0][0],
        originals_count[0][0],
    )
    assert all(type(value) is int for value in counts), repr(counts)
    return watermark, counts[0], counts[1], counts[2]


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
    event_kind: object = "1",
    proof: object = "spike-proof",
) -> dict[str, object]:
    """計画の最小本文を 1 球分だけ組み立てる。"""
    event: dict[str, object] = {
        "d5": str(d5),
        "d1": d1,
        "d4": d4,
        "game_id": str(game_id),
        "event_kind": event_kind,
        "d2": 0,
        "payload": {},
        "state_diff": {},
    }
    return {"recording_right_proof": proof, "events": [event]}


async def _post_one_ball(
    client: AsyncClient,
    game_id: UUID,
    body: dict[str, object],
) -> Any:
    """spike 入口へ 1 要求だけ送る。"""
    response = await client.post(
        f"/games/{game_id}/sync/events",
        json=body,
    )
    return cast(Any, response)


@pytest.mark.anyio
async def test_one_ball_slice_persists_once_and_replays_as_duplicate(
    prefix_database: SyncDatabase,
) -> None:
    """1 球の送信 → 原子保存 → 再送の重複を、独立 SQL で検証する。"""
    db = prefix_database
    app = create_app()
    spike_http.install(app)
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
        assert ack["boundary_result"] in {"B1", "B2", "B3", "B4"}
        assert ack["advanced_d3"] == 1
        assert ack["event_results"] == [
            {"d4": "1", "d1": 1, "d5": str(d5), "state": "受理", "reason": None}
        ]

        watermark, events, ledger, originals = _snapshot(db, db.game_a)
        assert watermark == 1
        assert events == 1
        assert ledger == 1
        assert originals == 0
        saved = _event_row(db, db.game_a)
        assert saved == ("play_input", 1, 0, True, False, False, "accepted", 1, d5)
        assert _ledger_kinds(db) == ("accepted",)

        second = await _post_one_ball(client, db.game_a, _one_ball_body(db.game_a, d5))
        assert second.status_code == 200
        replay = second.json()
        assert replay["boundary_result"] in {"B1", "B2", "B3", "B4"}
        assert replay["advanced_d3"] == 1
        assert replay["event_results"] == [
            {"d4": "1", "d1": 1, "d5": str(d5), "state": "重複", "reason": None}
        ]
        watermark_after, events_after, ledger_after, originals_after = _snapshot(
            db, db.game_a
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
            db, db.game_a
        )
        assert watermark_last == watermark
        assert events_last == events
        assert ledger_last == ledger
        assert originals_last == originals
        assert _ledger_kinds(db) == ("accepted",)
