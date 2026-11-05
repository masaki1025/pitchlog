"""原本readerの有限対向。issuer/Session/DB応答は明示したpure double。"""

from __future__ import annotations

import copy
import json
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import pytest
from test_authz_tenant_context import make_tenant_context

from pitchlog.domainrt.first_ball_projection import _canonical_json
from pitchlog.repositories import nonplay_prefix as api
from pitchlog.repositories import transaction as tx
from pitchlog.repositories.tokens import TenantOperationResult
from pitchlog.sync.idempotency import _json_value, event_source, source_fingerprint
from pitchlog.sync.model import SyncEvent
from pitchlog.sync.ports import _issue_port_writer
from pitchlog.sync.source_binding import _E1CoreSource
from pitchlog.sync.wire_fingerprint import freeze_wire_event, wire_event_fingerprint

ROOT = Path(__file__).resolve().parents[2]
CASES = json.loads(
    (
        ROOT / "contracts/state-transition/nonplay_prefix_bridge_cases_v1.json"
    ).read_text()
)


def wire_event(raw):
    """HTTP保存済みJSONから同一意味の実DTOだけを作る。"""
    return SyncEvent(
        raw["d5"],
        raw["game_id"],
        raw["d1"],
        raw["d4"],
        raw["event_kind"],
        v7=raw["payload"],
        v10=raw["target_reference"],
    )


def fixture_values(step=2):
    """数学goldenを採取せず、前置手例に指紋読取の対照だけを追加する。"""
    value = copy.deepcopy(CASES["steps"][step]["source"])
    records = []
    for frame in value["activeStack"]:
        number = int(frame["play"]["source"]["d1"])
        original = copy.deepcopy(CASES["steps"][number]["event"])
        original["state_diff"] = original["state_diff"]["difference"]
        fingerprint = wire_event_fingerprint(freeze_wire_event(original))
        frame["play"]["source"]["fingerprint"] = fingerprint
        record = {
            "frame": frame,
            "cursor": [1, number, frame["play"]["source"]["eventId"]],
            "original": original,
            "storedFingerprint": fingerprint,
            "physical": {"all_physical_fixture_fields": "same"},
            "expectedPhysical": {"all_physical_fixture_fields": "same"},
        }
        records.append(record)
    content = value["checkpoint"]["content"]
    head = value["activeStack"][0]["play"]
    content["activeHead"] = copy.deepcopy(head)
    content["d1Head"]["source"] = copy.deepcopy(head["source"])
    content["projectionHead"]["source"] = copy.deepcopy(head["source"])
    value["checkpoint"]["ref"]["digest"] = source_fingerprint(content)
    raw = copy.deepcopy(CASES["undoEvents"][0])
    raw["payload"]["expectedCheckpoint"] = copy.deepcopy(value["checkpoint"]["ref"])
    return value, raw, records


@pytest.fixture
def rig(monkeypatch):
    """実型handle/一回getterを実行し、E1/DBの成功とは区別する。"""
    value, raw, records = fixture_values()
    key = object()
    context = make_tenant_context(
        UUID(value["checkpoint"]["content"]["scope"]["tenantId"])
    )
    top = SimpleNamespace(is_active=True)
    session = SimpleNamespace(
        get_transaction=lambda: top, in_nested_transaction=lambda: False
    )
    runtime = (session, ExitStack())
    monkeypatch.setitem(tx._TRANSACTION_RUNTIMES, key, runtime)
    handle = tx._TenantTransaction(
        context,
        key,
        context.tenant_id,
        context._integrity_proof,
        tx._HANDLE_CREATION_TOKEN,
    )
    event = wire_event(raw)
    lease = SimpleNamespace(
        attempt_id=UUID(int=41),
        phase_id=UUID(int=42),
        nonce=b"x" * 32,
        device_id=UUID(int=43),
        game_id=UUID(event.game_id),
    )
    bound = SimpleNamespace(
        _handle=handle, _lease=lease, _phase_snapshot="pure-fixture-not-real-binding"
    )
    source = cast(Any, object.__new__(_E1CoreSource))
    source.scope, source.context, source.event, source.bound = (
        handle,
        context,
        event,
        bound,
    )
    source.request, source.phase, source.binding, source.write_started = (
        object(),
        object(),
        object(),
        False,
    )
    view = SimpleNamespace(
        origin="e1",
        wire_event=freeze_wire_event(
            json.loads(_canonical_json(_json_value(event_source(event))))
        ),
        event_fingerprint=wire_event_fingerprint(
            freeze_wire_event(
                json.loads(_canonical_json(_json_value(event_source(event))))
            )
        ),
    )

    def source_read(actual, actual_handle, actual_event):
        assert (
            actual is source
            and actual_handle is handle
            and actual_event is source.event
        )
        return view

    monkeypatch.setattr(_E1CoreSource, "read", source_read)
    calls = []
    r = SimpleNamespace(
        handle=handle,
        event=event,
        source=source,
        value=value,
        raw=raw,
        records=records,
        calls=calls,
        top=top,
        runtime=runtime,
        view=view,
        lease=lease,
        response_override=None,
        chain=["1"],
        actual_next_physical="3",
        failure=None,
    )

    def run_function(actual, operation):
        assert actual is handle
        qualified = api._qualified_nonplay_call(actual, operation)
        assert qualified.operation is operation
        assert qualified.parameters["binding_nonce"] == lease.nonce
        calls.append(operation)
        if r.failure is not None:
            raise r.failure
        if type(operation) is api._LockNonplayCheckpoint:
            result = {
                "checkpoint": r.value["checkpoint"],
                "storage": {
                    "row": {"real_row_fixture": "not-a-DB-proof"},
                    "nextPhysicalPlayNumber": r.actual_next_physical,
                },
                "generationChain": r.chain,
            }
            return TenantOperationResult(((_canonical_json(result),),))
        if type(operation) is api._ReadNonplayHistoryPage:
            request = json.loads(operation.request_json)
            return TenantOperationResult(
                tuple((_canonical_json(item),) for item in r.records)
                if request["cursor"] is None
                else ()
            )
        return TenantOperationResult(
            r.response_override if r.response_override is not None else ((True,),)
        )

    monkeypatch.setattr(tx._TenantTransaction, "run_function", run_function)
    r.writer = _issue_port_writer(handle.run)
    with tx._sync_apply_active():
        yield r
    r.writer._close()
    assert not api._CALLS and not api._READS


def test_source_is_actual_issued_identity_and_expires(rig):
    """純DB応答を通した同scope identity寿命と全値保持を検査する。"""
    with api.read_confirmed_nonplay_prefix(
        rig.handle,
        rig.event,
        rig.source,
        artifact_sha256=rig.raw["payload"]["artifactSha256"],
    ) as prefix:
        actual, _ = api._read_prefix(prefix, rig.handle, rig.source, rig.event)
        assert actual == rig.value
        with pytest.raises(api.NonplaySourceUnavailable):
            api._read_prefix(
                object.__new__(api.ConfirmedNonplayPrefix),
                rig.handle,
                rig.source,
                rig.event,
            )
    with pytest.raises(api.NonplaySourceUnavailable):
        api._read_prefix(prefix, rig.handle, rig.source, rig.event)


@pytest.mark.parametrize(
    "fault",
    [
        "missing-tail",
        "reverse",
        "physical",
        "fingerprint",
        "original-flag",
        "scope",
        "repeated-cursor",
    ],
)
def test_source_refuses_missing_or_forged_original(rig, fault):
    """実shapeが揃っていても原本/全物理/完全履歴を補修しない。"""
    if fault == "missing-tail":
        rig.records.pop()
    elif fault == "reverse":
        rig.records.reverse()
    elif fault == "physical":
        rig.records[0]["physical"]["all_physical_fixture_fields"] = "changed"
    elif fault == "fingerprint":
        rig.records[0]["storedFingerprint"] = "wire-v1:" + "0" * 64
    elif fault == "original-flag":
        rig.records[0]["original"]["state_diff"]["statFlags"]["安打"] = True
    elif fault == "scope":
        rig.value["checkpoint"]["content"]["scope"]["tenantId"] = str(UUID(int=999))
    else:
        rig.records[1]["cursor"] = rig.records[0]["cursor"]
    with pytest.raises((api.NonplaySourceUnavailable, ValueError)):
        with api.read_confirmed_nonplay_prefix(
            rig.handle,
            rig.event,
            rig.source,
            artifact_sha256=rig.raw["payload"]["artifactSha256"],
        ):
            pytest.fail("偽原本が成功しました")


def test_direct_sql_and_forged_write_loan_are_rejected(rig):
    """SQL直入口/値tokenだけから資格を発行しない。"""
    token = api._ReadNonplayHistoryPage("{}")
    with pytest.raises(api.NonplaySourceUnavailable):
        api._qualified_nonplay_call(rig.handle, token)
    with pytest.raises(RuntimeError):
        with api._call_scope(
            rig.handle, rig.source, rig.event, api._PrepareNonplayUndo("{}")
        ):
            pytest.fail("frameなしwrite資格が成立しました")


def test_getter_is_exact_token_and_one_use(rig):
    """clone/別token/二度consumeをSQL前で拒否する。"""
    token = api._ReadNonplayHistoryPage("{}")
    with api._call_scope(rig.handle, rig.source, rig.event, token):
        with pytest.raises(api.NonplaySourceUnavailable):
            api._qualified_nonplay_call(rig.handle, api._ReadNonplayHistoryPage("{}"))
        qualified = api._qualified_nonplay_call(rig.handle, token)
        assert qualified.operation is token
        with pytest.raises(api.NonplaySourceUnavailable):
            api._qualified_nonplay_call(rig.handle, token)


def test_historical_hook_evidence_is_only_same_live_page_item(rig, monkeypatch):
    """歴史原本は実page区間だけへ貸し、raw JSON自由供給を拒否する。"""
    from dataclasses import dataclass

    from pitchlog.repositories import recorded_snapshot

    old = rig.records[1]
    old["original"]["event_kind"] = "1"
    fingerprint = wire_event_fingerprint(freeze_wire_event(old["original"]))
    old["storedFingerprint"] = fingerprint
    old["frame"]["play"]["source"]["fingerprint"] = fingerprint
    src = old["frame"]["play"]["source"]
    item = saved_item(old, rig, first=True)
    old["physical"] = {"play_row": item["play"], "play_runners": item["runners"]}
    old["expectedPhysical"] = copy.deepcopy(old["physical"])
    rig.records[1] = item
    kwargs = {"source_event_id": UUID(src["eventId"]), "generation": 1, "d1": 1}
    with pytest.raises(api.NonplaySourceUnavailable):
        api._read_historical_first_ball_evidence(
            rig.handle, rig.event, rig.source, **kwargs
        )
    with pytest.raises(api.NonplaySourceUnavailable):
        api._legacy_first_ball_item(
            rig.handle,
            rig.event,
            rig.source,
            item,
            rig.handle._writer_lifetime(),
            rig.runtime,
        )

    @dataclass(frozen=True, slots=True)
    class HistoricalFirstBallFrame:
        source_event_id: UUID
        generation: int
        d1: int
        frame_json: str
        semantic_event_json: str
        stored_fingerprint: str
        physical_json: str
        expected_physical_json: str

    def read(handle, event, source, **reference):
        assert reference == kwargs
        with pytest.raises(api.NonplaySourceUnavailable):
            api._read_historical_first_ball_evidence(
                handle, event, source, **{**reference, "generation": 2}
            )
        evidence = api._read_historical_first_ball_evidence(
            handle, event, source, **reference
        )
        assert json.loads(evidence.ledger_json)["source_fingerprint"] == fingerprint
        with pytest.raises(api.NonplaySourceUnavailable):
            api._read_historical_first_ball_evidence(handle, event, source, **reference)
        return HistoricalFirstBallFrame(
            **reference,
            frame_json=_canonical_json(old["frame"]),
            semantic_event_json=_canonical_json(
                api._semantic_event(item["event"], item["admission"])
            ),
            stored_fingerprint=fingerprint,
            physical_json=_canonical_json(old["physical"]),
            expected_physical_json=_canonical_json(old["expectedPhysical"]),
        )

    monkeypatch.setattr(
        recorded_snapshot,
        "HistoricalFirstBallFrame",
        HistoricalFirstBallFrame,
        raising=False,
    )
    monkeypatch.setattr(
        recorded_snapshot, "_read_nonplay_first_ball_frame", read, raising=False
    )
    with api.read_confirmed_nonplay_prefix(
        rig.handle,
        rig.event,
        rig.source,
        artifact_sha256=rig.raw["payload"]["artifactSha256"],
    ) as prefix:
        actual, _ = api._read_prefix(prefix, rig.handle, rig.source, rig.event)
        assert actual == rig.value
    assert not api._HISTORICAL_LOANS and not api._PAGE_ITEMS
    with pytest.raises(api.NonplaySourceUnavailable):
        api._read_historical_first_ball_evidence(
            rig.handle, rig.event, rig.source, **kwargs
        )


def test_unprovided_historical_hook_is_not_a_success(rig, monkeypatch):
    """frame欠測を推測で初期状態へ補完しない。"""
    from pitchlog.repositories import recorded_snapshot

    monkeypatch.setattr(
        recorded_snapshot, "_read_nonplay_first_ball_frame", None, raising=False
    )
    monkeypatch.setattr(
        recorded_snapshot, "HistoricalFirstBallFrame", None, raising=False
    )
    rig.records[1] = saved_item(rig.records[1], rig, first=True)
    with pytest.raises(api.NonplaySourceUnavailable, match="未供給"):
        with api.read_confirmed_nonplay_prefix(
            rig.handle,
            rig.event,
            rig.source,
            artifact_sha256=rig.raw["payload"]["artifactSha256"],
        ):
            pytest.fail("未供給bootstrapが成功しました")


@pytest.mark.parametrize("nonce", [b"y" * 32, bytearray(b"x" * 32), True])
def test_qualified_call_rechecks_nonce_value_and_exact_type(rig, nonce):
    """値同値bytearrayも実nonceのbytes資格へ強制変換しない。"""
    token = api._ReadNonplayHistoryPage("{}")
    with pytest.raises(api.NonplaySourceUnavailable):
        with api._call_scope(rig.handle, rig.source, rig.event, token):
            rig.lease.nonce = nonce
            api._qualified_nonplay_call(rig.handle, token)


@pytest.mark.parametrize("use_raw_hash", [False, True])
def test_legacy_fingerprint_keeps_actual_P2_algorithm(rig, use_raw_hash):
    """旧plain64をraw単独hashへ付替えず、既P2原典式を再利用する。"""
    from pitchlog.sync.idempotency import operation_fingerprint

    for record in rig.records:
        original = record["original"]
        original["d2"] = int(original["d2"])
        historical = SyncEvent(
            original["d5"],
            original["game_id"],
            original["d1"],
            original["d4"],
            original["event_kind"],
            v6=original["d2"],
            v7=original["payload"],
            v8=original["state_diff"],
        )
        fingerprint = (
            source_fingerprint(original)
            if use_raw_hash
            else operation_fingerprint(historical, "P2", None)
        )
        record["storedFingerprint"] = fingerprint
        record["frame"]["play"]["source"]["fingerprint"] = fingerprint
    cp = rig.value["checkpoint"]
    head = rig.value["activeStack"][0]["play"]
    cp["content"]["activeHead"] = copy.deepcopy(head)
    cp["content"]["d1Head"]["source"] = copy.deepcopy(head["source"])
    cp["content"]["projectionHead"]["source"] = copy.deepcopy(head["source"])
    cp["ref"]["digest"] = source_fingerprint(cp["content"])
    if use_raw_hash:
        with pytest.raises(api.NonplaySourceUnavailable):
            with api.read_confirmed_nonplay_prefix(
                rig.handle,
                rig.event,
                rig.source,
                artifact_sha256=rig.raw["payload"]["artifactSha256"],
            ):
                pytest.fail("旧式と異なるraw hashを成功へ付替えました")
    else:
        with api.read_confirmed_nonplay_prefix(
            rig.handle,
            rig.event,
            rig.source,
            artifact_sha256=rig.raw["payload"]["artifactSha256"],
        ) as prefix:
            actual, _ = api._read_prefix(prefix, rig.handle, rig.source, rig.event)
            assert actual == rig.value


def saved_item(record, rig, *, first=False):
    """前置手例と明示DB行doubleを結ぶ。真正DB/原wireの証明ではない。"""
    from sqlalchemy import BigInteger, Boolean, DateTime, Integer, LargeBinary, Uuid
    from sqlalchemy.dialects.postgresql import JSONB

    from pitchlog.db.game_state.models import PlayRow
    from pitchlog.db.sync_protocol.models import (
        EventSlot,
        IdempotencyLedger,
        OperationEvent,
    )
    from pitchlog.db.writer_binding.ordinary_models import OrdinaryPitchWriteAdmission
    from pitchlog.sync.control_provider.writer_binding_models import (
        FirstBallWriteAdmission,
    )

    def row(model):
        result = {}
        for c in model.__table__.c:
            result[c.name] = (
                None
                if c.nullable
                else 1
                if isinstance(c.type, (BigInteger, Integer))
                else False
                if isinstance(c.type, Boolean)
                else str(UUID(int=800))
                if isinstance(c.type, Uuid)
                else "2026-11-06T00:00:00+00:00"
                if isinstance(c.type, DateTime)
                else "\\x" + "78" * 32
                if isinstance(c.type, LargeBinary)
                else {}
                if isinstance(c.type, JSONB)
                else "fixture"
            )
        return result

    src = record["frame"]["play"]["source"]
    tenant = str(rig.handle._bound_tenant_id)
    ev, ledger, slot, admission = (
        row(m)
        for m in (
            OperationEvent,
            IdempotencyLedger,
            EventSlot,
            FirstBallWriteAdmission if first else OrdinaryPitchWriteAdmission,
        )
    )
    ev.update(
        tenant_id=tenant,
        game_id=src["gameId"],
        id=src["eventId"],
        generation=int(src["generation"]),
        d1=int(src["d1"]),
        d2=int(record["frame"]["play"]["d2"]),
        d5=src["d5"],
        ledger_kind="accepted",
        event_kind="play_input",
        is_tombstone=False,
        replaced_at=None,
        retired_at=None,
        import_batch_id=None,
        legacy_row_identifier=None,
        migration_unverified=False,
        payload=record["original"]["payload"],
        state_diff=record["frame"]["historyEntry"]["difference"],
    )
    ledger.update(
        tenant_id=tenant,
        d5=src["d5"],
        kind="accepted",
        source_fingerprint=src["fingerprint"],
        retired_at=None,
        import_batch_id=None,
    )
    slot.update(
        tenant_id=tenant,
        game_id=src["gameId"],
        generation=int(src["generation"]),
        d1=int(src["d1"]),
        confirmed_version=1,
    )
    play = {
        **row(PlayRow),
        "tenant_id": tenant,
        "game_id": src["gameId"],
        "id": record["frame"]["play"]["playId"],
        "source_event_id": src["eventId"],
        "hidden_at": None,
        "import_batch_id": None,
        "legacy_row_identifier": None,
        "migration_unverified": False,
        "play_number": int(record["frame"]["play"]["physicalPlayNumber"]),
    }
    physical = {"play_row": play, "play_runners": []}
    admission.update(
        tenant_id=tenant,
        game_id=src["gameId"],
        d5=src["d5"],
        source_event_id=src["eventId"],
        internal_generation=int(src["generation"]),
        wire_d4=src["generation"],
        event_fingerprint=src["fingerprint"],
        state="consumed",
        transaction_id="4294967307",
        consumed_at="2026-11-06T00:00:00+00:00",
        play_row_id=play["id"],
    )
    base = {
        "kind": "legacy-first-ball-v1" if first else "accepted-ordinary-admission-v1",
        "cursor": record["cursor"],
        "event": ev,
        "ledger": ledger,
        "slot": slot,
        "admission": admission,
        "qualified": True,
        "xmins": {k: "11" for k in ("event", "ledger", "slot", "admission", "play")},
    }
    if first:
        return {**base, "play": play, "runners": []}
    before, after = record["frame"]["beforeContext"], record["frame"]["afterContext"]
    before_source = {
        k: before[k]
        for k in (
            "rules",
            "rulesDigest",
            "layoutDigest",
            "rosterDigest",
            "lineup",
            "participants",
            "runners",
            "responsibility",
        )
    }
    before_source.update(after=before["current"], t2=before["lastPlayEvaluation"])
    after_value = {
        k: after[k] for k in ("rosterDigest", "lineup", "participants", "runners")
    }
    after_value.update(
        t1={"after": after["current"]},
        nextResponsibility=after["responsibility"],
        t2=after["lastPlayEvaluation"],
    )
    ev["payload"] = copy.deepcopy(
        {
            "calculation": {
                "request": {"source": before_source},
                "response": {"value": after_value},
            }
        }
    )
    admission.update(
        source_d1=ev["d1"],
        source_d2=ev["d2"],
        history_entry=record["frame"]["historyEntry"],
        next_checkpoint_content={"projection_snapshot": physical},
    )
    return {
        **base,
        "frame": record["frame"],
        "storedEvent": api._semantic_event(ev, admission),
        "storedFingerprint": src["fingerprint"],
        "physical": physical,
        "expectedPhysical": copy.deepcopy(physical),
    }


def test_saved_profile_keeps_fingerprint_without_recreating_wire(rig):
    """意味列の指紋が原wireと違っても、保存資格を満たす別profileだけが通る。"""
    rig.records[:] = [saved_item(r, rig) for r in rig.records]
    assert any(
        wire_event_fingerprint(freeze_wire_event(r["storedEvent"]))
        != r["storedFingerprint"]
        for r in rig.records
    )
    with api.read_confirmed_nonplay_prefix(
        rig.handle,
        rig.event,
        rig.source,
        artifact_sha256=rig.raw["payload"]["artifactSha256"],
    ) as prefix:
        actual, _ = api._read_prefix(prefix, rig.handle, rig.source, rig.event)
        assert actual == rig.value


@pytest.mark.parametrize(
    "mutation",
    [
        "qualified-int",
        "qualified-false",
        "event-xmin",
        "ledger-xmin",
        "slot-xmin",
        "play-xmin",
        "admission-xmin",
        "txid",
        "bool-d1",
        "float-d2",
        "missing-column",
        "extra-column",
        "tenant",
        "game",
        "event-id",
        "d5",
        "fingerprint",
        "not-consumed",
        "retired",
        "import",
        "slot",
        "physical",
        "history",
        "expected-physical",
        "semantic",
        "fake-wire",
        "unknown-profile",
    ],
)
def test_saved_profile_rejects_each_broken_binding(rig, mutation):
    """同時hash追随や意味列再hashで保存資格の欠落を埋めない。"""
    rig.records[:] = [saved_item(r, rig) for r in rig.records]
    r = rig.records[0]
    if mutation == "qualified-int":
        r["qualified"] = 1
    elif mutation == "qualified-false":
        r["qualified"] = False
    elif mutation.endswith("-xmin"):
        r["xmins"][mutation.removesuffix("-xmin")] = "12"
    elif mutation == "txid":
        r["admission"]["transaction_id"] = "04294967307"
    elif mutation == "bool-d1":
        r["event"]["d1"] = True
    elif mutation == "float-d2":
        r["event"]["d2"] = float(r["event"]["d2"])
    elif mutation == "missing-column":
        r["event"].pop("payload")
    elif mutation == "extra-column":
        r["ledger"]["extra"] = None
    elif mutation == "tenant":
        r["ledger"]["tenant_id"] = str(UUID(int=90))
    elif mutation == "game":
        r["admission"]["game_id"] = str(UUID(int=90))
    elif mutation == "event-id":
        r["admission"]["source_event_id"] = str(UUID(int=90))
    elif mutation == "d5":
        r["ledger"]["d5"] = str(UUID(int=90))
    elif mutation == "fingerprint":
        r["ledger"]["source_fingerprint"] = "wire-v1:" + "a" * 64
    elif mutation == "not-consumed":
        r["admission"]["state"] = "evaluated"
    elif mutation == "retired":
        r["event"]["retired_at"] = "2026-11-06"
    elif mutation == "import":
        r["event"]["import_batch_id"] = str(UUID(int=90))
    elif mutation == "slot":
        r["slot"]["confirmed_version"] = 2
    elif mutation == "physical":
        r["physical"]["play_row"]["hidden_at"] = "2026-11-06"
    elif mutation == "history":
        r["admission"]["history_entry"] = {}
    elif mutation == "expected-physical":
        r["admission"]["next_checkpoint_content"] = {"projection_snapshot": {}}
    elif mutation == "semantic":
        r["storedEvent"]["event_kind"] = "1"
    elif mutation == "fake-wire":
        r["storedFingerprint"] = wire_event_fingerprint(
            freeze_wire_event(r["storedEvent"])
        )
    else:
        r["kind"] = "accepted-ordinary-admission-v2"
    with pytest.raises((api.NonplaySourceUnavailable, ValueError)):
        with api.read_confirmed_nonplay_prefix(
            rig.handle,
            rig.event,
            rig.source,
            artifact_sha256=rig.raw["payload"]["artifactSha256"],
        ):
            pytest.fail("保存資格の破損を受理しました")


def test_saved_profile_cannot_be_minted_from_free_json(rig):
    """同じ全JSONを持っても実page identity貸与がなければ資格にしない。"""
    item = saved_item(rig.records[0], rig)
    with pytest.raises(api.NonplaySourceUnavailable, match="実page"):
        api._stored_ordinary_item(
            rig.handle,
            rig.event,
            rig.source,
            item,
            rig.handle._writer_lifetime(),
            rig.runtime,
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "payload-context",
        "frame-context",
        "runner-ref",
        "extra-physical",
        "physical-bool",
        "timestamp-type",
        "nonce-type",
        "fingerprint-plain",
        "ledger-result-type",
    ],
)
def test_saved_profile_full_values_and_types_are_bound(rig, mutation):
    """全列/文脈の一葉差や数値型同値を保存証拠へ混入させない。"""
    rig.records[:] = [saved_item(r, rig) for r in rig.records]
    r = rig.records[0]
    if mutation == "payload-context":
        r["event"]["payload"]["calculation"]["request"]["source"]["after"][
            "stateFields"
        ]["state.outs"] = "2"
    elif mutation == "frame-context":
        r["frame"]["beforeContext"]["current"]["stateFields"]["state.outs"] = "2"
    elif mutation == "runner-ref":
        # 全形がない走者も、余分な走者の混入として拒否する。
        r["physical"]["play_runners"] = [
            {"tenant_id": str(UUID(int=1)), "play_id": str(UUID(int=2))}
        ]
    elif mutation == "extra-physical":
        r["physical"]["play_row"]["extra"] = 1
    elif mutation == "physical-bool":
        r["physical"]["play_row"]["play_number"] = True
    elif mutation == "timestamp-type":
        r["admission"]["consumed_at"] = 1
    elif mutation == "nonce-type":
        r["admission"]["nonce_digest"] = 1
    elif mutation == "fingerprint-plain":
        r["storedFingerprint"] = r["storedFingerprint"].removeprefix("wire-v1:")
    else:
        r["ledger"]["result"] = None
    with pytest.raises(api.NonplaySourceUnavailable):
        with api.read_confirmed_nonplay_prefix(
            rig.handle,
            rig.event,
            rig.source,
            artifact_sha256=rig.raw["payload"]["artifactSha256"],
        ):
            pytest.fail("保存全列の一葉差を受理しました")
