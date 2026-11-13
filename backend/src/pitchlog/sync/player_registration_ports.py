"""その場登録の内容確認と保存投影を、適用核の閉じた Port へ接続する。

選手行と一時 ID 写像の作成は適用核の T2・T6 が所有する。ここでは登録イベントの
V7 が一時 ID だけを持つことと、投影後が正式 ID だけを持つことを確認し、意味の
再計算や別の作成経路を持たない。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import final
from uuid import UUID

from pitchlog.sync.model import ABSENT, SyncEvent, _canonical_uuid
from pitchlog.sync.ports import PortWriter

_EVENT_KIND = "player_registration"
_PAYLOAD_KEYS = frozenset({"player_id"})


def _player_id(event: SyncEvent) -> str | None:
    """V7 の選手参照が閉じた 1 キーなら返す。"""
    payload = event.v7
    if not isinstance(payload, Mapping) or frozenset(payload) != _PAYLOAD_KEYS:
        return None
    value = payload["player_id"]
    return value if _canonical_uuid(value) else None


@final
class PlayerRegistrationContentValidationPort:
    """その場登録の V5・V7・一時 ID の外形だけを確認する。"""

    def validate(self, event: SyncEvent, writer: PortWriter) -> tuple[bool, str | None]:
        """作成値の意味は検査せず、核が要求する閉じた参照だけを確かめる。"""
        if event.v5 != _EVENT_KIND:
            return False, "その場登録のイベント種別が不一致"
        if type(event.d1) is not int or event.d1 < 1:
            return False, "その場登録の D1 が不正"
        if type(event.d4) is not str or not event.d4:
            return False, "その場登録の D4 が不正"
        if (
            event.v6 is not ABSENT
            or event.v8 is not ABSENT
            or event.v9 is not ABSENT
            or event.v10 is not ABSENT
        ):
            return False, "その場登録に論理位置・状態差分・置換・対象参照を持てない"
        if _player_id(event) is None:
            return False, "その場登録の V7 が一時選手 ID だけを持たない"
        if writer is None:
            return False, "その場登録の書き手がない"
        return True, None


@final
class PlayerRegistrationProjectionPort:
    """投影後の V7 が正式選手 ID 1 件へ解決済みであることだけを確認する。"""

    def apply(self, event: SyncEvent, writer: PortWriter) -> None:
        """写像の解決結果を保存前に確認し、追加の行を作らない。"""
        if event.v5 != _EVENT_KIND or _player_id(event) is None:
            raise RuntimeError("その場登録の投影結果が不一致です")
        if type(event.d1) is not int or event.d1 < 1:
            raise RuntimeError("その場登録の投影 D1 が不一致です")
        if writer is None:
            raise RuntimeError("その場登録の書き手がありません")
        UUID(event.d5)
