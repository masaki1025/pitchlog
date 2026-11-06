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
from test_nonplay_prefix import CASES

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


def test_saved_history_difference_omission_survives_source_roundtrip():
    """旧v3履歴の省略差分を明示nullへ補完しない。"""
    from pitchlog.domainrt.lineup_play_prefix_continuation import NonplaySource

    raw = CASES["steps"][1]["source"]
    assert len(raw["activeStack"]) == 1
    difference = raw["activeStack"][0]["historyEntry"]["difference"]
    assert "battingOrderBySide" not in difference
    parsed = NonplaySource.model_validate_json(json.dumps(raw))
    assert api._same(
        raw, parsed.model_dump(mode="json", by_alias=True, exclude_unset=True)
    )
    assert not api._same(raw, parsed.model_dump(mode="json", by_alias=True))


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


@pytest.fixture
def bootstrap_rig(monkeypatch):
    """保存行だけを明示doubleにする。writer/getter/型/frame/mapperは製品を使う。"""
    from test_nonplay_prefix import rig as original_rig

    yield from getattr(original_rig, "__wrapped__")(monkeypatch)


def _bootstrap_read_setup(
    r, monkeypatch, *, count=2, mutation=None, wire_generation=None
):
    """既前置手例を再利用し、>100はページ制御だけの合成原本と明示する。"""
    from test_nonplay_prefix import legacy_profile_fixture, saved_item

    from pitchlog.repositories.play_prefix import read_lineup_prefix_document

    artifact = r.value["checkpoint"]["content"]["executionArtifactSha256"]
    if count != 2:
        # これはDBの成功/野球計算の期待ではなく、同一型contextのページ境界fixture。
        template = copy.deepcopy(r.records[0])
        context = copy.deepcopy(template["frame"]["afterContext"])
        records = []
        for number in range(count, 0, -1):
            record = copy.deepcopy(template)
            frame = record["frame"]
            frame["beforeContext"] = copy.deepcopy(context)
            frame["afterContext"] = copy.deepcopy(context)
            src = frame["play"]["source"]
            src.update(
                eventId=str(UUID(int=10000 + number)),
                d5=str(UUID(int=20000 + number)),
                d1=str(number),
                fingerprint="wire-v1:" + source_fingerprint({"page-case": number}),
            )
            frame["play"].update(
                playId=str(UUID(int=30000 + number)),
                d2=str(number * 1024),
                physicalPlayNumber=str(number),
            )
            record["cursor"] = [1, number, src["eventId"]]
            records.append(record)
        r.records[:] = records
        r.value["activeStack"] = [record["frame"] for record in records]
        c = r.value["checkpoint"]["content"]
        c.update(d3=str(count), activeDepth=str(count), historyVersion=str(count))
        r.actual_next_physical = str(count + 1)
    if wire_generation is not None:
        r.value["checkpoint"]["content"]["scope"]["generation"] = wire_generation
        for record in r.records:
            record["frame"]["play"]["source"]["generation"] = wire_generation
        r.chain = [wire_generation]
    raw, row = legacy_profile_fixture(r, monkeypatch, artifact)
    doc = read_lineup_prefix_document(json.dumps(raw))
    original = tx._TenantTransaction.run_function
    calls = []
    items = []
    for record in r.records:
        numeric_record = copy.deepcopy(record)
        numeric_record["frame"]["play"]["source"]["generation"] = "1"
        saved = saved_item(numeric_record, r)
        saved["frame"] = record["frame"]
        saved["admission"]["wire_d4"] = record["frame"]["play"]["source"]["generation"]
        items.append(
            {
                "kind": saved["kind"],
                "cursor": saved["cursor"],
                "frame": saved["frame"],
                "event": saved["event"],
                "fingerprint": saved["ledger"]["source_fingerprint"],
                "wireD4": saved["admission"]["wire_d4"],
                "physical": saved["physical"],
            }
        )

    def run(handle, token):
        if type(token) is not NonplayActiveHistoryReadToken:
            return original(handle, token)
        assert handle is r.handle and token.page_size == 100
        calls.append(token)
        point = (token.after_order, token.after_d1, str(token.after_id))
        selected = [
            item for item in items if point[0] == 0 or tuple(item["cursor"]) < point
        ][:101]
        packet: dict[str, Any] = copy.deepcopy(
            {
                "checkpoint": raw,
                "total": count,
                "items": selected,
                "storage": {
                    "row": row,
                    "nextPhysicalPlayNumber": r.actual_next_physical,
                },
                "generationChain": r.chain,
            }
        )
        if mutation == "missing-page" and len(calls) == 1:
            packet["items"] = packet["items"][:30]
        elif mutation == "anchor-drift" and len(calls) == 2:
            packet["checkpoint"]["revision"] = "999"
        elif mutation == "storage-drift" and len(calls) == 2:
            packet["storage"]["row"]["saved_at"] = "2026-11-07T00:00:00+00:00"
        elif mutation == "ledger":
            packet["items"][0]["fingerprint"] = "wire-v1:" + "a" * 64
        elif mutation == "raw-wire":
            packet["items"][0]["event"]["state_diff"] = {}
        elif mutation == "tenant":
            packet["items"][0]["event"]["tenant_id"] = str(UUID(int=999))
        elif mutation == "profile":
            packet["items"][0]["kind"] = "unknown"
        elif mutation == "generation-chain":
            packet["generationChain"] = ["unknown-generation"]
        elif mutation == "total-bool":
            packet["total"] = True
        return TenantOperationResult(((json.dumps(packet),),))

    monkeypatch.setattr(tx._TenantTransaction, "run_function", run)
    return SimpleNamespace(
        doc=doc, row=row, calls=calls, artifact=artifact, items=items
    )


def test_bootstrap_get_ref_equals_actual_writer_mapper(bootstrap_rig, monkeypatch):
    """初回GETのexpectedCheckpointは、同writer原本readerが生成するNP refと一致。"""
    from pitchlog.repositories import nonplay_prefix as writer

    r = bootstrap_rig
    setup = _bootstrap_read_setup(r, monkeypatch)
    cp, values = api._read_legacy_undo_source(
        r.handle, setup.doc, setup.row, setup.artifact
    )
    with writer.read_confirmed_nonplay_prefix(
        r.handle, r.event, r.source, artifact_sha256=setup.artifact
    ) as prefix:
        actual, _ = writer._read_prefix(prefix, r.handle, r.source, r.event)
    assert cp.model_dump(mode="json", by_alias=True) == actual["checkpoint"]
    assert [frame for _, frame in values] == actual["activeStack"]
    assert cp.ref.digest != setup.doc.content_digest
    assert len(setup.calls) == 1
    assert r.handle._state_key not in api._PREFIX_READS


def test_bootstrap_over_100_qualifies_whole_stack_with_bounded_pages(
    bootstrap_rig, monkeypatch
):
    """通常1試合の205原本を100+1ずつ読み、100件上限で不適格にしない。"""
    r = bootstrap_rig
    setup = _bootstrap_read_setup(r, monkeypatch, count=205)
    cp, values = api._read_legacy_undo_source(
        r.handle, setup.doc, setup.row, setup.artifact
    )
    assert len(values) == 205 and cp.content.active_depth == "205"
    assert [t.after_d1 for t in setup.calls] == [0, 106, 6]
    assert all(t.page_size == 100 for t in setup.calls)
    assert len({frame["play"]["source"]["eventId"] for _, frame in values}) == 205


@pytest.mark.parametrize(
    "mutation",
    [
        "missing-page",
        "anchor-drift",
        "storage-drift",
        "ledger",
        "raw-wire",
        "tenant",
        "profile",
        "generation-chain",
        "total-bool",
    ],
)
def test_bootstrap_incomplete_changed_or_unqualified_page_is_not_a_source(
    bootstrap_rig, monkeypatch, mutation
):
    """一部ページ・別anchor・原wire/受理指紋不一致を完全Sourceへ昇格しない。"""
    r = bootstrap_rig
    setup = _bootstrap_read_setup(r, monkeypatch, count=205, mutation=mutation)
    with pytest.raises(api.NonplaySourceUnavailable):
        api._read_legacy_undo_source(r.handle, setup.doc, setup.row, setup.artifact)
    assert r.handle._state_key not in api._PREFIX_READS


def _bootstrap_service_setup(r, monkeypatch, *, count):
    """scope/headメタデータ境界はdouble、新service/fullpage/既DTOは実物。"""
    from dataclasses import replace

    from test_api_started_game import _bundle_for

    from pitchlog.repositories import ordinary_prefix_read as ordinary
    from pitchlog.repositories.started_read import StartedGameView, read_started_game
    from pitchlog.sync.d4_reference import encode_d4_reference

    wire = encode_d4_reference(
        r.handle._bound_tenant_id,
        UUID(r.value["checkpoint"]["content"]["scope"]["gameId"]),
        1,
    )
    setup = _bootstrap_read_setup(r, monkeypatch, count=count, wire_generation=wire)
    doc = setup.doc
    with pytest.MonkeyPatch.context() as local:
        bundle = _bundle_for(r.handle._bound_tenant_id, local)
        initial = read_started_game(bundle.handle, bundle.game_id)
    assert type(initial) is StartedGameView
    metadata = replace(
        initial, game_id=UUID(doc.prefix_ref.game_id), current_d4=doc.wire_d4
    )
    snapshot = {
        "row": setup.row,
        "generation": 1,
        "epoch": 1,
        "d3": count,
        "d4": doc.wire_d4,
        "tail": {"d2": count * 1024},
        "game": {},
    }
    monkeypatch.setattr(api, "_read_undo_snapshot", lambda *a: snapshot)
    monkeypatch.setattr(api, "_legacy_undo_metadata", lambda *a: metadata)
    monkeypatch.setattr(
        ordinary,
        "read_lineup_prefix",
        lambda *a, **kw: pytest.fail("legacyの旧公開history-page経路を流用しました"),
    )
    return setup, metadata


def test_bootstrap_service_returns_only_requested_pages_with_same_writer_checkpoint(
    bootstrap_rig, monkeypatch
):
    """内部全205資格と公開100/100/5を区別し、全pageだけで完全Sourceを組める。"""
    from pitchlog.repositories.nonplay_prefix import _check_source

    r = bootstrap_rig
    setup, metadata = _bootstrap_service_setup(r, monkeypatch, count=205)
    game = UUID(setup.doc.prefix_ref.game_id)
    cursor = None
    items = []
    refs = []
    sizes = []
    for _ in range(3):
        view = api.read_undo_prefix(r.handle, game, limit=100, cursor=cursor)
        assert view.metadata is metadata
        cp = view.projection["checkpoint"]
        refs.append(cp.ref)
        page = view.projection["page"]
        sizes.append(len(page["items"]))
        items.extend(page["items"])
        cursor = page["next_cursor"]
    assert sizes == [100, 100, 5] and cursor is None
    assert refs[0] == refs[1] == refs[2]
    source = {
        "formatVersion": "nonplay-prefix-source-v1",
        "checkpoint": cp.model_dump(mode="json", by_alias=True),
        "activeStack": items,
    }
    assert _check_source(source) == source
    assert len(setup.calls) == 9  # 各HTTP readの内部pageも同100+1 bounded。
    assert r.handle._state_key not in api._PREFIX_READS


def test_bootstrap_service_rejects_public_cursor_from_another_checkpoint(
    bootstrap_rig, monkeypatch
):
    """cursorを別NP refへ差替えても数学提案や保存資格へ転用しない。"""
    r = bootstrap_rig
    setup, _ = _bootstrap_service_setup(r, monkeypatch, count=2)
    game = UUID(setup.doc.prefix_ref.game_id)
    first = api.read_undo_prefix(r.handle, game, limit=1)
    cursor = first.projection["page"]["next_cursor"]
    import base64

    packet = json.loads(base64.urlsafe_b64decode(cursor + "=" * ((-len(cursor)) % 4)))
    packet["anchor"]["checkpoint"]["digest"] = "a" * 64
    bad = (
        base64.urlsafe_b64encode(api._canonical_json(packet).encode())
        .decode()
        .rstrip("=")
    )
    with pytest.raises(api.NonplaySourceUnavailable):
        api.read_undo_prefix(r.handle, game, limit=1, cursor=bad)


@pytest.mark.anyio
async def test_bootstrap_http_legacy_returns_np_checkpoint_and_bounded_pages(
    bootstrap_rig, monkeypatch
):
    """認証/SQLは明示double、HTTP/router/実reader/同mapper/DTOの接続を通す。"""
    from contextlib import contextmanager

    import fastapi.dependencies.utils
    import fastapi.routing
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from test_roster_boundary import _metadata_headers

    from pitchlog.api import tenant_access
    from pitchlog.api.routers import started_games

    r = bootstrap_rig

    async def inline(function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(fastapi.routing, "run_in_threadpool", inline)
    monkeypatch.setattr(fastapi.dependencies.utils, "run_in_threadpool", inline)
    monkeypatch.setattr(tenant_access, "run_in_threadpool", inline)
    monkeypatch.setattr(
        tenant_access, "require_tenant_access", lambda *a, **kw: r.handle._context
    )
    setup, _ = _bootstrap_service_setup(r, monkeypatch, count=2)
    app = FastAPI()
    app.include_router(started_games.router)
    app.dependency_overrides[started_games.require_tenant_access] = lambda: (
        r.handle._context
    )

    @contextmanager
    def scope(context):
        assert context is r.handle._context
        yield r.handle

    monkeypatch.setattr(started_games, "tenant_transaction_scope", scope)
    game = setup.doc.prefix_ref.game_id
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test"
    ) as client:
        client.cookies.set("__Host-pitchlog_token", "explicit-auth-double")
        client.headers.update(_metadata_headers(r.handle._bound_tenant_id))
        response = await client.get(
            f"/games/{game}/started?projection=undo-prefix-v1&limit=1"
        )
        assert response.status_code == 200, response.text
        first = response.json()
        cursor = first["page"]["next_cursor"]
        assert type(cursor) is str
        response = await client.get(
            f"/games/{game}/started",
            params={"projection": "undo-prefix-v1", "limit": 1, "cursor": cursor},
        )
        assert response.status_code == 200, response.text
        second = response.json()
    assert first["read_kind"] == "nonplay-prefix"
    assert first["profile"] == "nonplay-prefix-read-v1"
    assert first["checkpoint"] == second["checkpoint"]
    assert first["checkpoint"]["ref"]["digest"] != setup.doc.content_digest
    assert len(first["page"]["items"]) == len(second["page"]["items"]) == 1
    assert second["page"]["next_cursor"] is None
    assert first["checkpoint"]["content"]["activeDepth"] == "2"
    raw = json.dumps((first, second))
    assert all(key not in raw for key in ("binding_nonce", "lease_id", "admission"))


def test_zero_cursor_uses_real_public_function_dispatcher():
    """先頭cursor0を偽handleでなく実token/registry/dispatcher全体へ通す。"""
    from pitchlog.repositories.function_operations import prepare_function_operation
    from pitchlog.repositories.operation_registry import FUNCTION_OPERATION_REGISTRY

    token = NonplayActiveHistoryReadToken(
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
        page_size=100,
    )
    _, parameters = prepare_function_operation(
        token,
        UUID(int=3),
        FUNCTION_OPERATION_REGISTRY,
    )
    assert parameters["after_order"] == 0
    assert parameters["after_d1"] == 0
    assert parameters["tenant_id"] == UUID(int=3)


@pytest.mark.parametrize(
    "field", ["generation", "revision", "epoch", "d3", "logical_version", "page_size"]
)
def test_real_dispatcher_keeps_non_cursor_zero_closed(field):
    """constructor迂回の改変でも、cursor以外の0を新たに通さない。"""
    from pitchlog.repositories.function_operations import (
        FunctionOperationError,
        prepare_function_operation,
    )
    from pitchlog.repositories.operation_registry import FUNCTION_OPERATION_REGISTRY

    token = NonplayActiveHistoryReadToken(
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
        page_size=100,
    )
    object.__setattr__(token, field, 0)
    with pytest.raises(FunctionOperationError):
        prepare_function_operation(token, UUID(int=3), FUNCTION_OPERATION_REGISTRY)


@pytest.mark.parametrize("bad", [-1, True, 0.0, 2**63])
def test_real_dispatcher_keeps_invalid_cursor_closed(bad):
    """正規tokenの私有値を改変しても型/負値/上限を拒否する。"""
    from pitchlog.repositories.function_operations import (
        FunctionOperationError,
        prepare_function_operation,
    )
    from pitchlog.repositories.operation_registry import FUNCTION_OPERATION_REGISTRY

    token = NonplayActiveHistoryReadToken(
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
        page_size=100,
    )
    object.__setattr__(token, "after_order", bad)
    with pytest.raises(FunctionOperationError):
        prepare_function_operation(token, UUID(int=3), FUNCTION_OPERATION_REGISTRY)
