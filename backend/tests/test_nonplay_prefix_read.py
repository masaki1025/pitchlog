"""有限非play readerのscope/型/cursor対向。実DB資格の成功とは区別する。"""

import copy
import json
from contextlib import ExitStack
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from test_authz_tenant_context import make_tenant_context
from test_nonplay_normal_payload import fixture_values

from pitchlog.repositories import nonplay_prefix_read as api
from pitchlog.repositories import transaction as tx
from pitchlog.repositories.nonplay_prefix_read_operations import (
    NonplayActiveHistoryReadToken,
)
from pitchlog.repositories.tokens import TenantOperationResult
from pitchlog.sync.idempotency import source_fingerprint


@pytest.fixture
def read_rig(monkeypatch):
    """製品型handleと実TX identity検査を残し、SQL応答だけを合成する。"""
    v7, _ = fixture_values()
    raw = v7["calculation"]["request"]["source"]["checkpoint"]
    cp = api.checked_checkpoint(
        raw,
        tenant=raw["content"]["scope"]["tenantId"],
        game=raw["content"]["scope"]["gameId"],
        generation=raw["content"]["scope"]["generation"],
        d3=int(raw["content"]["d3"]),
    )
    key = object()
    top = SimpleNamespace(is_active=True)
    session = SimpleNamespace(
        get_transaction=lambda: top, in_nested_transaction=lambda: False
    )
    runtime = (session, ExitStack())
    monkeypatch.setitem(tx._TRANSACTION_RUNTIMES, key, runtime)
    context = make_tenant_context(UUID(raw["content"]["scope"]["tenantId"]))
    handle = tx._TenantTransaction(
        context,
        key,
        context.tenant_id,
        context._integrity_proof,
        tx._HANDLE_CREATION_TOKEN,
    )
    calls = []
    packet = {"checkpoint": raw, "total": 0, "items": []}

    def run(actual, token):
        assert actual is handle and type(token) is NonplayActiveHistoryReadToken
        calls.append(token)
        return TenantOperationResult(((json.dumps(packet),),))

    monkeypatch.setattr(tx._TenantTransaction, "run_function", run)
    return SimpleNamespace(
        cp=cp,
        handle=handle,
        top=top,
        session=session,
        packet=packet,
        calls=calls,
        key=key,
    )


def test_empty_active_preserves_true_d3_and_finite_read(read_rig):
    """2pop後active空は初期D3=0でなく、readonly能力1だけを読む。"""
    r = read_rig
    assert int(r.cp.content.d3) > 0 and r.cp.content.active_depth == "0"
    assert api.read_active_page(r.handle, r.cp, generation=1, limit=1) == {
        "items": [],
        "next_cursor": None,
    }
    assert len(r.calls) == 1 and r.calls[0].d3 == int(r.cp.content.d3)
    assert r.calls[0].epoch == int(r.cp.content.storage_history_epoch)


@pytest.mark.parametrize(
    "field",
    [
        "total-bool",
        "cp-bool",
        "extra",
        "items-shape",
        "expired",
        "nested",
        "foreign",
        "unknown-cursor",
        "cursor-anchor",
    ],
)
def test_reader_closes_corruption_and_scope_changes(read_rig, field, monkeypatch):
    """型等値/別scope/失効/未知cursorを初期値へ補完しない。"""
    r = read_rig
    cursor = None
    if field == "total-bool":
        r.packet["total"] = False
    elif field == "cp-bool":
        r.packet["checkpoint"] = copy.deepcopy(r.packet["checkpoint"])
        r.packet["checkpoint"]["content"]["activeDepth"] = False
    elif field == "extra":
        r.packet["secret"] = "not-a-secret-test-marker"
    elif field == "items-shape":
        r.packet["items"] = {}
    elif field == "expired":
        r.top.is_active = False
    elif field == "nested":
        r.session.in_nested_transaction = lambda: True
    elif field == "foreign":
        r.handle._bound_tenant_id = UUID(int=998)
    elif field == "unknown-cursor":
        cursor = "!"
    else:
        cursor = (
            "eyJhbmNob3IiOnt9LCJwb3NpdGlvbiI6WzEsMSwiMDAwMDAwMDAtMDAw"
            "MC00MDAwLTgwMDAtMDAwMDAwMDAwMDAxIl19"
        )
    with pytest.raises((api.NonplaySourceUnavailable, ValueError)):
        api.read_active_page(r.handle, r.cp, generation=1, limit=1, cursor=cursor)


@pytest.mark.parametrize(
    "field", ["page_size", "revision", "d3", "after_d1", "generation"]
)
@pytest.mark.parametrize("bad", [True, 1.0, -1, None])
def test_read_token_rejects_numeric_type_equivalence(field, bad):
    """bool/floatをintへ変換せず全bound型を閉じる。"""
    values: dict[str, Any] = dict(
        game_id=UUID(int=1),
        generation=1,
        checkpoint_id=UUID(int=2),
        revision=1,
        epoch=1,
        d3=1,
        logical_version=1,
        after_order=0,
        after_d1=0,
        after_id=UUID(int=0),
        page_size=1,
    )
    values[field] = bad
    with pytest.raises(ValueError):
        NonplayActiveHistoryReadToken(**values)


def test_checkpoint_digest_and_head_cannot_follow_unknown_scope():
    """digestだけ追随してtenant/世代/水位を変えたCPも拒否する。"""
    v7, _ = fixture_values()
    original = v7["calculation"]["request"]["source"]["checkpoint"]
    for key, new in [
        ("generation", "other-generation"),
        ("gameId", str(UUID(int=998))),
        ("tenantId", str(UUID(int=997))),
    ]:
        raw = copy.deepcopy(original)
        raw["content"]["scope"][key] = new
        raw["ref"]["digest"] = source_fingerprint(raw["content"])
        with pytest.raises(api.NonplaySourceUnavailable):
            api.checked_checkpoint(
                raw,
                tenant=original["content"]["scope"]["tenantId"],
                game=original["content"]["scope"]["gameId"],
                generation=original["content"]["scope"]["generation"],
                d3=int(original["content"]["d3"]),
            )


def _issued_prefix(r, monkeypatch):
    """issuerの独立原値を実型handleへ置くpure完成境界。DB発行の証拠ではない。"""
    from pitchlog.domainrt.first_ball_projection import _canonical_json
    from pitchlog.domainrt.lineup_play_prefix_continuation import NonplaySource

    raw = {
        "formatVersion": "nonplay-prefix-source-v1",
        "checkpoint": r.cp.model_dump(mode="json", by_alias=True),
        "activeStack": [],
    }
    source = NonplaySource.model_validate_json(json.dumps(raw))
    view = api.NonplayCheckpointView(source.checkpoint, 1, 1)
    roster = SimpleNamespace(model_dump=lambda **_: {"saved": "roster"})
    prefix = object.__new__(api.ConfirmedNonplayNormalPrefix)
    for k, v in dict(
        checkpoint=view,
        source=source,
        next_play_number=int(source.checkpoint.content.next_physical_play_number),
        roster=roster,
        previous_payload=None,
    ).items():
        object.__setattr__(prefix, k, v)
    state = SimpleNamespace(handle=r.handle, prefix=prefix)
    entry = (
        prefix,
        state,
        _canonical_json(raw),
        _canonical_json({"saved": "roster"}),
        api._owner(r.handle),
        _canonical_json({"generation": 1, "epoch": 1, "next": prefix.next_play_number}),
        source,
        view,
        roster,
    )
    monkeypatch.setitem(api._PREFIX_READS, r.key, entry)
    return state, prefix


def test_issued_prefix_live_then_finally_expired(read_rig, monkeypatch):
    """同scopeだけ有効で、最後のrelease後は同文字列/同参照でも失効する。"""
    state, _ = _issued_prefix(read_rig, monkeypatch)
    api._assert_nonplay_normal_prefix(state)
    api._release_nonplay_normal_prefix(read_rig.handle)
    with pytest.raises(api.NonplaySourceUnavailable):
        api._assert_nonplay_normal_prefix(state)


@pytest.mark.parametrize(
    "mutation",
    [
        "clone",
        "source-clone",
        "view-clone",
        "roster-clone",
        "ref-follow",
        "generation-bool",
        "epoch-bool",
        "next-float",
        "other-state",
        "stale-tx",
    ],
)
def test_issuer_anchor_independent_of_mutable_receipt_target(
    read_rig, monkeypatch, mutation
):
    """state/rawを追随させてもissuer側identity/原値を置換できない。"""
    state, prefix = _issued_prefix(read_rig, monkeypatch)
    if mutation == "clone":
        clone = object.__new__(api.ConfirmedNonplayNormalPrefix)
        for k in (
            "checkpoint",
            "source",
            "next_play_number",
            "roster",
            "previous_payload",
        ):
            object.__setattr__(clone, k, getattr(prefix, k))
        state.prefix = clone
    elif mutation == "source-clone":
        object.__setattr__(prefix, "source", prefix.source.model_copy(deep=True))
    elif mutation == "view-clone":
        object.__setattr__(prefix, "checkpoint", copy.copy(prefix.checkpoint))
    elif mutation == "roster-clone":
        object.__setattr__(prefix, "roster", copy.copy(prefix.roster))
    elif mutation == "ref-follow":
        raw = prefix.source.model_dump(mode="json", by_alias=True)
        raw["checkpoint"]["content"]["historyVersion"] = "99"
        raw["checkpoint"]["ref"]["digest"] = source_fingerprint(
            raw["checkpoint"]["content"]
        )
        object.__setattr__(
            prefix, "source", type(prefix.source).model_validate_json(json.dumps(raw))
        )
    elif mutation == "generation-bool":
        object.__setattr__(prefix.checkpoint, "internal_generation", True)
    elif mutation == "epoch-bool":
        object.__setattr__(prefix.checkpoint, "recovery_generation", True)
    elif mutation == "next-float":
        object.__setattr__(prefix, "next_play_number", float(prefix.next_play_number))
    elif mutation == "other-state":
        state = copy.copy(state)
    else:
        read_rig.session.get_transaction = lambda: SimpleNamespace(is_active=True)
    with pytest.raises(api.NonplaySourceUnavailable):
        api._assert_nonplay_normal_prefix(state)


@pytest.mark.parametrize("desired", [2025, 3024, 5000])
def test_actual_existing_allocator_append_branch_is_used_without_fixed_gap(
    read_rig, monkeypatch, desired
):
    """実固定関数応答doubleから既allocatorを動かし、+1000以外の正常appendも保持。"""
    from pitchlog.db.sync_protocol.models import OperationEvent
    from pitchlog.repositories.ordinary_order import OrdinaryOrderSummaryToken

    r = read_rig
    game = r.cp.content.scope.game_id
    calls = []
    tail = dict.fromkeys(OperationEvent.__table__.c.keys())
    tail.update(
        tenant_id=str(r.handle._bound_tenant_id),
        game_id=game,
        generation=1,
        d1=2,
        d2=2024,
        id=str(UUID(int=20)),
        d5=str(UUID(int=21)),
        ledger_kind="accepted",
        event_kind="play_input",
        is_tombstone=False,
        migration_unverified=False,
        payload={},
    )

    def run(handle, token):
        assert handle is r.handle and type(token) is OrdinaryOrderSummaryToken
        calls.append(token)
        return TenantOperationResult(
            (
                (
                    json.dumps(
                        {"tail": tail, "duplicate": False, "recovery_generation": 1}
                    ),
                ),
            )
        )

    monkeypatch.setattr(tx._TenantTransaction, "run_function", run)
    monkeypatch.setattr(
        tx._TenantTransaction,
        "run",
        lambda *a: pytest.fail("append資格で再採番DMLへ入った"),
    )
    event = SimpleNamespace(game_id=game, v6=desired)
    proposal = SimpleNamespace(source_position=SimpleNamespace(d2=str(desired)))
    assert api._read_nonplay_append_d2(r.handle, event, proposal, epoch=1) == desired
    assert len(calls) == 2


@pytest.mark.parametrize("desired", [2024, 2023, -1, True, 2025.0])
def test_nonappend_or_wrong_type_never_enters_legacy_reorder(
    read_rig, monkeypatch, desired
):
    """過去位置/型混同は既fallbackを呼ばず読み取りだけで閉じる。"""
    from pitchlog.repositories.ordinary_order import OrdinaryOrderSummaryToken

    r = read_rig
    game = r.cp.content.scope.game_id
    calls = []

    def run(handle, token):
        assert type(token) is OrdinaryOrderSummaryToken
        calls.append(token)
        return TenantOperationResult(
            (
                (
                    json.dumps(
                        {
                            "tail": {
                                "tenant_id": str(r.handle._bound_tenant_id),
                                "game_id": game,
                                "d2": 2024,
                            },
                            "duplicate": False,
                            "recovery_generation": 1,
                        }
                    ),
                ),
            )
        )

    monkeypatch.setattr(tx._TenantTransaction, "run_function", run)
    monkeypatch.setattr(
        tx._TenantTransaction,
        "run",
        lambda *a: pytest.fail("不正appendで再採番DMLへ入った"),
    )
    with pytest.raises(api.NonplaySourceUnavailable):
        api._read_nonplay_append_d2(
            r.handle,
            SimpleNamespace(game_id=game, v6=desired),
            SimpleNamespace(source_position=SimpleNamespace(d2=str(desired))),
            epoch=1,
        )
    assert len(calls) == 1
