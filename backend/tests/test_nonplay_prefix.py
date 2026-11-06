"""原本readerの有限対向。issuer/Session/DB応答は明示したpure double。"""

from __future__ import annotations

import copy
import hashlib
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
    # 原手例は不変。これは現runtimeだけの自己pinを持つ新規pure文脈。
    current = hashlib.sha256(
        (ROOT / "frontend/public/domain/pitchlog-domain.js").read_bytes()
    ).hexdigest()
    content["executionArtifactSha256"] = current
    head = value["activeStack"][0]["play"]
    content["activeHead"] = copy.deepcopy(head)
    content["d1Head"]["source"] = copy.deepcopy(head["source"])
    content["projectionHead"]["source"] = copy.deepcopy(head["source"])
    value["checkpoint"]["ref"]["digest"] = source_fingerprint(content)
    raw = copy.deepcopy(CASES["undoEvents"][0])
    raw["payload"]["artifactSha256"] = current
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


def test_saved_profile_accepts_finite_saved_course_and_rejects_boolean(rig):
    """実数座標の保存原本を保持し、bool偽装を型境界で拒否する。"""
    rig.records[:] = [saved_item(r, rig) for r in rig.records]
    item = rig.records[0]
    for value in (
        item["physical"],
        item["expectedPhysical"],
        item["admission"]["next_checkpoint_content"]["projection_snapshot"],
    ):
        value["play_row"]["course_x"] = 0.375
    with api.read_confirmed_nonplay_prefix(
        rig.handle,
        rig.event,
        rig.source,
        artifact_sha256=rig.raw["payload"]["artifactSha256"],
    ) as prefix:
        actual, _ = api._read_prefix(prefix, rig.handle, rig.source, rig.event)
        assert actual == rig.value
    for value in (
        item["physical"],
        item["expectedPhysical"],
        item["admission"]["next_checkpoint_content"]["projection_snapshot"],
    ):
        value["play_row"]["course_x"] = True
    with pytest.raises(api.NonplaySourceUnavailable):
        with api.read_confirmed_nonplay_prefix(
            rig.handle,
            rig.event,
            rig.source,
            artifact_sha256=rig.raw["payload"]["artifactSha256"],
        ):
            pytest.fail("bool座標を保存済みDoubleとして受理しました")


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


def legacy_profile_fixture(rig, monkeypatch, prior):
    """前置手例から型整合した旧v3境界doubleを作り、数学期待は生成しない。"""
    from pitchlog.repositories.play_prefix import read_lineup_prefix_document

    for frame in rig.value["activeStack"]:
        for name in ("beforeContext", "afterContext"):
            context = frame[name]
            context["layoutDigest"] = context["rosterDigest"]
    cp = rig.value["checkpoint"]
    c = cp["content"]
    head = rig.value["activeStack"][0]["play"]
    src = head["source"]
    restored = copy.deepcopy(rig.value["activeStack"][0]["afterContext"])
    ref = {
        "version": "3",
        "scope": "play-prefix-v3",
        "tenantId": c["scope"]["tenantId"],
        "gameId": c["scope"]["gameId"],
        "generation": c["scope"]["generation"],
        "length": c["activeDepth"],
        "checkpoint": copy.deepcopy(cp["ref"]),
        "historyVersion": c["historyVersion"],
        "origin": c["origin"],
    }
    raw = {
        "version": "3",
        "id": cp["ref"]["id"],
        "revision": cp["ref"]["revision"],
        "history_version": c["storageHistoryEpoch"],
        "storage_anchor": {
            "id": cp["ref"]["id"],
            "history_epoch": c["storageHistoryEpoch"],
        },
        "prefix_ref": ref,
        "wire_d4": c["scope"]["generation"],
        "internal_generation": "1",
        "recovery_generation": "1",
        "confirmed_watermark": c["d3"],
        "applied_watermark": c["d3"],
        "last_source": {
            "id": src["eventId"],
            "tenant_id": c["scope"]["tenantId"],
            "game_id": src["gameId"],
            "generation": "1",
            "d1": src["d1"],
            "d2": head["d2"],
            "d5": src["d5"],
            "source_fingerprint": src["fingerprint"],
            "event_fingerprint": src["fingerprint"],
        },
        "history_depth": c["activeDepth"],
        "after": restored["current"],
        "rules": restored["rules"],
        "t2": restored["lastPlayEvaluation"],
        "runners": restored["runners"],
        "participants": restored["participants"],
        "pa_start_source": restored["responsibility"]["paStartSource"],
        "lineup": restored["lineup"],
        "roster_digest": restored["rosterDigest"],
        "roster_source_digest": source_fingerprint({"explicit-roster-fixture": 1}),
        "source_origin": c["origin"],
        "previous_prefix_ref": copy.deepcopy(ref),
        "artifact_sha256": prior,
        "state": "current",
        "projection_snapshot": {
            "play_row": {"fixture": "not-real-DB"},
            "play_runners": [],
        },
    }
    raw["content_digest"] = source_fingerprint(raw)
    doc = read_lineup_prefix_document(_canonical_json(raw))
    row = {
        "tenant_id": c["scope"]["tenantId"],
        "game_id": c["scope"]["gameId"],
        "internal_generation": 1,
        "id": doc.id,
        "revision": int(doc.revision),
        "history_version": int(doc.history_version),
        "recovery_generation": 1,
        "confirmed_watermark": int(c["d3"]),
        "applied_watermark": int(c["d3"]),
        "content_digest": doc.content_digest,
        "content": raw,
        "roster": {},
        "state": "current",
        "saved_at": "2026-11-06T00:00:00+00:00",
    }
    original = tx._TenantTransaction.run_function

    def run(handle, operation):
        if type(operation) is api._LockNonplayCheckpoint:
            q = api._qualified_nonplay_call(handle, operation)
            assert q.operation is operation
            return TenantOperationResult(
                (
                    (
                        _canonical_json(
                            {
                                "checkpoint": raw,
                                "storage": {
                                    "row": row,
                                    "nextPhysicalPlayNumber": rig.actual_next_physical,
                                },
                                "generationChain": rig.chain,
                            }
                        ),
                    ),
                )
            )
        return original(handle, operation)

    monkeypatch.setattr(tx._TenantTransaction, "run_function", run)
    return raw, row


def test_current_fixture_self_pin_is_derived_without_changing_original_goldens():
    """自己pin/digestだけを派生し、元JSON/数学/履歴/原保存pinは全保持する。"""
    path = ROOT / "contracts/state-transition/nonplay_prefix_bridge_cases_v1.json"
    before = path.read_bytes()
    original = copy.deepcopy(CASES)
    actual = hashlib.sha256(
        (ROOT / "frontend/public/domain/pitchlog-domain.js").read_bytes()
    ).hexdigest()
    for step in (2, 5):
        value, event, records = fixture_values(step)
        assert value["checkpoint"]["content"]["executionArtifactSha256"] == actual
        assert event["payload"]["artifactSha256"] == actual
        assert event["payload"]["expectedCheckpoint"] == value["checkpoint"]["ref"]
        assert value["checkpoint"]["ref"]["digest"] == source_fingerprint(
            value["checkpoint"]["content"]
        )
        assert (
            event["payload"]["calculation"]
            == CASES["undoEvents"][0]["payload"]["calculation"]
        )
        assert [r["frame"]["historyEntry"] for r in records] == [
            f["historyEntry"] for f in CASES["steps"][step]["source"]["activeStack"]
        ]
    assert CASES == original and path.read_bytes() == before


@pytest.mark.parametrize("prior", ["unknown", "same-current"])
def test_legacy_v3_requires_real_shared_finite_qualification(
    rig, monkeypatch, tmp_path, prior
):
    """旧原本が型整合していても未宣言pairをcurrentへ投影しない。"""
    current = rig.raw["payload"]["artifactSha256"]
    prior = (
        current
        if prior == "same-current"
        else source_fingerprint({"unregistered-legacy": 1})
    )
    raw, row = legacy_profile_fixture(rig, monkeypatch, prior)
    if prior == current:
        # 正常v3宣言を別rootで欠落させる。unsupported固定に依存しない真の負例。
        from test_play_prefix import _v3_compatibility_root

        from pitchlog.repositories import play_prefix

        root, module = _v3_compatibility_root(tmp_path)
        path = (
            root
            / "contracts/state-transition/play_prefix_v2_source_compatibility_v1.json"
        )
        declared = json.loads(path.read_bytes())
        declared["cases"] = [
            r for r in declared["cases"] if r["sourceFormat"] != "play-prefix-play-v3"
        ]
        path.write_text(json.dumps(declared, ensure_ascii=False, indent=2) + "\n")
        monkeypatch.setattr(play_prefix, "__file__", str(module))
    original = copy.deepcopy((raw, row))
    with pytest.raises(api.NonplaySourceUnavailable, match="有限artifact互換資格"):
        with api.read_confirmed_nonplay_prefix(
            rig.handle, rig.event, rig.source, artifact_sha256=current
        ):
            pytest.fail("v3未宣言互換を受理しました")
    assert (raw, row) == original
    assert not any(type(op) is api._ReadNonplayHistoryPage for op in rig.calls)


def test_shared_gate_unknown_format_missing_and_changed_witness_stays_closed(
    tmp_path, monkeypatch
):
    """正式checker本体を使い、独立な欠落/別形式/改変の閉拒否を確認する。"""
    from pitchlog.repositories import play_prefix
    from pitchlog.repositories.ordinary_prefix import OrdinaryPrefixError

    current = hashlib.sha256(
        (ROOT / "frontend/public/domain/pitchlog-domain.js").read_bytes()
    ).hexdigest()
    for prior in (source_fingerprint({"unknown": 2}),):
        with pytest.raises(OrdinaryPrefixError):
            play_prefix._require_legacy_compatibility(
                prior, current, source_format="play-prefix-play-v3"
            )
    with pytest.raises(OrdinaryPrefixError):
        play_prefix._require_legacy_compatibility(
            current, current, source_format="unknown-format"
        )
    # pathだけを隔離rootへ向け、checker/成功値をstubしない。
    fake = tmp_path / "backend/src/pitchlog/repositories/play_prefix.py"
    fake.parent.mkdir(parents=True)
    fake.write_text("# test-only root")
    monkeypatch.setattr(play_prefix, "__file__", str(fake))
    for value in (
        None,
        {
            "version": "1",
            "cases": [
                {
                    "priorArtifactSha256": current,
                    "executionArtifactSha256": current,
                    "sourceFormat": "first-ball-play-v1",
                    "compatibleOperations": [
                        "deriveState",
                        "deriveFirstPitchWithContinuation",
                    ],
                    "witnessSha256": "changed",
                }
            ],
        },
    ):
        path = (
            tmp_path
            / "contracts/state-transition/play_prefix_v2_source_compatibility_v1.json"
        )
        if value is not None:
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(value))
        with pytest.raises(OrdinaryPrefixError):
            play_prefix._require_legacy_compatibility(
                current, current, source_format="first-ball-play-v1"
            )


@pytest.mark.parametrize("which", ["prior", "current"])
def test_legacy_v3_declared_real_gate_returns_current_view_preserving_storage(
    rig, monkeypatch, which
):
    """有限宣言済旧v3を本物gate経由で提供し、原CP/storageを保持する。"""
    witness = json.loads(
        (
            ROOT / "contracts/state-transition/nonplay_v3_compatibility_witness_v1.json"
        ).read_bytes()
    )
    current = witness["executionArtifactSha256"]
    prior = witness["priorArtifacts"][0] if which == "prior" else current
    raw, row = legacy_profile_fixture(rig, monkeypatch, prior)
    original = copy.deepcopy((raw, row))
    with api.read_confirmed_nonplay_prefix(
        rig.handle, rig.event, rig.source, artifact_sha256=current
    ) as prefix:
        view, storage = api._read_prefix(prefix, rig.handle, rig.source, rig.event)
        assert view["checkpoint"]["content"]["executionArtifactSha256"] == current
        assert storage["storage"]["row"] == row
        assert raw["artifact_sha256"] == prior
        assert raw["content_digest"] == row["content_digest"]
        assert view["checkpoint"]["ref"]["digest"] != row["content_digest"]
    assert (raw, row) == original
