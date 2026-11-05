"""取消の接続spikeから正式 artifact の ``applyUndo`` を呼ぶ合成部品。

ポート実装の静的検査対象ではない。ポートには callable として注入し、
ポート自身は host/json を import しない。
"""

from __future__ import annotations

import json
from collections.abc import Mapping

from pitchlog.domainrt.host import open_domain_host


def _plain(value: object) -> object:
    """Immutable な JSON 値を素の値へ戻す。"""
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def invoke_undo_artifact(
    current: Mapping[str, object], entries: list[object]
) -> dict[str, object] | None:
    """正式 artifact の取消計算を 1 回だけ呼ぶ。"""
    current_request: dict[str, object] = {
        "stateFields": current.get("stateFields"),
        "scoreboard": current.get("scoreboard"),
    }
    cursors = current.get("battingOrderBySide")
    if cursors is not None:
        current_request["battingOrderBySide"] = cursors
    request = {
        "current": current_request,
        "history": {"stack": entries},
    }
    with open_domain_host() as host:
        raw = host.call(
            "applyUndo",
            json.dumps(_plain(request), ensure_ascii=False, sort_keys=True),
        )
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(parsed, Mapping) or parsed.get("ok") is not True:
        return None
    value = parsed.get("value")
    if not isinstance(value, Mapping):
        return None
    return dict(value)


__all__ = ("invoke_undo_artifact",)
