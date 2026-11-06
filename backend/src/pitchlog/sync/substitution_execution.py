"""交代の真正E1原本を同writer/一回hostで評価する。"""

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
from pitchlog.sync.idempotency import _json_value, event_source, source_fingerprint
from pitchlog.sync.model import SyncEvent
from pitchlog.sync.ports import PortWriter
from pitchlog.sync.source_binding import _E1CoreSource
from pitchlog.sync.substitution_payload import read_substitution_event
from pitchlog.sync.substitution_projection import build_substitution_source
from pitchlog.sync.substitution_roster import read_eligible_incoming
from pitchlog.sync.undo_payload import _load


class SubstitutionExecutionError(RuntimeError):
    """交代の不明な原本・実評価・保存資格を成功に写さない。"""


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
        raise SubstitutionExecutionError("交代の同writer資格が失効しました")
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
        raise SubstitutionExecutionError("交代の実評価済み原本が変更されました")


@contextmanager
def bind_substitution_execution(handle, writer, event, source):
    """D5/権利/順序後に唯一readerとhostで交代1件だけを評価する。"""
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
        raise SubstitutionExecutionError("交代の発行入口が不一致です")
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
            payload = read_substitution_event(event)
            selected = source.read(handle, event)
            if (
                selected.origin != "e1"
                or selected.wire_event is None
                or _canonical_json(_json_value(selected.wire_event.wire_event))
                != _canonical_json(_json_value(event_source(event)))
            ):
                raise SubstitutionExecutionError("交代の原wireとE1元参照が不一致です")
            host = stack.enter_context(open_domain_host())
            if type(host) is not NodeDomainHost:
                raise SubstitutionExecutionError("交代の配布hostが不一致です")
            prefix = stack.enter_context(
                read_confirmed_nonplay_prefix(
                    handle, event, source, artifact_sha256=host.artifact_sha256
                )
            )
            before, evidence = _read_prefix(prefix, handle, source, event)
            cp = before["checkpoint"]
            content = cp["content"]
            stored = content["restored"].get("substitutionState")
            if stored is None:
                # 同CP行の保存名簿をdigestで束ね、唯一artifactから初期全9配置を得る。
                row = evidence["storage"]["row"]
                roster = row["roster"]
                saved_content = row["content"]
                if saved_content.get("version") == "3":
                    # v3のrosterDigestは配置値であり、実名簿の原本digestは別列。
                    if source_fingerprint(roster) != saved_content.get(
                        "roster_source_digest"
                    ):
                        raise SubstitutionExecutionError(
                            "交代の保存済み初期名簿が不一致です"
                        )
                elif saved_content.get(
                    "formatVersion"
                ) != "nonplay-prefix-checkpoint-v1" or _canonical_json(
                    saved_content
                ) != _canonical_json(cp):
                    raise SubstitutionExecutionError("交代の保存済みNP名簿が不一致です")
                side = (
                    "away"
                    if content["restored"]["current"]["stateFields"]["state.half"]
                    == "top"
                    else "home"
                )
                initial = {
                    "version": "substitution-initial-state-v1",
                    "roster": roster,
                    "attackingSide": side,
                    "runners": content["restored"]["runners"],
                }
                evaluated = _load(
                    host.call(
                        "deriveInitialSubstitutionStateV1", _canonical_json(initial)
                    )
                )
                if (
                    type(evaluated) is not dict
                    or set(evaluated) != {"ok", "value"}
                    or evaluated["ok"] is not True
                    or type(evaluated["value"]) is not dict
                ):
                    raise SubstitutionExecutionError("交代の初期配置を実評価できません")
                stored = evaluated["value"]
            eligible = read_eligible_incoming(handle, payload, stored)
            request = {
                "version": "substitution-transition-v1",
                "state": stored,
                "operation": payload.to_wire()["operation"],
                "eligibleIncomingIds": eligible,
                "restoreContext": content["restored"],
            }
            evaluated = _load(
                host.call("transitionSubstitutionV1", _canonical_json(request))
            )
            if (
                type(evaluated) is not dict
                or set(evaluated) != {"ok", "value"}
                or evaluated["ok"] is not True
                or type(evaluated["value"]) is not dict
            ):
                raise SubstitutionExecutionError("交代の配布artifact応答が不一致です")
            transition = evaluated["value"]
            _live(state)
            if (
                type(transition) is not dict
                or transition.get("ok") is not True
                or set(transition) != {"ok", "state", "warnings", "afterContext"}
            ):
                state.phase = "rejected"
            else:
                after = build_substitution_source(
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


def reserved_substitution_event_id(handle, event) -> UUID:
    """V7 UUIDを実host評価済み同scopeから元INSERTへ渡す。"""
    state = _EXECUTIONS.get(handle._state_key)
    if state is None or state.phase != "ready" or type(event) is not SyncEvent:
        raise SubstitutionExecutionError("交代の予約event idがありません")
    _live(state)
    if any(
        not _same_wire_value(getattr(state.event, field), getattr(event, field))
        for field in ("d5", "game_id", "d1", "d4", "v5", "v7", "v8", "v9", "v10", "v11")
    ):
        raise SubstitutionExecutionError("交代の元eventと確定eventが不一致です")
    return UUID(state.payload.to_wire()["eventId"])


def substitution_content_result(handle, event, writer):
    """同一内容段のhost結果だけを閉応答へ写す。"""
    state = _EXECUTIONS.get(handle._state_key)
    if state is None or state.event is not event or state.writer is not writer:
        raise SubstitutionExecutionError("交代の実評価がありません")
    _live(state)
    if state.phase == "ready":
        return True, None
    if state.phase == "rejected":
        return False, "交代内容が保存済み原本または実評価値と不一致"
    raise SubstitutionExecutionError("交代の内容段が不一致です")


def substitution_preparation(handle, event, writer) -> dict[str, object]:
    """元INSERT後に同一実評価からだけDB照合文を構成する。"""
    state = _EXECUTIONS.get(handle._state_key)
    if state is None or state.projected is not event or state.writer is not writer:
        raise SubstitutionExecutionError("交代の投影資格がありません")
    _live(state)
    if (
        state.phase != "projecting"
        or state.projection_call is None
        or not state.source.write_started
    ):
        raise SubstitutionExecutionError("交代の元INSERT前又は再利用です")
    selected = state.source.read(handle, state.event)
    state.phase = "consumed"
    return {
        "formatVersion": "nonplay-substitution-preparation-v1",
        "eventId": state.payload.to_wire()["eventId"],
        "eventOriginal": _json_value(selected.wire_event.wire_event),
        "beforeSource": state.before,
        "afterSource": state.after,
        "storage": state.evidence["storage"],
        "transition": state.transition,
    }


@contextmanager
def bind_substitution_projection(handle, writer, event, projected):
    """元eventと核投影eventの全値を同一writerへ一回だけ結ぶ。"""
    state = _EXECUTIONS.get(handle._state_key)
    if state is None or state.event is not event or state.writer is not writer:
        raise SubstitutionExecutionError("交代投影の元要求がありません")
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
        raise SubstitutionExecutionError("交代投影の全wireが不一致です")
    state.phase = "projecting"
    state.projected = projected
    state.projection_call = object()
    try:
        yield
        _live(state)
        if state.phase != "projected":
            raise SubstitutionExecutionError("交代投影の実DB完了がありません")
    finally:
        state.projected = None
        state.projection_call = None
