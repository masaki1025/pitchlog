"""認可後routeのD5/V12順だけを確認する。認証・DB成立の証拠ではない。"""

from types import SimpleNamespace
from typing import cast
from uuid import UUID

import pytest
from fastapi import HTTPException
from starlette.requests import Request
from test_authz_tenant_context import make_tenant_context

from pitchlog.api.routers import sync
from pitchlog.sync.model import A5Result, AckResult


@pytest.mark.parametrize("proof", ["absent", "null", "old"])
def test_stored_d5_precedes_null_missing_or_old_v12(monkeypatch, proof):
    """V12の再判定に進まず保存済みD5だけを返す（D5応答は明示double）。"""
    game, d5 = UUID(int=12), UUID(int=8)
    payload: dict[str, object] = {
        "events": [
            {
                "d5": str(d5),
                "game_id": str(game),
                "d1": 3,
                "d4": "generation-A",
                "event_kind": "undo",
                "payload": {},
            }
        ]
    }
    if proof != "absent":
        payload["recording_right_proof"] = None if proof == "null" else {"old": True}
    seen = []
    monkeypatch.setattr(sync, "_configuration", lambda request: SimpleNamespace())

    def replay(*args):
        seen.append("D5")
        return AckResult("B1", 3, (A5Result("generation-A", 3, str(d5), "重複"),))

    monkeypatch.setattr(sync, "_replay_e1_without_binding", replay)
    result = sync.sync_events(
        game,
        payload,
        cast(Request, object()),
        make_tenant_context(UUID(int=13)),
        "public-unit-cookie",
        UUID(int=999),
        "public-unit-credential",
        UUID(int=15),
    )
    assert result.status_code == 200 and seen == ["D5"]


def test_unused_null_v12_retains_existing_closed_rejection(monkeypatch):
    """未使用D5へ成功を補わず、既null拒否の位置だけをD5後へ移す。"""
    game = UUID(int=12)
    payload: dict[str, object] = {
        "recording_right_proof": None,
        "events": [
            {
                "d5": str(UUID(int=8)),
                "game_id": str(game),
                "d1": 3,
                "d4": "generation-A",
                "event_kind": "undo",
                "payload": {},
            }
        ],
    }
    seen = []
    monkeypatch.setattr(sync, "_configuration", lambda request: SimpleNamespace())
    monkeypatch.setattr(
        sync, "_replay_e1_without_binding", lambda *a: seen.append("D5")
    )
    with pytest.raises(HTTPException) as error:
        sync.sync_events(
            game,
            payload,
            cast(Request, object()),
            make_tenant_context(UUID(int=13)),
            "public-unit-cookie",
            UUID(int=999),
            "public-unit-credential",
            UUID(int=15),
        )
    assert error.value.status_code == 422 and seen == ["D5"]
