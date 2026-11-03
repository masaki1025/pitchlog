"""HTTP層へ既存の記録識別値の復号だけを提供する。"""

from uuid import UUID

from pitchlog.recording_rights.initial_grant_broker import _broker_generation


def _decode_recording_key(value: str, tenant_id: UUID, game_id: UUID) -> int:
    """既存codecを一回呼び、値と失敗をそのまま返す。"""
    return _broker_generation(value, tenant_id, game_id)
