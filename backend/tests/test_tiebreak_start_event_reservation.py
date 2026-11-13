"""タイブレーク開始の元INSERTが実評価の予約eventIdだけを使うことを固定する。"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import pytest

from pitchlog.sync import prefix_path
from pitchlog.sync import tiebreak_start_execution as tiebreak
from pitchlog.sync.model import SyncEvent

_EVENT_ID = UUID("00000000-0000-4000-8000-0000000005a1")
_GAME_ID = UUID("00000000-0000-4000-8000-0000000000aa")
_D5 = "00000000-0000-4000-8000-0000000000d5"


def _event(*, event_id: UUID = _EVENT_ID) -> SyncEvent:
    """タイブレーク開始の閉じたP1入力を返す。"""
    return SyncEvent(
        _D5,
        str(_GAME_ID),
        55,
        "d4.1.synthetic",
        "tiebreak_start",
        55001,
        {
            "formatVersion": "tiebreak-start-event-v1",
            "eventId": str(event_id),
        },
    )


@dataclass
class _Payload:
    """予約eventIdだけを返す実payloadの代役。"""

    event_id: UUID

    def to_wire(self) -> dict[str, object]:
        """保存eventと同じeventId値だけを公開する。"""
        return {"eventId": str(self.event_id)}


@dataclass
class _State:
    """予約検査に必要な実評価状態だけを持つ。"""

    event: SyncEvent
    payload: _Payload
    phase: str = "ready"


@dataclass
class _Handle:
    """予約台帳のkeyだけを持つscopeの代役。"""

    _state_key: object


def test_event_insert_uses_reserved_tiebreak_event_id(monkeypatch):
    """元INSERTが乱数uuid4ではなく実評価済みeventIdを使う。"""
    reserved = UUID("00000000-0000-4000-8000-0000000005b2")
    random_id = UUID("00000000-0000-4000-8000-0000000005c3")
    monkeypatch.setattr(
        tiebreak, "reserved_tiebreak_start_event_id", lambda *_: reserved
    )
    monkeypatch.setattr(prefix_path, "uuid4", lambda: random_id)
    token = prefix_path._event_insert_token(
        _event(),
        _GAME_ID,
        1,
        "none",
        "{}",
        None,
        scope=object(),
    )
    assert token.id == reserved
    assert token.id != random_id
    assert token.event_kind == "tiebreak_start"


def test_reserved_tiebreak_event_id_rejects_changed_projection(monkeypatch):
    """元eventと別eventIdの投影を予約IDとして受理しない。"""
    state = _State(_event(), _Payload(_EVENT_ID))
    monkeypatch.setattr(tiebreak, "_live", lambda _state: None)
    key = object()
    monkeypatch.setitem(tiebreak._EXECUTIONS, key, state)
    handle = _Handle(key)
    try:
        reserved = tiebreak.reserved_tiebreak_start_event_id(handle, state.event)
        assert reserved == _EVENT_ID
        changed = _event(event_id=UUID(int=0x5d4))
        with pytest.raises(tiebreak.TiebreakStartExecutionError):
            tiebreak.reserved_tiebreak_start_event_id(handle, changed)
    finally:
        tiebreak._EXECUTIONS.pop(key, None)
