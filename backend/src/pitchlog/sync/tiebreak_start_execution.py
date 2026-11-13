"""タイブレーク開始の真正E1原本を同writer/一回hostで評価する。"""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from pitchlog.domainrt.first_ball_projection import _canonical_json
from pitchlog.domainrt.host import NodeDomainHost, open_domain_host
from pitchlog.repositories import transaction
from pitchlog.repositories.nonplay_prefix import (
    _read_prefix,
    read_confirmed_nonplay_prefix,
)
from pitchlog.sync.first_ball_execution import _same_wire_value
from pitchlog.sync.idempotency import _json_value, event_source
from pitchlog.sync.model import SyncEvent
from pitchlog.sync.ports import PortWriter
from pitchlog.sync.source_binding import _E1CoreSource
from pitchlog.sync.tiebreak_start_payload import read_tiebreak_start_event
from pitchlog.sync.tiebreak_start_projection import build_tiebreak_start_source
from pitchlog.sync.undo_payload import _load


class TiebreakStartExecutionError(RuntimeError):
    """タイブレーク開始の不明な原本・実評価・保存資格を成功に写さない。"""


@dataclass(slots=True, repr=False)
class _Execution:
    handle: Any
    writer: PortWriter
    source: _E1CoreSource
    event: SyncEvent
    runtime: object
    lifetime: tuple
    phase: str = "reading"
    prefix: Any = None
    payload: Any = None
    transition: Any = None
    before: Any = None
    after: Any = None
    evidence: Any = None
    fingerprint: str | None = None
    artifact: str | None = None
    frame: object = None
    anchor: tuple | None = None
    projected: SyncEvent | None = None
    projection_call: object = None


_EXECUTIONS: dict[object, _Execution] = {}


def _live(state: _Execution) -> None:
    """E1と同じ実Session・単一writer・top TXの寿命を再確認する。"""
    handle = state.handle
    if (
        type(handle) is not transaction._TenantTransaction
        or _EXECUTIONS.get(handle._state_key) is not state
        or type(state.writer) is not PortWriter
        or state.writer._active is not True
        or getattr(state.writer._execute, "__self__", None) is not handle
        or getattr(state.writer._execute, "__func__", None)
        is not transaction._TenantTransaction.run
        or transaction._TRANSACTION_RUNTIMES.get(handle._state_key) is not state.runtime
        or transaction._SYNC_APPLY_ACTIVE.get() is not True
        or state.source.scope is not handle
        or state.source.event is not state.event
    ):
        raise TiebreakStartExecutionError(
            "タイブレーク開始の同writer資格が失効しました"
        )
    handle._assert_writer_lifetime(state.lifetime)
    state.source.read(handle, state.event)
    handle._assert_writer_lifetime(state.lifetime)
    if state.anchor is not None and (
        state.frame is not state.anchor[0]
        or state.prefix is not state.anchor[1]
        or state.payload is not state.anchor[2]
        or state.artifact != state.anchor[3]
        or _canonical_json(state.before) != state.anchor[4]
        or _canonical_json(state.after) != state.anchor[5]
        or _canonical_json(state.transition) != state.anchor[6]
    ):
        raise TiebreakStartExecutionError(
            "タイブレーク開始の実評価済み原本が変更されました"
        )


def _active_player_ids(restored: dict[str, Any]) -> list[str]:
    """現半回の攻撃側打順に登録された実選手IDだけを返す。"""
    current = restored.get("current")
    lineup = restored.get("lineup")
    if type(current) is not dict or type(lineup) is not dict:
        raise TiebreakStartExecutionError("タイブレーク開始の復元文脈が不一致です")
    fields = current.get("stateFields")
    if type(fields) is not dict:
        raise TiebreakStartExecutionError("タイブレーク開始の状態が不一致です")
    side = "away" if fields.get("state.half") == "top" else "home"
    team = lineup.get(side)
    if type(team) is not dict:
        raise TiebreakStartExecutionError("タイブレーク開始の攻撃側名簿が不一致です")
    order = team.get("battingOrder")
    if type(order) is not dict:
        raise TiebreakStartExecutionError("タイブレーク開始の打順が不一致です")
    players: list[str] = []
    for value in order.values():
        if type(value) is not str:
            raise TiebreakStartExecutionError("タイブレーク開始の選手IDが不一致です")
        players.append(value)
    return players


def _rule(restored: dict[str, Any]) -> dict[str, Any]:
    """保存規則snapshotのタイブレーク3値だけを返す。"""
    rules = restored.get("rules")
    if type(rules) is not dict:
        raise TiebreakStartExecutionError("タイブレーク開始の規則snapshotがありません")
    tiebreak = rules.get("tiebreak")
    if type(tiebreak) is not dict:
        raise TiebreakStartExecutionError("この試合にはタイブレーク規則がありません")
    if set(tiebreak) != {"startInning", "runnerPlacement", "leadoffRule"}:
        raise TiebreakStartExecutionError("タイブレーク規則の形が不一致です")
    return tiebreak


@contextmanager
def bind_tiebreak_start_execution(handle, writer, event, source):
    """D5/権利/順序後に唯一readerとhostでタイブレーク開始1件だけを評価する。"""
    if (
        type(handle) is not transaction._TenantTransaction
        or type(writer) is not PortWriter
        or type(event) is not SyncEvent
        or type(source) is not _E1CoreSource
        or source.scope is not handle
        or source.event is not event
        or source.write_started
        or handle._state_key in _EXECUTIONS
    ):
        raise TiebreakStartExecutionError("タイブレーク開始の発行入口が不一致です")
    state = _Execution(
        handle,
        writer,
        source,
        event,
        transaction._TRANSACTION_RUNTIMES.get(handle._state_key),
        handle._writer_lifetime(),
    )
    _EXECUTIONS[handle._state_key] = state
    try:
        with ExitStack() as stack:
            _live(state)
            payload = read_tiebreak_start_event(event)
            selected = source.read(handle, event)
            if (
                selected.origin != "e1"
                or selected.wire_event is None
                or _canonical_json(_json_value(selected.wire_event.wire_event))
                != _canonical_json(_json_value(event_source(event)))
            ):
                raise TiebreakStartExecutionError(
                    "タイブレーク開始の原wireとE1元参照が不一致です"
                )
            host = stack.enter_context(open_domain_host())
            if type(host) is not NodeDomainHost:
                raise TiebreakStartExecutionError(
                    "タイブレーク開始の配布hostが不一致です"
                )
            prefix = stack.enter_context(
                read_confirmed_nonplay_prefix(
                    handle, event, source, artifact_sha256=host.artifact_sha256
                )
            )
            before, evidence = _read_prefix(prefix, handle, source, event)
            content = before["checkpoint"]["content"]
            restored = content.get("restored")
            if type(restored) is not dict:
                raise TiebreakStartExecutionError(
                    "タイブレーク開始の復元文脈がありません"
                )
            rule = _rule(restored)
            active = _active_player_ids(restored)
            frames = content.get("tiebreakFrames", [])
            last_placement = None
            if frames:
                last_fields = frames[-1]["afterContext"]["current"]["stateFields"]
                last_placement = {
                    "inning": str(last_fields["state.inning"]),
                    "half": str(last_fields["state.half"]),
                }
            request = {
                "version": "tiebreak-start-v1",
                "restoreContext": restored,
                "rule": rule,
                "selection": {
                    "firstRunnerId": payload.first_runner_id,
                    "secondRunnerId": payload.second_runner_id,
                },
                "activePlayerIds": active,
            }
            if last_placement is not None:
                request["lastPlacementHalf"] = last_placement
            evaluated = _load(
                host.call("transitionTiebreakStartV1", _canonical_json(request))
            )
            if type(evaluated) is not dict or set(evaluated) != {"ok", "value"}:
                raise TiebreakStartExecutionError(
                    "タイブレーク開始の配布artifact応答が不一致です"
                )
            _live(state)
            if evaluated["ok"] is not True:
                state.phase = "rejected"
            else:
                transition = evaluated["value"]
                after = build_tiebreak_start_source(
                    before,
                    event,
                    fingerprint=selected.event_fingerprint,
                    artifact_sha256=host.artifact_sha256,
                    transition=transition,
                )
                state.prefix = prefix
                state.payload = payload
                state.transition = transition
                state.before = before
                state.after = after
                state.evidence = evidence
                state.fingerprint = selected.event_fingerprint
                state.artifact = host.artifact_sha256
                state.frame = object()
                state.anchor = (
                    state.frame,
                    state.prefix,
                    state.payload,
                    state.artifact,
                    _canonical_json(state.before),
                    _canonical_json(state.after),
                    _canonical_json(state.transition),
                )
                state.phase = "ready"
            _live(state)
            yield
    finally:
        if _EXECUTIONS.get(handle._state_key) is state:
            del _EXECUTIONS[handle._state_key]
        state.phase = "closed"
        state.prefix = state.payload = state.transition = None
        state.before = state.after = state.evidence = None
        state.frame = state.anchor = None


def reserved_tiebreak_start_event_id(handle, event) -> UUID:
    """V7 UUIDを実host評価済み同scopeから元INSERTへ渡す。"""
    state = _EXECUTIONS.get(handle._state_key)
    if state is None or state.phase != "ready" or type(event) is not SyncEvent:
        raise TiebreakStartExecutionError("タイブレーク開始の予約event idがありません")
    _live(state)
    if any(
        not _same_wire_value(getattr(state.event, field), getattr(event, field))
        for field in ("d5", "game_id", "d1", "d4", "v5", "v7", "v8", "v9", "v10", "v11")
    ):
        raise TiebreakStartExecutionError(
            "タイブレーク開始の元eventと確定eventが不一致です"
        )
    return UUID(state.payload.to_wire()["eventId"])


def tiebreak_start_content_result(handle, event, writer):
    """同一内容段のhost結果だけを閉応答へ写す。"""
    state = _EXECUTIONS.get(handle._state_key)
    if state is None or state.event is not event or state.writer is not writer:
        raise TiebreakStartExecutionError("タイブレーク開始の実評価がありません")
    _live(state)
    if state.phase == "ready":
        return True, None
    if state.phase == "rejected":
        return False, "タイブレーク開始内容が保存済み原本または実評価値と不一致"
    raise TiebreakStartExecutionError("タイブレーク開始の内容段が不一致です")


def tiebreak_start_preparation(handle, event, writer) -> dict[str, object]:
    """元INSERT後に同一実評価からだけDB照合文を構成する。"""
    state = _EXECUTIONS.get(handle._state_key)
    if state is None or state.projected is not event or state.writer is not writer:
        raise TiebreakStartExecutionError("タイブレーク開始の投影資格がありません")
    _live(state)
    if (
        state.phase != "projecting"
        or state.projection_call is None
        or not state.source.write_started
    ):
        raise TiebreakStartExecutionError("タイブレーク開始の元INSERT前又は再利用です")
    selected = state.source.read(handle, state.event)
    state.phase = "consumed"
    return {
        "formatVersion": "nonplay-tiebreak-start-preparation-v1",
        "eventId": state.payload.to_wire()["eventId"],
        "eventOriginal": _json_value(selected.wire_event.wire_event),
        "beforeSource": state.before,
        "afterSource": state.after,
        "storage": state.evidence["storage"],
        "transition": state.transition,
    }


@contextmanager
def bind_tiebreak_start_projection(handle, writer, event, projected):
    """元eventと核投影eventの全値を同一writerへ一回だけ結ぶ。"""
    state = _EXECUTIONS.get(handle._state_key)
    if state is None or state.event is not event or state.writer is not writer:
        raise TiebreakStartExecutionError("タイブレーク開始投影の元要求がありません")
    _live(state)
    if (
        state.phase != "ready"
        or not state.source.write_started
        or type(projected) is not SyncEvent
        or any(
            not _same_wire_value(getattr(event, field), getattr(projected, field))
            for field in (
                "d5",
                "game_id",
                "d1",
                "d4",
                "v5",
                "v7",
                "v8",
                "v9",
                "v10",
                "v11",
            )
        )
    ):
        raise TiebreakStartExecutionError("タイブレーク開始投影の全wireが不一致です")
    state.phase = "projecting"
    state.projected = projected
    state.projection_call = object()
    try:
        yield
        _live(state)
        if state.phase != "projected":
            raise TiebreakStartExecutionError(
                "タイブレーク開始投影の実DB完了がありません"
            )
    finally:
        state.projected = None
        state.projection_call = None
