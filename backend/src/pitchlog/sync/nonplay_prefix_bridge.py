"""取消の一回frameを同TXの固定prepare/consumeへ橋渡しする。"""

from __future__ import annotations

from contextlib import contextmanager

from pitchlog.domainrt.first_ball_projection import _canonical_json
from pitchlog.repositories.nonplay_prefix import (
    _ConsumeNonplayUndo,
    _PrepareNonplayUndo,
    _read_prefix,
    _run,
)
from pitchlog.sync.idempotency import _json_value, source_fingerprint
from pitchlog.sync.undo_execution import (
    UndoExecutionError,
    _consume_undo_frame,
    _execution_live,
)
from pitchlog.sync.undo_payload import _load


def _preparation(state):
    """既host結果と真正原本を写す。Pythonで逆計算しない。"""
    before, evidence = _read_prefix(
        state.prefix, state.handle, state.source, state.event
    )
    selected = state.source.read(state.handle, state.event)
    if selected.origin != "e1" or selected.wire_event is None:
        raise UndoExecutionError("取消は真正E1原本だけを使用します")
    original = _json_value(selected.wire_event.wire_event)
    prior = before["checkpoint"]
    content = _load(_canonical_json(prior["content"]))
    tail = before["activeStack"][1:]
    event_source = {
        "eventId": str(state.event_id),
        "gameId": state.event.game_id,
        "generation": state.event.d4,
        "d1": str(state.event.d1),
        "d5": state.event.d5,
        "fingerprint": selected.event_fingerprint,
        "eventKind": "undo",
    }
    content.update(
        d3=str(state.event.d1),
        d1Head={"kind": "accepted-event", "source": event_source},
        projectionHead={"kind": "d1-event", "source": event_source},
        activeHead=tail[0]["play"] if tail else None,
        activeDepth=str(len(tail)),
        historyVersion=str(int(content["historyVersion"]) + 1),
        restored=before["activeStack"][0]["beforeContext"],
    )
    after = {
        "formatVersion": "nonplay-prefix-source-v1",
        "checkpoint": {
            "formatVersion": "nonplay-prefix-checkpoint-v1",
            "ref": {
                "id": prior["ref"]["id"],
                "revision": str(int(prior["ref"]["revision"]) + 1),
                "digest": source_fingerprint(content),
            },
            "content": content,
        },
        "activeStack": tail,
    }
    preparation = {
        "frame_id": str(state.frame_id),
        "event_id": str(state.event_id),
        "artifact_sha256": state.artifact,
        "event_original": original,
        "source_fingerprint": selected.event_fingerprint,
        "before_source": before,
        "after_source": after,
        "storage": evidence["storage"],
        "target": before["activeStack"][0]["play"],
        "response": state.response.to_wire(),
    }
    preparation["frame_digest"] = source_fingerprint(preparation)
    return preparation


_WRITE_CALLS = {}


def _assert_undo_write_call(handle, operation):
    """私有frameを消費したbridge区間以外のprepare/consumeをSQL0で拒否する。"""
    loan = _WRITE_CALLS.get(handle._state_key)
    if loan is None or loan[1] is not operation or loan[2] is not False:
        raise UndoExecutionError("取消write資格が未発行又は消費済みです")
    state, token, _used, raw = loan
    _execution_live(state)
    if (
        state.handle is not handle
        or state.phase != "consumed"
        or state.projection_call is None
        or token.request_json != raw
    ):
        raise UndoExecutionError("取消writeのframe/全bindが不一致です")


def _consume_undo_write_call(handle, operation):
    """Root dispatcherが固定SQLより前に一回だけ消費する。"""
    _assert_undo_write_call(handle, operation)
    _WRITE_CALLS[handle._state_key][2] = True


@contextmanager
def _write_call(state, token):
    """実bridgeの同state/同tokenへ一回貸与する。"""
    key = state.handle._state_key
    if key in _WRITE_CALLS:
        raise UndoExecutionError("取消write再入です")
    loan = [state, token, False, token.request_json]
    _WRITE_CALLS[key] = loan
    try:
        yield
        if loan[2] is not True:
            raise UndoExecutionError("取消write資格が消費されていません")
    finally:
        if _WRITE_CALLS.get(key) is loan:
            del _WRITE_CALLS[key]


def _true_row(rows):
    """bool/int同値を成功へ通さない。"""
    return (
        type(rows) is tuple
        and len(rows) == 1
        and type(rows[0]) is tuple
        and len(rows[0]) == 1
        and type(rows[0][0]) is bool
        and rows[0][0] is True
    )


def project_nonplay_undo(handle, event, writer):
    """同projection区間のframeを一回消費し、実DB応答のみを成功にする。"""
    state = _consume_undo_frame(handle, event, writer)
    preparation = _preparation(state)
    raw = _canonical_json(preparation)
    _execution_live(state)
    token = _PrepareNonplayUndo(raw)
    with _write_call(state, token):
        rows = _run(handle, state.source, state.event, token)
    if not _true_row(rows):
        raise UndoExecutionError("取消の独立DB資格を確認できません")
    _execution_live(state)
    token = _ConsumeNonplayUndo(raw)
    with _write_call(state, token):
        rows = _run(handle, state.source, state.event, token)
    from pitchlog.sync.stats_native_flush import _bind_undo_stats_receipt

    _bind_undo_stats_receipt(state, preparation, rows)
    _execution_live(state)
    state.phase = "projected"
