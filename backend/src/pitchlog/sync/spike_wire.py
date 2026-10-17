"""spike 用の要求本文を同期核の S-1 型へ変換する。

設計書は参加区分を種別番号の文字列で運び、backend の同期核は
`event_kinds.py` の literal を要求する。この変換層は「数字文字列 → literal」と
「literal → literal」の両方を受け、未知の形は S-1 違反
（`RequestShapeError`）として候補分類の前に拒否する。外形検査の本体は
`SyncRequest.from_payload` が所有し、このモジュールは写像だけを行う。
"""

from __future__ import annotations

from collections.abc import Mapping

from pitchlog.db.sync_protocol.event_kinds import EVENT_KIND_BY_NUMBER
from pitchlog.sync.model import ApplicationPath, RequestShapeError, SyncRequest

# 種別番号文字列から literal への写像は正本（event_kinds.py）から導出する。
# 墓標（8）と改訂版（9）は V5 を持たないため正本の表に含まれない。
# literal 側は既知の集合だけを通す。
_NUMBER_TO_KIND: Mapping[str, str] = EVENT_KIND_BY_NUMBER
_KIND_LITERALS: frozenset[str] = frozenset(EVENT_KIND_BY_NUMBER.values())


def _event_kind_value(value: object) -> object:
    """種別の数字文字列を literal へ写し、既知の literal はそのまま渡す。"""
    if type(value) is not str or not value:
        raise RequestShapeError("S-1: event_kind は既知の番号か literal の文字列が必要")
    if value in _KIND_LITERALS:
        return value
    literal = _NUMBER_TO_KIND.get(value)
    if literal is None:
        raise RequestShapeError("S-1: event_kind が既知の番号でも literal でもない")
    return literal


def _event_with_mapped_kind(
    item: Mapping[str, object], kind_field: str
) -> dict[str, object]:
    """1 イベント文の V5 だけを backend の literal へ写す。"""
    event: dict[str, object] = dict(item)
    if kind_field in event:
        event[kind_field] = _event_kind_value(event[kind_field])
    return event


def _normalized_payload(payload: object) -> object:
    """本文の event_kind だけを写像する。それ以外の形は from_payload へ渡す。"""
    if not isinstance(payload, Mapping):
        return payload
    normalized = dict(payload)
    events = payload.get("events")
    if isinstance(events, list):
        normalized["events"] = [
            _event_with_mapped_kind(item, "event_kind")
            if isinstance(item, Mapping)
            else item
            for item in events
        ]
    change = payload.get("change")
    if isinstance(change, Mapping):
        normalized["change"] = _event_with_mapped_kind(change, "event_kind")
    return normalized


def to_sync_request(
    path: ApplicationPath, game_id: str, payload: object
) -> SyncRequest:
    """URL の経路・試合と本文から S-1 を満たす同期要求を作る。

    Args:
        path: D1 付き経路の種別。spike の 1 球入口は P1 を渡す。
        game_id: URL で確定した試合 ID の正規文字列。
        payload: JSON 本文。`event_kind` は番号文字列でも literal でもよい。

    Returns:
        S-1 を満たす `SyncRequest`。

    Raises:
        RequestShapeError: 外形が S-1 を満たさない。HTTP 入口が 422 へ写す。
    """
    return SyncRequest.from_payload(path, game_id, _normalized_payload(payload))
