"""同期経路の無効化意図 ID を導出し、配信対象を判定する。"""

from __future__ import annotations

SYNC_INTENT_PREFIX = "sync:"
_SYNC_SCOPE_KINDS = frozenset(
    {"game", "player_total", "team_total", "shared_total", "chart"}
)


def derive_sync_intent_id(event_identity: str, scope_kind: str) -> str:
    """B03 のイベント識別と範囲から安定した意図 ID を作る。"""
    if (
        type(event_identity) is not str
        or not event_identity
        or any(not part for part in event_identity.split(":"))
        or type(scope_kind) is not str
        or scope_kind not in _SYNC_SCOPE_KINDS
    ):
        raise ValueError("同期意図にはイベント識別と既知の範囲が必要")
    return f"{SYNC_INTENT_PREFIX}{event_identity}:{scope_kind}"


def is_sync_intent_id(intent_id: object) -> bool:
    """混在する未配信行から同期経路の意図だけを識別する。"""
    if type(intent_id) is not str:
        return False
    parts = intent_id.split(":")
    return (
        len(parts) >= 3
        and parts[0] == "sync"
        and all(parts[1:-1])
        and parts[-1] in _SYNC_SCOPE_KINDS
    )
