"""正規終了再開の同frame/同TX投影。ドメイン状態の変換はartifactだけ。"""

from __future__ import annotations

from contextlib import contextmanager

from pitchlog.domainrt.first_ball_projection import _canonical_json
from pitchlog.repositories.nonplay_prefix import _read_prefix
from pitchlog.sync.idempotency import _json_value, source_fingerprint
from pitchlog.sync.lifecycle_execution import LifecycleExecutionError
from pitchlog.sync.undo_payload import _load

_WRITE_CALLS = {}


def _context_chain_matches(before, after, anchor, bridges):
    """同active source間の全制御を順に消費し、未知隙間を一致ORで通さない。"""
    current = before
    for bridge in bridges:
        if bridge["anchorEventId"] != anchor:
            continue
        if _canonical_json(current) != _canonical_json(bridge["beforeContext"]):
            return False
        current = bridge["afterContext"]
    return _canonical_json(current) == _canonical_json(after)


def _validate_control_bridges(content):
    """閉型/全応答リンクだけ。SQLの真正consumed証拠を代替しない。"""
    from pitchlog.domainrt.game_lifecycle import LifecycleRequest, LifecycleResponse

    bridges = content.get("controlBridges", [])
    if type(bridges) is not list:
        raise ValueError("制御bridge配列が必要です")
    seen = set()
    for b in bridges:
        if type(b) is not dict or set(b) != {
            "source",
            "action",
            "anchorEventId",
            "beforeContext",
            "afterContext",
            "kernel",
            "frameId",
            "checkpointBefore",
        }:
            raise ValueError("制御bridgeの全memberが不一致です")
        source = b["source"]
        request = LifecycleRequest(_canonical_json(b["kernel"]["request"])).to_wire()
        response = LifecycleResponse(
            _canonical_json(b[("kernel")][("response")])
        ).to_wire()
        if (
            source["eventId"] in seen
            or source["gameId"] != content["scope"]["gameId"]
            or source["eventKind"]
            != {"end": "game_end_declaration", "reopen": "game_reopen"}[b["action"]]
            or request["action"] != b["action"]
            or request["event"]["eventId"] != source["eventId"]
            or request["current"] != b["beforeContext"]["current"]
            or response["ok"] is not True
            or _canonical_json(response["value"]["current"])
            != _canonical_json(b["afterContext"]["current"])
            or _canonical_json(
                {k: v for k, v in b["beforeContext"].items() if k != "current"}
            )
            != _canonical_json(
                {k: v for k, v in b["afterContext"].items() if k != "current"}
            )
        ):
            raise ValueError("制御bridgeの元event/全前後応答が不一致です")
        seen.add(source["eventId"])
    return bridges


def _preparation(state):
    """元原本/完全stackを保持し、実核の唯一応答だけを新CPへ写す。"""
    before, evidence = _read_prefix(
        state.prefix, state.handle, state.source, state.event
    )
    prior = before["checkpoint"]
    content = _load(_canonical_json(prior["content"]))
    selected = state.source.read(state.handle, state.event)
    if selected.origin != "e1" or selected.wire_event is None:
        raise LifecycleExecutionError("終了再開は真正E1原本だけを使用します")
    source = {
        "eventId": str(state.event_id),
        "gameId": state.event.game_id,
        "generation": state.event.d4,
        "d1": str(state.event.d1),
        "d5": state.event.d5,
        "fingerprint": selected.event_fingerprint,
        "eventKind": state.event.v5,
    }
    before_context = content["restored"]
    after_context = {
        **before_context,
        "current": state.response.to_wire()["value"]["current"],
    }
    anchor = content["origin"]["eventId"]
    if before["activeStack"]:
        anchor = before["activeStack"][0]["play"]["source"]["eventId"]
    bridge = {
        "source": source,
        "action": state.payload["action"],
        "anchorEventId": anchor,
        "beforeContext": before_context,
        "afterContext": after_context,
        "kernel": {
            "request": state.request.to_wire(),
            "response": state.response.to_wire(),
        },
        "frameId": str(state.frame_id),
        "checkpointBefore": prior["ref"],
    }
    content.update(
        d3=str(state.event.d1),
        d1Head={"kind": "accepted-event", "source": source},
        projectionHead={"kind": "d1-event", "source": source},
        historyVersion=str(int(content["historyVersion"]) + 1),
        restored=after_context,
        controlBridges=[*content.get("controlBridges", []), bridge],
    )
    after = {
        "formatVersion": before["formatVersion"],
        "checkpoint": {
            "formatVersion": prior["formatVersion"],
            "ref": {
                "id": prior["ref"]["id"],
                "revision": str(int(prior["ref"]["revision"]) + 1),
                "digest": source_fingerprint(content),
            },
            "content": content,
        },
        "activeStack": before["activeStack"],
    }
    preparation = {
        "frame_id": str(state.frame_id),
        "event_id": str(state.event_id),
        "receipt_id": str(state.receipt_id),
        "artifact_sha256": state.artifact,
        "event_original": _json_value(selected.wire_event.wire_event),
        "source_fingerprint": selected.event_fingerprint,
        "before_source": before,
        "after_source": after,
        "storage": evidence["storage"],
        "request": state.request.to_wire(),
        "response": state.response.to_wire(),
    }
    preparation["frame_digest"] = source_fingerprint(preparation)
    return preparation


def _assert_lifecycle_write_call(handle, operation):
    """正規投影の私有一回区間以外はSQL0で拒否する。"""
    from pitchlog.sync.lifecycle_execution import _execution_live

    loan = _WRITE_CALLS.get(handle._state_key)
    if loan is None or loan[1] is not operation or loan[2] is not False:
        raise LifecycleExecutionError("終了再開のwrite資格が未発行又は消費済みです")
    state, token, _used, raw = loan
    _execution_live(state)
    if (
        state.handle is not handle
        or state.phase != "consumed"
        or state.projection_call is None
        or token.request_json != raw
    ):
        raise LifecycleExecutionError("終了再開のwrite全値/寿命が不一致です")


def _consume_lifecycle_write_call(handle, operation):
    """実dispatcherで一回だけ消費する。"""
    _assert_lifecycle_write_call(handle, operation)
    _WRITE_CALLS[handle._state_key][2] = True


@contextmanager
def _write_call(state, token):
    key = state.handle._state_key
    if key in _WRITE_CALLS:
        raise LifecycleExecutionError("終了再開write資格の再入です")
    loan = [state, token, False, token.request_json]
    _WRITE_CALLS[key] = loan
    try:
        yield
        if loan[2] is not True:
            raise LifecycleExecutionError("終了再開write資格が消費されていません")
    finally:
        if _WRITE_CALLS.get(key) is loan:
            del _WRITE_CALLS[key]


def project_game_lifecycle(handle, event, writer):
    """同frame一回→同TX実SQL→厳密receiptだけを完了にする。"""
    from pitchlog.repositories.game_lifecycle import (
        _ConsumeLifecycle,
        _PrepareLifecycle,
        _run,
    )
    from pitchlog.sync.lifecycle_execution import (
        _consume_lifecycle_frame,
        _execution_live,
    )

    state = _consume_lifecycle_frame(handle, event, writer)
    preparation = _preparation(state)
    raw = _canonical_json(preparation)
    token = _PrepareLifecycle(raw)
    with _write_call(state, token):
        rows = _run(handle, state.source, state.event, token)
    if type(rows) is not tuple or rows != ((True,),) or type(rows[0][0]) is not bool:
        raise LifecycleExecutionError("終了再開prepareの独立DB資格が不一致です")
    _execution_live(state)
    token = _ConsumeLifecycle(raw)
    with _write_call(state, token):
        rows = _run(handle, state.source, state.event, token)
    if (
        type(rows) is not tuple
        or len(rows) != 1
        or type(rows[0]) is not tuple
        or len(rows[0]) != 1
        or type(rows[0][0]) is not str
    ):
        raise LifecycleExecutionError("終了再開の実receipt形が不一致です")
    receipt = _load(rows[0][0])
    if (
        type(receipt) is not dict
        or set(receipt)
        != {"eventId", "receiptId", "frameId", "factVersionId", "lifecycle"}
        or receipt["eventId"] != str(state.event_id)
        or receipt["receiptId"] != str(state.receipt_id)
        or receipt["frameId"] != str(state.frame_id)
        or _canonical_json(receipt["lifecycle"])
        != _canonical_json(state.response.to_wire()["value"]["lifecycle"])
    ):
        raise LifecycleExecutionError("終了再開の実receipt全bindが不一致です")
    from uuid import UUID

    if (
        type(receipt["factVersionId"]) is not str
        or str(UUID(receipt["factVersionId"])) != receipt["factVersionId"]
    ):
        raise LifecycleExecutionError("終了再開の実stats版参照が不一致です")
    _execution_live(state)
    state.phase = "projected"
