"""取消Portは資格を作らず、元参照tokenと厳密応答だけを扱う。"""

import pytest
from test_nonplay_prefix import CASES, wire_event
from test_nonplay_prefix import rig as rig

from pitchlog.repositories.tokens import TenantOperationResult
from pitchlog.sync.ports import _issue_port_writer
from pitchlog.sync.undo_ports import (
    _UNDO_CONTENT_REJECTION_REASON,
    UndoContentValidationPort,
    UndoProjectionPort,
    ValidateUndoToken,
)


@pytest.mark.parametrize(
    "rows,accepted",
    [(((True, None),), True), (((False, _UNDO_CONTENT_REJECTION_REASON),), False)],
)
def test_content_original_event_and_writer_identity(rows, accepted):
    """自由計算やSQLをPortへ渡さない。"""
    calls = []
    writer = _issue_port_writer(
        lambda token: (calls.append(token), TenantOperationResult(rows))[1]
    )
    event = wire_event(CASES["undoEvents"][0])
    assert UndoContentValidationPort().validate(event, writer)[0] is accepted
    assert (
        type(calls[0]) is ValidateUndoToken
        and calls[0].event is event
        and calls[0].writer is writer
    )
    writer._close()


@pytest.mark.parametrize(
    "rows",
    [
        ((1, None),),
        ((True, "bad"),),
        ((False, None),),
        ((False, "fixed rejection"),),
        (),
        ((True,),),
    ],
)
def test_content_response_corruption_not_success(rows):
    """bool/intや余剰/欠落を成功へ補完しない。"""
    writer = _issue_port_writer(lambda _: TenantOperationResult(rows))
    with pytest.raises(RuntimeError):
        UndoContentValidationPort().validate(wire_event(CASES["undoEvents"][0]), writer)
    writer._close()


@pytest.mark.parametrize("rows", [((1,),), ((False,),), (), ((True, True),)])
def test_projection_only_real_boolean(rows):
    """SQLの一回完了bool以外をPortで拒否する。"""
    writer = _issue_port_writer(lambda _: TenantOperationResult(rows))
    with pytest.raises(RuntimeError):
        UndoProjectionPort().apply(wire_event(CASES["undoEvents"][0]), writer)
    writer._close()


def test_direct_port_command_without_actual_frame_is_rejected(rig):
    """registryの採用有無に依存せず、未発行frameを成功にしない。"""
    from pitchlog.sync.undo_execution import _undo_content_result

    with pytest.raises(RuntimeError):
        _undo_content_result(rig.handle, rig.event, rig.writer)


@pytest.mark.parametrize("rejected", [False, True])
def test_actual_content_hook_result_reaches_actual_port_without_conversion(
    rig, monkeypatch, rejected
):
    """実hook値を2列へ包むだけで実Portへ通す。正式registry/PG成功ではない。"""
    import json
    from types import SimpleNamespace

    from pitchlog.domainrt.first_ball_projection import _canonical_json
    from pitchlog.repositories import transaction as tx
    from pitchlog.sync import undo_execution as execution
    from pitchlog.sync.idempotency import _json_value, event_source
    from pitchlog.sync.wire_fingerprint import freeze_wire_event, wire_event_fingerprint

    if rejected:
        rig.raw["payload"]["expectedCheckpoint"]["revision"] = "1"
        rig.event = wire_event(rig.raw)
        rig.source.event = rig.event
        wire = freeze_wire_event(
            json.loads(_canonical_json(_json_value(event_source(rig.event))))
        )
        rig.view.wire_event, rig.view.event_fingerprint = (
            wire,
            wire_event_fingerprint(wire),
        )
    original_run = tx._TenantTransaction.run
    seen = []

    def dispatch(handle, token):
        if type(token) is not ValidateUndoToken:
            return original_run(handle, token)
        assert token.game_id == rig.lease.game_id and str(token.d5) == rig.event.d5
        assert token.event is rig.event and token.writer is rig.writer
        value = execution._undo_content_result(handle, token.event, token.writer)
        assert type(value) is tuple and len(value) == 2
        seen.append(value)
        # bool→理由の便宜変換はせず、実hookの同じtupleを運ぶ。
        return TenantOperationResult((value,))

    monkeypatch.setattr(tx._TenantTransaction, "run", dispatch)
    rig.writer._close()
    rig.writer = _issue_port_writer(rig.handle.run)
    with execution._bind_undo_execution(rig.handle, rig.writer, rig.event, rig.source):
        phase = SimpleNamespace(
            kind="content",
            handle=rig.handle,
            bound=rig.source.bound,
            snapshot=rig.source.bound._phase_snapshot,
        )
        with monkeypatch.context() as m:
            m.setattr(tx, "_port_phase", lambda _: phase)
            actual = UndoContentValidationPort().validate(rig.event, rig.writer)
            expected = (
                (False, _UNDO_CONTENT_REJECTION_REASON) if rejected else (True, None)
            )
            assert actual == expected and seen == [expected]
            wrong_phase = SimpleNamespace(**{**vars(phase), "kind": "device"})
            m.setattr(tx, "_port_phase", lambda _: wrong_phase)
            with pytest.raises(execution.UndoExecutionError):
                UndoContentValidationPort().validate(rig.event, rig.writer)
            m.setattr(tx, "_port_phase", lambda _: phase)
            rig.writer._close()
            with pytest.raises(RuntimeError):
                UndoContentValidationPort().validate(rig.event, rig.writer)
