"""P1 の適用試験に限って接続する合成ポート。"""

from collections.abc import Callable

from pitchlog.sync.model import SyncEvent
from pitchlog.sync.ports import PortWriter


class PrefixRights:
    """記録権判定の呼び出しを記録する。"""

    def __init__(self) -> None:
        """空の呼び出し列を持つ。"""
        self.calls: list[str] = []

    def holds_recording_right(
        self, game_id: str, d4: object, v12: object, writer: PortWriter
    ) -> bool:
        """合成試験では記録権を許す。"""
        self.calls.append(game_id)
        return True

    def is_restoration_active(self, game_id: str, writer: PortWriter) -> bool:
        """合成試験では復元調整中でない。"""
        return False

    def is_recovery_generation_current(
        self, game_id: str, supplied: str, writer: PortWriter
    ) -> bool:
        """合成試験では復旧世代が一致する。"""
        return True


class DenyPrefixRights(PrefixRights):
    """順序試験で B2 より先の記録権拒否を観測する。"""

    def holds_recording_right(
        self, game_id: str, d4: object, v12: object, writer: PortWriter
    ) -> bool:
        """呼び出しを記録し、記録権を拒否する。"""
        self.calls.append(game_id)
        return False


class PrefixValidator:
    """内容検証の呼び出しを記録する。"""

    def __init__(self) -> None:
        """空の呼び出し列を持つ。"""
        self.calls: list[str] = []

    def validate(self, event: SyncEvent, writer: PortWriter) -> tuple[bool, str | None]:
        """合成試験では内容を受け付ける。"""
        self.calls.append(event.d5)
        return True, None


class PrefixProjection:
    """投影へ渡されたイベントを記録する。"""

    def __init__(self) -> None:
        """空の呼び出し列を持つ。"""
        self.events: list[SyncEvent] = []

    def apply(self, event: SyncEvent, writer: PortWriter) -> None:
        """渡されたイベントを保持する。"""
        self.events.append(event)


class ScopeOpeningProjection:
    """テストから注入した別スコープ開始処理を投影中に呼ぶ。"""

    def __init__(self, open_scope: Callable[[], None]) -> None:
        """試験側だけが持つ処理を保存する。"""
        self.open_scope = open_scope
        self.calls = 0

    def apply(self, event: SyncEvent, writer: PortWriter) -> None:
        """投影呼び出し後にスコープ入口の拒否を観測する。"""
        self.calls += 1
        self.open_scope()
