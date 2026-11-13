"""同HTTP GETの非play分岐。DBは明示row double、認証/C2/DTOは実経路。"""

import copy
import json
from contextlib import ExitStack
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from test_api_started_game import _app, _bundle_for
from test_authz_tenant_context import make_tenant_context
from test_nonplay_normal_payload import fixture_values
from test_roster_boundary import _TENANT_A, _TENANT_B, _metadata_headers

from pitchlog.repositories import transaction as tx
from pitchlog.repositories.nonplay_prefix_read_operations import (
    NonplayActiveHistoryReadToken,
)
from pitchlog.repositories.ordinary_order import OrdinaryOrderSummaryToken
from pitchlog.repositories.ordinary_prefix_operations import OrdinaryCheckpointReadToken
from pitchlog.repositories.past_correction_right import _ReadP3CurrentToken
from pitchlog.repositories.started_read import read_started_game
from pitchlog.repositories.started_snapshot_read_operations import (
    StartedNonplayActiveHistoryReadToken,
)
from pitchlog.repositories.tokens import TenantOperationResult
from pitchlog.sync.d4_reference import encode_d4_reference
from pitchlog.sync.idempotency import source_fingerprint


def setup_view(monkeypatch):
    """実start metadataとNP CPの合成保存面を分離し、期待を製品GETから採取しない。"""
    b = _bundle_for(_TENANT_A, monkeypatch)
    initial = read_started_game(b.handle, b.game_id)
    from pitchlog.repositories.started_read import StartedGameView

    assert type(initial) is StartedGameView
    v7, _ = fixture_values()
    cp = copy.deepcopy(v7["calculation"]["request"]["source"]["checkpoint"])
    c = cp["content"]
    d4 = encode_d4_reference(_TENANT_A, b.game_id, 1)
    c["scope"] = {
        "tenantId": str(_TENANT_A),
        "gameId": str(b.game_id),
        "generation": d4,
    }
    for name in ("d1Head", "projectionHead"):
        c[name]["source"]["gameId"] = str(b.game_id)
        c[name]["source"]["generation"] = d4
    cp["ref"]["digest"] = source_fingerprint(c)
    b.generation.update(
        confirmed_watermark=int(c["d3"]),
        applied_prefix=int(c["d3"]),
        recovery_generation=1,
    )
    context = make_tenant_context(_TENANT_A)
    b.handle._context = context
    b.handle._bound_integrity_proof = context._integrity_proof
    top = SimpleNamespace(is_active=True)
    session = SimpleNamespace(
        get_transaction=lambda: top, in_nested_transaction=lambda: False
    )
    monkeypatch.setitem(
        tx._TRANSACTION_RUNTIMES, b.handle._state_key, (session, ExitStack())
    )
    row = dict(
        tenant_id=str(_TENANT_A),
        game_id=str(b.game_id),
        internal_generation=1,
        id=cp["ref"]["id"],
        revision=int(cp["ref"]["revision"]),
        history_version=int(c["storageHistoryEpoch"]),
        recovery_generation=1,
        confirmed_watermark=int(c["d3"]),
        applied_watermark=int(c["d3"]),
        content_digest=cp["ref"]["digest"],
        content=cp,
        roster=initial.roster.model_dump(mode="json", by_alias=True),
        state="current",
        saved_at=b.game["started_at"].isoformat(),
    )
    row["last_play_row"] = None
    calls = []

    def run(handle, token):
        calls.append(type(token))
        if type(token) is OrdinaryOrderSummaryToken:
            value = {
                "tail": {
                    "tenant_id": str(_TENANT_A),
                    "game_id": str(b.game_id),
                    "generation": 1,
                    "d1": 2,
                    "d2": 2024,
                },
                "duplicate": False,
                "recovery_generation": 1,
            }
        elif type(token) is OrdinaryCheckpointReadToken:
            value = {"kind": "checkpoint", "row": row}
        elif type(token) in {
            NonplayActiveHistoryReadToken,
            StartedNonplayActiveHistoryReadToken,
        }:
            value = {"checkpoint": cp, "total": 0, "items": []}
        elif type(token) is _ReadP3CurrentToken:
            value = {"kind": "none"}
        else:
            raise AssertionError("公開GETからwriter関数へ到達")
        return TenantOperationResult(((json.dumps(value),),))

    monkeypatch.setattr(tx._TenantTransaction, "run_function", run)
    app, _ = _app(monkeypatch, b)
    return app, b, cp, calls


@pytest.mark.anyio
async def test_nonplay_get_in_rr_scope_uses_unlocked_page(monkeypatch):
    """同snapshotの非play原本を別read関数で照合し、行lockを発行しない。"""
    from pitchlog.sync.tokens import GameLockToken, RecordingGenerationLockToken

    app, bundle, _, calls = setup_view(monkeypatch)
    session = tx._TRANSACTION_RUNTIMES[bundle.handle._state_key][0]
    monkeypatch.setitem(
        tx._STARTED_READ_HANDLES,
        bundle.handle._state_key,
        (bundle.handle, session.get_transaction()),
    )
    bundle.calls.clear()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test"
    ) as client:
        client.cookies.set("__Host-pitchlog_token", "token-a")
        response = await client.get(
            f"/games/{bundle.game_id}/started?projection=play-prefix-v3",
            headers=_metadata_headers(_TENANT_A),
        )
    assert response.status_code == 200
    assert response.json()["read_kind"] == "nonplay-prefix"
    # 非play CPはplay-onlyのGET専用関数ではなく非play受理印を照合するreaderで読む。
    assert NonplayActiveHistoryReadToken in calls
    assert StartedNonplayActiveHistoryReadToken not in calls
    assert not any(
        type(token) in {GameLockToken, RecordingGenerationLockToken}
        for token in bundle.calls
    )


@pytest.mark.anyio
async def test_get_after_two_pops_preserves_real_heads_allocator_and_empty_page(
    monkeypatch,
):
    """実D3=4/tailD1=2を許可し、D2/物理番号を初期へ戻さない。"""
    app, b, cp, calls = setup_view(monkeypatch)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test"
    ) as client:
        client.cookies.set("__Host-pitchlog_token", "token-a")
        response = await client.get(
            f"/games/{b.game_id}/started?projection=play-prefix-v3",
            headers=_metadata_headers(_TENANT_A),
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["read_kind"] == "nonplay-prefix" and body["checkpoint"] == cp
    assert body["next_position"] == {"d1": "5", "d2": "3024"}
    assert body["checkpoint"]["content"]["activeDepth"] == "0"
    assert body["checkpoint"]["content"]["nextPhysicalPlayNumber"] == "3"
    assert body["page"] == {"items": [], "next_cursor": None}
    assert calls == [
        OrdinaryOrderSummaryToken,
        OrdinaryCheckpointReadToken,
        _ReadP3CurrentToken,
        NonplayActiveHistoryReadToken,
    ]
    raw = json.dumps(body)
    for key in (
        "binding_nonce",
        "nonce_digest",
        "lease_id",
        "admission",
        "credential_digest",
    ):
        assert key not in raw


@pytest.mark.anyio
async def test_foreign_tenant_request_never_uses_nonplay_read_capability(monkeypatch):
    """C2の越境拒否を実routeで保持する。"""
    app, b, _, calls = setup_view(monkeypatch)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test"
    ) as client:
        client.cookies.set("__Host-pitchlog_token", "token-a")
        response = await client.get(
            f"/games/{b.game_id}/started?projection=play-prefix-v3",
            headers=_metadata_headers(_TENANT_B),
        )
    assert response.status_code in {403, 404}
    assert calls == []


@pytest.mark.anyio
async def test_undo_projection_reuses_existing_nonplay_dto_without_writer_qualification(
    monkeypatch,
):
    """新projectionも既NPを正直に返し、既v3 GETや保存資格を変更しない。"""
    app, bundle, checkpoint, calls = setup_view(monkeypatch)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test"
    ) as client:
        client.cookies.set("__Host-pitchlog_token", "token-a")
        response = await client.get(
            f"/games/{bundle.game_id}/started?projection=undo-prefix-v1",
            headers=_metadata_headers(_TENANT_A),
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["read_kind"] == "nonplay-prefix" and body["checkpoint"] == checkpoint
    assert body["profile"] == "nonplay-prefix-read-v1"
    assert body["next_position"] == {"d1": "5", "d2": "3024"}
    assert calls == [
        OrdinaryOrderSummaryToken,
        OrdinaryCheckpointReadToken,
        OrdinaryOrderSummaryToken,
        OrdinaryCheckpointReadToken,
        _ReadP3CurrentToken,
        NonplayActiveHistoryReadToken,
    ]


def test_undo_snapshot_uses_real_game_generation_and_readonly_point_tokens(monkeypatch):
    """新入口のscope helperも同じGame/generation lockと正規CPを検証する。"""
    from pitchlog.repositories.nonplay_prefix_read import _read_undo_snapshot

    _, bundle, checkpoint, calls = setup_view(monkeypatch)
    snapshot = _read_undo_snapshot(bundle.handle, bundle.game_id)
    assert type(snapshot) is dict
    assert snapshot["row"]["content"] == checkpoint
    assert snapshot["d3"] == 4 and snapshot["generation"] == 1
    assert calls == [OrdinaryOrderSummaryToken, OrdinaryCheckpointReadToken]


@pytest.mark.parametrize(
    "mutation", ["tenant", "revoked", "generation-bool", "gap", "profile"]
)
def test_undo_snapshot_scope_and_unknown_profile_are_closed(monkeypatch, mutation):
    """scope破損や未知profileを旧v3へ推測で補完しない。"""
    from uuid import UUID

    from pitchlog.repositories.nonplay_prefix import NonplaySourceUnavailable
    from pitchlog.repositories.nonplay_prefix_read import read_undo_prefix

    _, bundle, checkpoint, _ = setup_view(monkeypatch)
    if mutation == "tenant":
        bundle.game["tenant_id"] = UUID(int=999)
    elif mutation == "revoked":
        bundle.generation["revoked_at"] = bundle.game["started_at"]
    elif mutation == "generation-bool":
        bundle.generation["generation"] = True
    elif mutation == "gap":
        bundle.generation["applied_prefix"] = 3
    else:
        checkpoint["formatVersion"] = "unknown"
    with pytest.raises(NonplaySourceUnavailable):
        read_undo_prefix(bundle.handle, bundle.game_id)


@pytest.mark.parametrize("drift", [False, True])
def test_undo_snapshot_reads_full_v3_head_and_rejects_second_point_drift(
    monkeypatch, drift
):
    """Raw point段は旧full-head入口を使い、後段の型/数学検査を省略しない。"""
    from pitchlog.authz import terminal_pitch_product
    from pitchlog.repositories.nonplay_prefix import NonplaySourceUnavailable
    from pitchlog.repositories.nonplay_prefix_read import _read_undo_snapshot
    from pitchlog.sync.terminal_pitch_tokens import PlayPrefixCheckpointReadToken

    _, bundle, checkpoint, _ = setup_view(monkeypatch)
    # このcaseは入口選択/二重点照合だけのdouble。完成したv3/DB原本とは扱わない。
    checkpoint.clear()
    checkpoint["version"] = "3"
    original = tx._TenantTransaction.run_function
    raw_point = original(
        bundle.handle, OrdinaryCheckpointReadToken(bundle.game_id, 1)
    ).rows[0][0]
    assert isinstance(raw_point, str)
    point = json.loads(raw_point)
    seen = []
    modes = []
    monkeypatch.setattr(
        terminal_pitch_product,
        "require_registered_product",
        lambda **kw: modes.append(kw["mode"]),
    )

    def run(handle, token):
        seen.append(type(token))
        if type(token) is PlayPrefixCheckpointReadToken:
            full = copy.deepcopy(point)
            full["row"].update(
                last_history={"real-head-fixture": True}, last_play_runners=[]
            )
            if drift:
                full["row"]["revision"] += 1
            return TenantOperationResult(((json.dumps(full),),))
        return original(handle, token)

    monkeypatch.setattr(tx._TenantTransaction, "run_function", run)
    if drift:
        with pytest.raises(NonplaySourceUnavailable):
            _read_undo_snapshot(bundle.handle, bundle.game_id)
    else:
        snapshot = _read_undo_snapshot(bundle.handle, bundle.game_id)
        assert snapshot["row"]["last_history"] == {"real-head-fixture": True}
    assert modes == ["play-prefix-play-v3"]
    assert seen == [
        OrdinaryOrderSummaryToken,
        OrdinaryCheckpointReadToken,
        PlayPrefixCheckpointReadToken,
    ]
