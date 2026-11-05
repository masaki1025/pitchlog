"""実型と明示pure doubleで一回source資格を検査する。実DB/issuer実証ではない。"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from test_sync_apply_first_ball_execution import rig as base_rig

from pitchlog.db.sync_protocol.models import IdempotencyLedger, OperationEvent
from pitchlog.repositories import transaction as tx
from pitchlog.repositories.context import _ISSUANCE_CAPABILITY, TenantContext
from pitchlog.repositories.tokens import TenantOperationResult
from pitchlog.sync import first_ball_bridge as bridge
from pitchlog.sync import first_ball_execution as first
from pitchlog.sync import ordinary_pitch_execution as ordinary
from pitchlog.sync import stats_native_hook as api
from pitchlog.sync.control_provider.evidence import (
    AttemptBinding,
    AuthorityBinding,
    EventPhaseBinding,
)
from pitchlog.sync.first_ball_frame import FirstBallBridge, FirstBallFrame
from pitchlog.sync.first_ball_payload import (
    FirstBallPlayPayload,
    read_first_ball_payload,
)
from pitchlog.sync.model import SyncEvent
from pitchlog.sync.ports import _issue_port_writer
from pitchlog.sync.tokens import IdempotencyLedgerReadToken, OperationEventReadToken

ROOT = Path(__file__).parents[2]
MODES = (
    "first-ball-play-v1",
    "ordinary-pitch-play-v1",
    "play-prefix-play-v2",
    "play-prefix-play-v3",
)


def _payload(mode, rig):
    """既固定封筒から値だけを供給し、本testで数学期待を生成しない。"""
    if mode == MODES[0]:
        value = FirstBallPlayPayload.model_validate_json(json.dumps(rig.v7))
        return (
            read_first_ball_payload(
                json.dumps(rig.v7),
                json.dumps(rig.v8),
                expected_calculation=value.calculation,
                expected_participants=value.participants,
            ),
            rig.v7,
            rig.v8,
        )
    if mode == MODES[1]:
        from test_ordinary_pitch_payload import SUCCESS, _values

        from pitchlog.sync.ordinary_pitch_payload import (
            format_ordinary_pitch_payload,
            read_ordinary_pitch_payload,
        )

        obs, people, calc = _values(SUCCESS[0])
        a, b = format_ordinary_pitch_payload(obs, people, calc)
        return (
            read_ordinary_pitch_payload(
                a, b, expected_calculation=calc, expected_participants=people
            ),
            json.loads(a),
            json.loads(b),
        )
    if mode == MODES[2]:
        from test_terminal_pitch_payload import values

        from pitchlog.sync.terminal_pitch_payload import (
            format_terminal_pitch_payload,
            read_terminal_pitch_payload,
        )

        obs, people, calc = values()
        # 数学fixtureの仮hashだけを実reader同様の規則原本hashへ束縛する。
        # T1/T2の全応答期待は変更せず、このtestは数学期待の代用ではない。
        from pitchlog.sync.terminal_pitch_payload import seal_play_prefix_metadata

        original_response = calc.response.model_dump(
            mode="json", by_alias=True, exclude_unset=True
        )
        request = calc.request.model_copy(
            update={
                "source": calc.request.source.model_copy(
                    update={
                        "rules_digest": api.source_fingerprint(
                            calc.request.rules.model_dump(mode="json", by_alias=True)
                        )
                    }
                )
            }
        )
        request, response = seal_play_prefix_metadata(request, calc.response)
        compared = response.model_dump(mode="json", by_alias=True, exclude_unset=True)
        # 唯一sealの自己echo digest以外は応答全fieldを元goldenへ完全比較する。
        compared["value"]["nextPrefixRef"]["checkpoint"]["digest"] = original_response[
            "value"
        ]["nextPrefixRef"]["checkpoint"]["digest"]
        assert compared == original_response
        calc = calc.model_copy(update={"request": request, "response": response})
        a, b = format_terminal_pitch_payload(obs, people, calc)
        return (
            read_terminal_pitch_payload(
                a, b, expected_calculation=calc, expected_participants=people
            ),
            json.loads(a),
            json.loads(b),
        )
    from pitchlog.sync.terminal_pitch_payload import (
        LineupPitchPlayPayload,
        read_lineup_pitch_payload,
    )

    raw = json.loads(
        (
            ROOT
            / "contracts/state-transition/lineup_play_prefix_payload_vectors_v1.json"
        ).read_text()
    )["cases"][0]
    expected = LineupPitchPlayPayload.model_validate_json(json.dumps(raw["V7"]))
    return (
        read_lineup_pitch_payload(
            json.dumps(raw["V7"]),
            json.dumps(raw["V8"]),
            expected_calculation=expected.calculation,
        ),
        raw["V7"],
        raw["V8"],
    )


@pytest.fixture(params=MODES)
def native(request, monkeypatch):
    """認可/実consume/DBは合成と明記し、生存型と原本の拒否だけを検査する。"""
    generator = cast(Any, base_rig).__wrapped__(monkeypatch)
    r = next(generator)
    mode = request.param
    payload, raw, diff = _payload(mode, r)
    request_raw = raw["calculation"]["request"]
    prefix = request_raw.get("prefixRef", {})
    tenant = UUID(prefix.get("tenantId", str(r.context.tenant_id)))
    game = UUID(prefix.get("gameId", str(r.rows.game_id)))
    context = TenantContext(tenant, _ISSUANCE_CAPABILITY)
    r.handle._context, r.handle._bound_tenant_id, r.handle._bound_integrity_proof = (
        context,
        tenant,
        context._integrity_proof,
    )
    r.context = context
    d1 = int(request_raw.get("source", {}).get("position", {}).get("d1", "1"))
    d2 = int(request_raw.get("source", {}).get("position", {}).get("d2", "1"))
    identity = request_raw.get("playIdentity", {})
    d5 = UUID(identity.get("d5", str(uuid4())))
    event = SyncEvent(str(d5), str(game), d1, "pure-wire-d4", "1", 0, raw, diff)
    projected = SyncEvent(str(d5), str(game), d1, "pure-wire-d4", "1", d2, raw, diff)
    r.event, r.projected, r.payload, r.mode = event, projected, payload, mode
    phase = EventPhaseBinding(
        AttemptBinding(
            AuthorityBinding(uuid4(), uuid4(), uuid4()),
            tenant,
            uuid4(),
            game,
            "pure-wire-d4",
            1,
            uuid4(),
            1,
            "pure-request",
            1,
        ),
        uuid4(),
        1,
        d1,
        d5,
        r.view.event_fingerprint,
    )
    r.source.event, r.source.context, r.source.phase, r.source.write_started = (
        event,
        context,
        phase,
        True,
    )
    r.bound._phase_snapshot = json.dumps({"phase": {"internal_generation": 1}})
    r.bound._lease = SimpleNamespace(
        nonce=b"n" * 32,
        attempt_id=phase.attempt.attempt_id,
        phase_id=phase.phase_id,
        game_id=game,
        device_id=phase.attempt.device_id,
        _phase_snapshot=r.bound._phase_snapshot,
    )
    event_id = UUID(identity.get("eventId", str(uuid4())))
    r.event_row = dict.fromkeys(OperationEvent.__table__.c.keys())
    r.event_row.update(
        tenant_id=tenant,
        id=event_id,
        game_id=game,
        generation=1,
        d1=d1,
        d2=d2,
        d5=d5,
        ledger_kind="accepted",
        event_kind="play_input",
        payload=raw,
        state_diff=diff,
        is_tombstone=False,
        migration_unverified=False,
    )
    r.ledger_row = dict.fromkeys(IdempotencyLedger.__table__.c.keys())
    r.ledger_row.update(
        tenant_id=tenant,
        d5=d5,
        kind="accepted",
        source_fingerprint=r.view.event_fingerprint,
        result={"state": "受理", "d3": d1, "temporary_id_mapping": {}},
    )
    r.reads = []

    def run(handle, token):
        assert handle is r.handle
        r.reads.append(type(token))
        if type(token) is OperationEventReadToken:
            assert (token.game_id, token.generation, token.d1) == (game, 1, d1)
            return TenantOperationResult((tuple(r.event_row.values()),))
        if type(token) is IdempotencyLedgerReadToken:
            assert token.d5 == d5
            return TenantOperationResult((tuple(r.ledger_row.values()),))
        raise AssertionError("本単位はread token以外を発行しない")

    monkeypatch.setattr(tx._TenantTransaction, "run", run)
    r.writer._close()
    r.writer = _issue_port_writer(r.handle.run)
    refs = (
        r.bound,
        r.bound._lease,
        phase,
        r.bound._lease.nonce,
        r.bound._phase_snapshot,
    )
    lifetime = r.handle._writer_lifetime()
    if mode == MODES[0]:
        br, fr = object.__new__(FirstBallBridge), object.__new__(FirstBallFrame)
        state = first._Execution(
            r.handle,
            r.writer,
            r.source,
            event,
            tx._TRANSACTION_RUNTIMES[r.key],
            lifetime,
            context,
            r.bound,
            r.bound._lease,
            phase,
            r.bound._phase_snapshot,
            r.bound._lease.nonce,
            r.view.event_fingerprint,
            phase="projected",
            bridge=br,
            frame=fr,
            payload=payload,
        )
        state.stats_source_reference = (br, fr, payload, *refs)
        monkeypatch.setitem(first._EXECUTIONS, r.key, state)
        monkeypatch.setitem(
            bridge._STATES,
            br,
            bridge._State(
                r.handle,
                r.writer,
                r.key,
                state.runtime,
                lifetime,
                tenant,
                event,
                r.view.event_fingerprint,
                r.source,
                phase="consumed",
            ),
        )
    else:
        fr = object.__new__(ordinary.OrdinaryPitchFrame)
        state = ordinary._Execution(
            r.handle,
            r.writer,
            r.source,
            event,
            lifetime,
            tx._TRANSACTION_RUNTIMES[r.key],
            frame_id=uuid4(),
            prefix=SimpleNamespace(
                checkpoint=SimpleNamespace(rules=payload.calculation.request.rules)
            ),
            payload=payload,
            phase="projected",
            mode=mode,
            preparation_used=True,
        )
        state.stats_source_reference = (fr, state.frame_id, payload, *refs)
        monkeypatch.setitem(ordinary._EXECUTIONS, r.key, state)
    r.state = state
    try:
        with tx._sync_apply_active():
            yield r
    finally:
        state.stats_source_reference = None
        state.phase = "closed"
        first._EXECUTIONS.pop(r.key, None)
        ordinary._EXECUTIONS.pop(r.key, None)
        generator.close()


def _issue(r):
    """実行sourceからの私有発行だけを呼ぶ。"""
    return api._issue_native_stats_source(
        r.handle, r.writer, r.event, r.projected, generation=1
    )


def test_one_opaque_source_consumption_without_math_or_writes(native):
    """全4variantで同原本を読み、T5/保存を呼ばず一度だけ値を返す。"""
    r = native
    receipt = _issue(r)
    with pytest.raises(api.StatsNativeSourceError):
        _issue(r)
    values = api._consume_native_stats_source(r.handle, receipt)
    assert values.source_event_id == r.event_row["id"]
    assert values.native_payload_json == api._json(r.event.v7)
    assert values.d2 == r.projected.v6 and values.d5 == UUID(r.event.d5)
    assert set(r.reads) == {OperationEventReadToken, IdempotencyLedgerReadToken}
    with pytest.raises(api.StatsNativeSourceError):
        api._consume_native_stats_source(r.handle, receipt)


@pytest.mark.parametrize(
    "change",
    [
        "phase",
        "frame",
        "runtime",
        "writer",
        "bound",
        "lease",
        "nonce",
        "source_phase",
        "payload",
        "rules",
        "event",
        "projected",
    ],
)
def test_changed_live_execution_cannot_issue(native, monkeypatch, change):
    """失効/別frame/改変payload規則を成功や未供給へ変換しない。"""
    r = native
    if change == "phase":
        r.state.phase = "consumed"
    elif change == "frame":
        if r.mode == MODES[0]:
            r.state.frame = object.__new__(FirstBallFrame)
        else:
            r.state.frame_id = uuid4()
    elif change == "runtime":
        monkeypatch.setitem(tx._TRANSACTION_RUNTIMES, r.key, object())
    elif change == "writer":
        r.writer._close()
    elif change == "bound":
        r.source.bound = object()
    elif change == "lease":
        r.bound._lease = SimpleNamespace(nonce=b"n" * 32)
    elif change == "nonce":
        r.bound._lease.nonce = b"x" * 32
    elif change == "source_phase":
        r.source.phase = object()
    elif change == "payload":
        r.state.payload = object()
    elif change == "rules":
        p = r.payload.v7 if r.mode == MODES[0] else r.payload
        rule = p.calculation.request.rules
        object.__setattr__(rule, "dh", not rule.dh)
    elif change == "event":
        r.source.event = r.projected
    else:
        r.projected = r.event
    with pytest.raises(
        (
            api.StatsNativeSourceError,
            first.FirstBallExecutionError,
            ordinary.OrdinaryPitchExecutionError,
        )
    ):
        _issue(r)


@pytest.mark.parametrize(
    "field,value",
    [
        ("tenant_id", UUID(int=99)),
        ("d2", True),
        ("d5", UUID(int=99)),
        ("ledger_kind", "rejected"),
        ("event_kind", "play"),
        ("retired_at", "invalid"),
        ("payload", {}),
        ("state_diff", {}),
    ],
)
def test_changed_operation_original_cannot_issue(native, field, value):
    """同handle readでも別tenant/連番/台帳/原V7V8を拒否する。"""
    native.event_row[field] = value
    with pytest.raises(api.StatsNativeSourceError):
        _issue(native)


@pytest.mark.parametrize(
    "field,value",
    [
        ("kind", "evacuated"),
        ("source_fingerprint", "forged"),
        ("reason", "unknown"),
        ("result", {"state": "受理", "d3": True, "temporary_id_mapping": {}}),
    ],
)
def test_changed_ledger_cannot_issue(native, field, value):
    """確定結果不明・指紋違いを原本成功扱いにしない。"""
    native.ledger_row[field] = value
    with pytest.raises(api.StatsNativeSourceError):
        _issue(native)


@pytest.mark.parametrize(
    "change", ["foreign_handle", "expired", "row_changed", "nonce_changed"]
)
def test_receipt_consumption_rechecks_and_burns_on_failure(native, change):
    """旧発行/別handle/照会後の変更を拒否し、同じ資格を再利用しない。"""
    r = native
    receipt = _issue(r)
    handle = r.handle
    if change == "foreign_handle":
        handle = object()
    elif change == "expired":
        r.state.stats_source_reference = None
    elif change == "row_changed":
        r.event_row["id"] = uuid4()
    else:
        r.bound._lease.nonce = b"x" * 32
    with pytest.raises(
        (
            api.StatsNativeSourceError,
            first.FirstBallExecutionError,
            ordinary.OrdinaryPitchExecutionError,
        )
    ):
        api._consume_native_stats_source(handle, receipt)
    with pytest.raises(api.StatsNativeSourceError):
        api._consume_native_stats_source(r.handle, receipt)


def test_free_receipts_and_values_are_not_authority(native):
    """通常構築も同型手作りも登録されていなければ拒否する。"""
    with pytest.raises(api.StatsNativeSourceError):
        api.NativeStatsSourceReceipt()
    for forged in (object(), object.__new__(api.NativeStatsSourceReceipt), {}):
        with pytest.raises(api.StatsNativeSourceError):
            api._consume_native_stats_source(native.handle, forged)


def test_failed_original_read_cannot_reissue_for_same_frame(native):
    """結果不明後に原本を直しても同frameの別資格へ置換しない。"""
    r = native
    old = r.event_row["ledger_kind"]
    r.event_row["ledger_kind"] = "rejected"
    with pytest.raises(api.StatsNativeSourceError):
        _issue(r)
    r.event_row["ledger_kind"] = old
    with pytest.raises(api.StatsNativeSourceError):
        _issue(r)


def test_receipt_does_not_pin_itself_after_execution_cleanup(native):
    """finally失効後は弱いregistryがnonce/実行参照を永久保持しない。"""
    import gc
    import weakref

    receipt = _issue(native)
    observed = weakref.ref(receipt)
    native.state.stats_source_reference = None
    del receipt
    gc.collect()
    assert observed() is None


@pytest.mark.parametrize("unclosed", ["not_consumed", "still_preparing"])
def test_real_projection_consumption_must_be_complete(native, unclosed):
    """ready参照だけでは資格にならず、本物のconsumed完了も必須にする。"""
    r = native
    if r.mode == MODES[0]:
        bridge._STATES[r.state.bridge].phase = "ready"
    elif unclosed == "not_consumed":
        r.state.preparation_used = False
    else:
        r.state.preparation_token = object()
    with pytest.raises(
        (
            api.StatsNativeSourceError,
            first.FirstBallExecutionError,
            ordinary.OrdinaryPitchExecutionError,
        )
    ):
        _issue(r)
