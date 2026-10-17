"""D1 付きイベントの参加区分から P1/P2 の経路を決める。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from pitchlog.sync.model import SyncEvent
from pitchlog.sync.prefix_path import _P2_LOGICAL_KINDS

type EventPath = Literal["P1", "P2"]


def route_for_event(
    event: SyncEvent, original_path: EventPath | None = None
) -> EventPath:
    """正本 8-1 の参加区分で経路を返す。改訂版は不変な原本の経路を継ぐ。"""
    if isinstance(event.v9, Mapping):
        if event.v9.get("tombstone") is True:
            return "P1"
        if event.v9.get("revision") is True and original_path is not None:
            return original_path
    return "P2" if type(event.v5) is str and event.v5 in _P2_LOGICAL_KINDS else "P1"
