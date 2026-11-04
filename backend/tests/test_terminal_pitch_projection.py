"""runner実識別と元play予約に束縛された物理10列を検査する。"""

from uuid import UUID, uuid5

import pytest
from test_terminal_pitch_payload import SUCCESS, values

from pitchlog.sync.ordinary_pitch_execution import OrdinaryPitchExecutionError
from pitchlog.sync.terminal_pitch_projection import (
    apply_play_prefix_projection,
    runner_physical_rows,
)


@pytest.mark.parametrize("case", SUCCESS, ids=lambda c: c["caseId"])
def test_runner_all10_and_d5_stable_ids(case):
    """本人/責任投手を数学実sourceから写し、同play再試行で採番し直さない。"""
    _, _, calc = values(case)
    q = calc.request
    rows = runner_physical_rows(
        calc.request.source.runners,
        t1=calc.response.value.t1,
        tenant_id=UUID(q.prefix_ref.tenant_id),
        play_id=UUID(q.play_identity.play_id),
    )
    assert rows == runner_physical_rows(
        calc.request.source.runners,
        t1=calc.response.value.t1,
        tenant_id=UUID(q.prefix_ref.tenant_id),
        play_id=UUID(q.play_identity.play_id),
    )
    for row, runner in zip(rows, calc.request.source.runners, strict=True):
        assert row == {
            "tenant_id": q.prefix_ref.tenant_id,
            "id": str(
                uuid5(
                    UUID(q.play_identity.play_id), "play-prefix-runner:" + runner.base
                )
            ),
            "play_id": q.play_identity.play_id,
            "base": int(runner.base),
            "runner_id": runner.runner_id,
            "status": runner.status,
            "status_source": runner.status_source,
            "responsible_pitcher_id": runner.responsible_pitcher_id,
            "import_batch_id": None,
            "retired_at": None,
        }


def test_free_projection_object_cannot_issue_frame():
    """値だけを渡して保存成功を発行できない。"""
    with pytest.raises(OrdinaryPitchExecutionError):
        apply_play_prefix_projection(object(), object())


def test_prepare_keeps_raw_v1_and_separates_wire_head_storage_anchor_and_digest():
    """構成器の全41/10列と移行封筒を試す。合成値を実source資格にはしない。"""
    import copy
    import json
    from types import SimpleNamespace

    from test_ordinary_prefix import _checkpoint

    from pitchlog.domainrt.play_prefix_continuation import (
        PlayPrefixRequest,
        PlayPrefixSuccess,
    )
    from pitchlog.repositories.ordinary_prefix import read_checkpoint_document
    from pitchlog.repositories.play_prefix import read_play_prefix_document
    from pitchlog.sync.idempotency import source_fingerprint
    from pitchlog.sync.model import SyncEvent
    from pitchlog.sync.terminal_pitch_payload import (
        TerminalPitchPlayPayload,
        seal_play_prefix_metadata,
    )
    from pitchlog.sync.terminal_pitch_projection import build_play_prefix_preparation

    obs, people, calc = values(SUCCESS[0])
    q = calc.request.model_dump(mode="json", by_alias=True, exclude_unset=True)
    r = calc.response.model_dump(mode="json", by_alias=True, exclude_unset=True)
    # 契約の任意位置echoを、この構成器試験だけ実append形へ機械的に束縛する。
    q["source"]["position"] = {"d1": "4", "d2": "3001", "appliedWatermark": "3"}
    r["value"]["sourcePosition"] = q["source"]["position"]
    last = q["source"]["lastSource"]
    raw = _checkpoint()
    raw.update(
        id=q["prefixRef"]["checkpoint"]["id"],
        revision=q["prefixRef"]["checkpoint"]["revision"],
        prefix_ref=q["prefixRef"]["origin"],
        wire_d4=q["prefixRef"]["generation"],
        confirmed_watermark=q["source"]["position"]["appliedWatermark"],
        applied_watermark=q["source"]["position"]["appliedWatermark"],
        history_depth=q["source"]["historyDepth"],
        after=q["t1"]["before"],
        rules=q["rules"],
        t2=q["source"]["t2"],
        artifact_sha256=q["source"]["priorArtifactSha256"],
        last_source={
            "id": last["eventId"],
            "tenant_id": q["prefixRef"]["tenantId"],
            "game_id": q["prefixRef"]["gameId"],
            "generation": "1",
            "d1": "3",
            "d2": "2001",
            "d5": last["d5"],
            "source_fingerprint": "c" * 64,
            "event_fingerprint": "c" * 64,
        },
    )
    raw["content_digest"] = source_fingerprint(
        {k: v for k, v in raw.items() if k != "content_digest"}
    )
    doc = read_checkpoint_document(json.dumps(raw))
    for ref in (
        q["prefixRef"],
        q["source"]["prefixRef"],
        r["value"]["previousPrefixRef"],
    ):
        ref["checkpoint"]["digest"] = doc.content_digest
    q["source"]["bridge"]["checkpoint"]["digest"] = doc.content_digest
    typed_q, typed_r = seal_play_prefix_metadata(
        PlayPrefixRequest.model_validate_json(json.dumps(q)),
        PlayPrefixSuccess.model_validate_json(json.dumps(r)),
    )
    wire = {
        "formatVersion": "play-prefix-play-v2",
        "observations": obs.model_dump(mode="json", by_alias=True),
        "participants": people.model_dump(mode="json", by_alias=True),
        "calculation": {
            "formatVersion": "play-prefix-calculation-v2",
            "artifactSha256": calc.artifact_sha256,
            "request": typed_q.model_dump(
                mode="json", by_alias=True, exclude_unset=True
            ),
            "response": typed_r.model_dump(
                mode="json", by_alias=True, exclude_unset=True
            ),
        },
    }
    payload = TerminalPitchPlayPayload.model_validate_json(json.dumps(wire))
    event = SyncEvent(
        q["playIdentity"]["d5"],
        q["prefixRef"]["gameId"],
        int(q["source"]["position"]["d1"]),
        q["prefixRef"]["generation"],
        v6=int(q["source"]["position"]["d2"]),
    )
    state = SimpleNamespace(
        prefix=SimpleNamespace(
            checkpoint=doc,
            roster=SimpleNamespace(model_dump=lambda **kwargs: {}),
            next_play_number=4,
        ),
        payload=payload,
        frame_id=UUID(int=500),
        projected=event,
        event=event,
        handle=object(),
        source=SimpleNamespace(
            read=lambda *args: SimpleNamespace(event_fingerprint="c" * 64)
        ),
    )
    original = copy.deepcopy(raw)
    prepared = build_play_prefix_preparation(
        state,
        {"id": UUID(q["playIdentity"]["eventId"])},
        UUID(q["prefixRef"]["tenantId"]),
    )
    assert prepared["checkpoint"] == original
    next_doc = read_play_prefix_document(json.dumps(prepared["next_checkpoint"]))
    assert next_doc.id == doc.id
    assert next_doc.prefix_ref.checkpoint.id != doc.id
    assert next_doc.history_version == doc.history_version
    assert next_doc.content_digest != next_doc.prefix_ref.checkpoint.digest
    assert len(prepared["play_row"]) == 41
    assert next_doc.projection_snapshot.play_runners == ()
    assert len(next_doc.runners) == 1
    assert next_doc.projection_snapshot.play_row == prepared["play_row"]
    assert prepared["play_row"]["id"] == q["playIdentity"]["playId"]
    assert prepared["play_row"]["source_event_id"] == q["playIdentity"]["eventId"]
    assert prepared["history_entry"] == r["value"]["newHistoryEntry"]


@pytest.mark.parametrize("case_index", [0, 3, 15])
def test_new_execution_uses_one_actual_artifact_call_and_cannot_store_fake_scope(
    monkeypatch, case_index
):
    """資格readerだけを合成する内部検査。実artifact全応答と一回callを検査する。"""
    import json
    from types import SimpleNamespace

    from pitchlog.domainrt.host import NodeDomainHost
    from pitchlog.repositories import play_prefix
    from pitchlog.sync import ordinary_pitch_execution as execution
    from pitchlog.sync.model import SyncEvent
    from pitchlog.sync.terminal_pitch_payload import format_terminal_pitch_payload

    obs, people, calc = values(SUCCESS[case_index])
    v7, v8 = format_terminal_pitch_payload(obs, people, calc)
    event = SyncEvent(
        calc.request.play_identity.d5,
        calc.request.prefix_ref.game_id,
        int(calc.request.source.position.d1),
        calc.request.prefix_ref.generation,
        v7=json.loads(v7),
        v8=json.loads(v8),
    )
    state = SimpleNamespace(
        event=event, handle=object(), source=object(), phase="preparing"
    )
    monkeypatch.setattr(
        play_prefix,
        "read_confirmed_play_prefix",
        lambda *args, **kwargs: SimpleNamespace(
            source=calc.request.source, roster=object()
        ),
    )
    monkeypatch.setattr(execution, "_live", lambda state: None)
    monkeypatch.setattr(
        execution, "select_ordinary_pitch_participants", lambda *args: people
    )
    actual_call = NodeDomainHost.call
    calls = []

    def traced(host, operation, request):
        calls.append(operation)
        return actual_call(host, operation, request)

    monkeypatch.setattr(NodeDomainHost, "call", traced)
    execution._evaluate_play_prefix(state)
    assert calls == ["derivePlayPrefixWithContinuation"]
    assert state.phase == "ready"
    assert state.payload.calculation == calc
    # 合成handleは実transaction/frame寿命を通過できない。
    with pytest.raises(OrdinaryPitchExecutionError):
        execution._consume_ordinary_pitch_frame(
            state.handle, event, object(), mode="play-prefix-play-v2"
        )


def test_new_execution_rejects_different_loaded_source_before_math(monkeypatch):
    """実loaded hashと異なるqualification sourceは一回callさえ許さない。"""
    import json
    from types import SimpleNamespace

    from pitchlog.domainrt.host import NodeDomainHost
    from pitchlog.domainrt.play_prefix_continuation import PlayPrefixSource
    from pitchlog.repositories import play_prefix
    from pitchlog.sync import ordinary_pitch_execution as execution
    from pitchlog.sync.model import SyncEvent
    from pitchlog.sync.terminal_pitch_payload import format_terminal_pitch_payload

    obs, people, calc = values()
    v7, v8 = format_terminal_pitch_payload(obs, people, calc)
    source = calc.request.source.model_dump(
        mode="json", by_alias=True, exclude_unset=True
    )
    source["executionArtifactSha256"] = "0" * 64
    wrong = PlayPrefixSource.model_validate_json(json.dumps(source))
    event = SyncEvent(
        calc.request.play_identity.d5,
        calc.request.prefix_ref.game_id,
        int(calc.request.source.position.d1),
        calc.request.prefix_ref.generation,
        v7=json.loads(v7),
        v8=json.loads(v8),
    )
    state = SimpleNamespace(
        event=event, handle=object(), source=object(), phase="preparing"
    )
    monkeypatch.setattr(
        play_prefix,
        "read_confirmed_play_prefix",
        lambda *args, **kwargs: SimpleNamespace(source=wrong, roster=object()),
    )
    monkeypatch.setattr(execution, "_live", lambda state: None)
    calls = []
    monkeypatch.setattr(NodeDomainHost, "call", lambda *args: calls.append(args))
    with pytest.raises(OrdinaryPitchExecutionError):
        execution._evaluate_play_prefix(state)
    assert calls == []
