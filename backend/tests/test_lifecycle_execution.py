"""値一致だけで実phase/同TX/一回frameを発行できないことを検査する。"""

from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import pytest

from pitchlog.repositories.function_operations import FunctionOperationError
from pitchlog.repositories.game_lifecycle import _finished_lifecycle_read_allowed
from pitchlog.repositories.lifecycle_function_operations import (
    LIFECYCLE_FUNCTION_OPERATIONS,
    _ConsumeLifecycleCall,
    _decode,
    _PrepareLifecycleCall,
    _private_decoder,
    _ReadLifecycleStateCall,
    validate_registration,
)
from pitchlog.repositories.lifecycle_qualification import (
    BindLifecycleDeviceToken,
    CheckLifecycleRightToken,
)
from pitchlog.sync.lifecycle_execution import (
    LifecycleExecutionError,
    LifecycleFrame,
    _bind_lifecycle_execution,
    _resolve_lifecycle_references,
)
from pitchlog.sync.lifecycle_payload import LifecyclePayloadError
from pitchlog.sync.lifecycle_prefix_bridge import _assert_lifecycle_write_call
from pitchlog.sync.model import SyncEvent

_GAME = "10000000-0000-0000-0000-000000000001"
_END = "10000000-0000-0000-0000-000000000002"
_RECEIPT = "20000000-0000-0000-0000-000000000002"
_D5 = "30000000-0000-0000-0000-000000000002"


def test_reserved_id_accepts_only_same_scope_and_all_eleven_wire_fields(monkeypatch):
    """核が作る同値cloneを通し、全11列の一箇所改変を拒否する。"""
    from pitchlog.sync import lifecycle_execution as execution

    names = execution._LIFECYCLE_EVENT_FIELDS
    raw = (
        _D5,
        _GAME,
        2,
        "generation-1",
        "game_end_declaration",
        None,
        {"kind": "end"},
        {"result": True},
        "memo",
        {"target": None},
        1,
    )
    original = SyncEvent(*raw)
    handle = SimpleNamespace(_state_key=object())
    state = SimpleNamespace(event=original, phase="ready", event_id=UUID(_END))
    monkeypatch.setitem(execution._EXECUTIONS, handle._state_key, state)
    monkeypatch.setattr(execution, "_execution_live", lambda _state: None)
    assert execution._reserved_lifecycle_event_id(handle, SyncEvent(*raw)) == UUID(_END)
    changes = (
        "40000000-0000-0000-0000-000000000002",
        "50000000-0000-0000-0000-000000000002",
        3,
        "generation-2",
        "game_reopen",
        0,
        {"kind": "reopen"},
        {"result": False},
        "other",
        {"target": "other"},
        2,
    )
    assert len(names) == len(raw) == len(changes) == 11
    for index, name in enumerate(names):
        altered = list(raw)
        altered[index] = changes[index]
        with pytest.raises(LifecycleExecutionError, match="予約原本id"):
            execution._reserved_lifecycle_event_id(
                handle, SyncEvent(*cast(Any, altered))
            )
    state.phase = "closed"
    with pytest.raises(LifecycleExecutionError, match="予約原本id"):
        execution._reserved_lifecycle_event_id(handle, SyncEvent(*raw))
    with pytest.raises(LifecycleExecutionError, match="未発行"):
        execution._reserved_lifecycle_event_id(
            SimpleNamespace(_state_key=object()), original
        )


def _accepted_end():
    """CP更新後の終端と実制御bridgeを独立値で構成する。"""
    source = {
        "eventId": _END,
        "gameId": _GAME,
        "generation": "owned-d4",
        "d1": "2",
        "d5": _D5,
    }
    before = {"id": _GAME, "revision": "1", "digest": "a" * 64}
    active = {"version": "1", "eventId": _END, "receiptId": _RECEIPT}
    bridge = {
        "source": source,
        "action": "end",
        "checkpointBefore": before,
        "kernel": {
            "request": {"event": {"eventId": _END, "receiptId": _RECEIPT}},
            "response": {"value": {"lifecycle": {"active": active}}},
        },
    }
    checkpoint = {
        "ref": {"id": _GAME, "revision": "2", "digest": "b" * 64},
        "content": {
            "d3": "2",
            "d1Head": {"source": source},
            "controlBridges": [bridge],
        },
    }
    event = SimpleNamespace(game_id=_GAME, d4="owned-d4", d1=3)
    lifecycle = {"active": active}
    return checkpoint, event, lifecycle


@pytest.mark.parametrize(
    "kind", ["confirmed", "confirmed_prefix", "queued_predecessor"]
)
@pytest.mark.parametrize("target_kind", ["confirmed", "queued_end"])
def test_accepted_predecessor_and_end_resolve_only_from_saved_values(kind, target_kind):
    """予約位置を先行の実受理終端と終了版へ束縛する。"""
    checkpoint, event, lifecycle = _accepted_end()
    source = checkpoint["content"]["d1Head"]["source"]
    position = {"d4": source["generation"], "d1": 2, "d5": _D5}
    if kind == "confirmed":
        ref = {"kind": kind, **checkpoint["ref"]}
    elif kind == "confirmed_prefix":
        ref = {
            "kind": kind,
            **checkpoint["content"]["controlBridges"][-1]["checkpointBefore"],
            **position,
        }
    else:
        ref = {"kind": kind, **position}
    if target_kind == "confirmed":
        target = {"kind": target_kind, **lifecycle["active"]}
    else:
        target = {
            "kind": target_kind,
            **position,
            "eventId": _END,
            "receiptId": _RECEIPT,
        }
    payload = {"action": "reopen", "checkpointRef": ref, "target": target}
    assert (
        _resolve_lifecycle_references(payload, checkpoint, lifecycle, event)
        == lifecycle["active"]
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "wrong-d1",
        "wrong-d4",
        "wrong-d5",
        "missing-end",
        "wrong-receipt",
        "wrong-version",
    ],
)
def test_reserved_predecessor_never_becomes_confirmed_without_matching_receipt(
    mutation,
):
    """未成立・別予約・別版を現在のCPや版へ補修しない。"""
    checkpoint, event, lifecycle = _accepted_end()
    checkpoint_ref: dict[str, str | int] = {
        "kind": "queued_predecessor",
        "d4": "owned-d4",
        "d1": 2,
        "d5": _D5,
    }
    end_target: dict[str, str | int] = {
        "kind": "queued_end",
        "d4": "owned-d4",
        "d1": 2,
        "d5": _D5,
        "eventId": _END,
        "receiptId": _RECEIPT,
    }
    payload = {
        "action": "reopen",
        "checkpointRef": checkpoint_ref,
        "target": end_target,
    }
    if mutation == "wrong-d1":
        checkpoint_ref["d1"] = 1
    elif mutation == "wrong-d4":
        checkpoint_ref["d4"] = "another-d4"
    elif mutation == "wrong-d5":
        checkpoint_ref["d5"] = _GAME
    elif mutation == "missing-end":
        checkpoint["content"]["controlBridges"] = []
    elif mutation == "wrong-receipt":
        end_target["receiptId"] = _GAME
    else:
        lifecycle["active"] = dict(lifecycle["active"])
        lifecycle["active"]["version"] = "2"
    with pytest.raises(LifecyclePayloadError):
        _resolve_lifecycle_references(payload, checkpoint, lifecycle, event)


@pytest.mark.parametrize(
    "token",
    [
        LifecycleFrame,
        _ReadLifecycleStateCall,
        _PrepareLifecycleCall,
        _ConsumeLifecycleCall,
        BindLifecycleDeviceToken,
        CheckLifecycleRightToken,
    ],
)
def test_private_frame_and_metadata_cannot_be_fabricated(token):
    """閉じた型と同値条件を検査する。"""
    with pytest.raises((FunctionOperationError, LifecycleExecutionError)):
        token()


def test_generic_decoder_cannot_elevate_metadata():
    """閉じた型と同値条件を検査する。"""
    for spec in LIFECYCLE_FUNCTION_OPERATIONS:
        validate_registration(spec)
    with pytest.raises(FunctionOperationError):
        _private_decoder(((True,),))


def test_prepare_requires_actual_bool_true():
    """閉じた型と同値条件を検査する。"""
    spec = next(
        s
        for s in LIFECYCLE_FUNCTION_OPERATIONS
        if s.token_type is _PrepareLifecycleCall
    )
    assert _decode(spec, ((True,),)).rows == ((True,),)
    for value in [(), ((False,),), ((1,),), [[True]], ((True, True),)]:
        with pytest.raises(FunctionOperationError):
            _decode(spec, value)


def test_free_values_cannot_enter_execution_or_write():
    """閉じた型と同値条件を検査する。"""
    fake = SimpleNamespace(_state_key=object())
    with pytest.raises(LifecycleExecutionError):
        with _bind_lifecycle_execution(fake, object(), object(), object()):
            pytest.fail("実E1なしで実行区間へ入ってはいけません")
    with pytest.raises(LifecycleExecutionError):
        _assert_lifecycle_write_call(fake, object())
    assert _finished_lifecycle_read_allowed(fake, object()) is False
