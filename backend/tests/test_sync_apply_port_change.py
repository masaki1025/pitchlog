"""P3 と意図配信の試験でだけ登録する合成ポート。"""

from pitchlog.sync.model import SyncEvent
from pitchlog.sync.ports import PortWriter


class ChangeRights:
    """復元状態・復旧世代・記録権の呼び出しを記録する。"""

    def __init__(
        self,
        *,
        restoration: bool = False,
        restoration_after_first: bool = False,
        current: bool = True,
        holds: bool = True,
    ) -> None:
        """試験の判定値を固定する。"""
        self.restoration = restoration
        self.restoration_after_first = restoration_after_first
        self.current = current
        self.holds = holds
        self.calls: list[str] = []

    def is_restoration_active(self, game_id: str, writer: PortWriter) -> bool:
        """復元調整状態を返す。"""
        self.calls.append("restoration")
        return self.restoration or (
            self.restoration_after_first and self.calls.count("restoration") > 1
        )

    def is_recovery_generation_current(
        self, game_id: str, supplied: str, writer: PortWriter
    ) -> bool:
        """復旧世代の比較を返す。"""
        self.calls.append("recovery")
        return self.current

    def holds_recording_right(
        self, game_id: str, d4: object, v12: object, writer: PortWriter
    ) -> bool:
        """進行中の記録権証明を返す。"""
        self.calls.append("holds")
        return self.holds


class ChangeValidator:
    """内容検査の結果を試験から制御する。"""

    def __init__(self, *, valid: bool = True) -> None:
        """内容判定を固定する。"""
        self.valid = valid
        self.calls = 0

    def validate(self, event: SyncEvent, writer: PortWriter) -> tuple[bool, str | None]:
        """拒否理由も固定して返す。"""
        self.calls += 1
        return self.valid, None if self.valid else "変更内容を拒否"


class ChangeProjection:
    """投影された変更イベントを記録する。"""

    def __init__(self) -> None:
        """空の観測列を持つ。"""
        self.events: list[SyncEvent] = []

    def apply(self, event: SyncEvent, writer: PortWriter) -> None:
        """T4 の呼び出しを観測する。"""
        self.events.append(event)


class ChangeSink:
    """意図 ID による論理効果の冪等化を試験する。"""

    def __init__(self, *, complete: bool = True) -> None:
        """配信状態を初期化する。"""
        self.complete = complete
        self.calls: list[str] = []
        self.effects: set[str] = set()

    def deliver(self, intent_id: str, scope_kind: str) -> bool:
        """同じ ID の再配送でも論理効果は一件に保つ。"""
        self.calls.append(intent_id)
        if self.complete:
            self.effects.add(intent_id)
        return self.complete
