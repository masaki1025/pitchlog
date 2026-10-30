"""新prefix GETの合成row対向。実PG/実認証資格の縦断証拠ではない。"""

import json

import pytest
from httpx import ASGITransport, AsyncClient
from test_api_started_game import _app, _bundle_for
from test_roster_boundary import _TENANT_A, _metadata_headers

from pitchlog.repositories.ordinary_order import OrdinaryOrderSummaryToken
from pitchlog.repositories.ordinary_prefix_operations import OrdinaryCheckpointReadToken
from pitchlog.repositories.tokens import TenantOperationResult
from pitchlog.repositories.transaction import _TenantTransaction


def _read_functions(monkeypatch, *, summary=None, stored=None):
    """readonly二入口のみ合成しwriter関数呼出は直ちに失敗させる。"""
    seen = []

    def run(handle, token):
        seen.append(type(token))
        if type(token) is OrdinaryOrderSummaryToken:
            return TenantOperationResult(
                (
                    (
                        json.dumps(
                            summary
                            or {
                                "tail": None,
                                "duplicate": False,
                                "recovery_generation": 1,
                            }
                        ),
                    ),
                )
            )
        if type(token) is OrdinaryCheckpointReadToken:
            return (
                TenantOperationResult(())
                if stored is None
                else TenantOperationResult(((json.dumps(stored),),))
            )
        raise AssertionError("GETはwriter資格/新checkpointを発行しない")

    monkeypatch.setattr(_TenantTransaction, "run_function", run)
    return seen


@pytest.mark.anyio
async def test_n0_get_uses_actual_start_and_readonly_functions(monkeypatch):
    """新projectionで実start時刻/空prefix、旧無queryの応答shapeは保持。"""
    bundle = _bundle_for(_TENANT_A, monkeypatch)
    bundle.generation["recovery_generation"] = 1
    app, _ = _app(monkeypatch, bundle)
    seen = _read_functions(monkeypatch)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test"
    ) as client:
        client.cookies.set("__Host-pitchlog_token", "token-a")
        response = await client.get(
            f"/games/{bundle.game_id}/started?projection=ordinary-prefix-v1",
            headers=_metadata_headers(_TENANT_A),
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["read_kind"] == "recorded-prefix"
        assert body["prefix_ref"]["length"] == "0"
        assert body["after"] == body["state"]
        assert body["page"] == {"items": [], "next_cursor": None}
        assert body["checkpoint_anchor"] is None and body["t2"] is None
        assert body["last_saved_at"] == body["started_at"]
        assert body["next_position"] == {"d1": "1", "d2": "1"}
        assert seen == [OrdinaryOrderSummaryToken, OrdinaryCheckpointReadToken]
        legacy = await client.get(
            f"/games/{bundle.game_id}/started", headers=_metadata_headers(_TENANT_A)
        )
        assert legacy.status_code == 200
        assert legacy.json()["read_kind"] == "initial"
        assert "prefix_ref" not in legacy.json()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "fault",
    [
        "duplicate",
        "false-tail",
        "fake-save",
        "unknown-projection",
        "limit0",
        "limit101",
    ],
)
async def test_new_get_closes_invalid_source_and_query(monkeypatch, fault):
    """自由保存時刻/原本矛盾や範囲外queryで成功を作らない。"""
    bundle = _bundle_for(_TENANT_A, monkeypatch)
    bundle.generation["recovery_generation"] = 1
    app, _ = _app(monkeypatch, bundle)
    summary = {
        "tail": {} if fault == "false-tail" else None,
        "duplicate": fault == "duplicate",
        "recovery_generation": 1,
    }
    stored = (
        {
            "kind": "first-ball-save",
            "source_event_id": str(bundle.game_id),
            "saved_at": "2026-10-30T00:00:00Z",
        }
        if fault == "fake-save"
        else None
    )
    _read_functions(monkeypatch, summary=summary, stored=stored)
    query = (
        "projection=unknown"
        if fault == "unknown-projection"
        else "projection=ordinary-prefix-v1"
    )
    if fault.startswith("limit"):
        query += "&limit=" + fault[5:]
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test"
    ) as client:
        client.cookies.set("__Host-pitchlog_token", "token-a")
        response = await client.get(
            f"/games/{bundle.game_id}/started?{query}",
            headers=_metadata_headers(_TENANT_A),
        )
    assert response.status_code == (
        422 if fault in {"unknown-projection", "limit0", "limit101"} else 503
    )
    assert "after" not in response.json()
