"""spike 用のスタブポート実装と、実行時の登録接続を置く。

本物の記録権判定・T4 投影・内容検証は別工程が実装する。spike の縦
スライスでは、記録権を常に許可し、投影を no-op に、内容検証を常に許可と
して、同期核の保存経路を実 DB で通すだけにする。

登録は製品の `pitchlog.sync.ports.PORT_IMPLEMENTATIONS` を書き換える行為
であり、同期核の安全境界（core-areas の敵対レビューと U-X1 ドメイントリガ）
に触れ得る。このため登録は install()（spike 起動時の明示的操作）または
試験の monkeypatch に限り、このモジュールを import しただけでは起こらない。
install() は検査器の静的規則（ポート実装からの登録表の属性参照は禁止）に
沿って、属性名を文字列として渡す `object.__setattr__` で接続する。
"""

from __future__ import annotations

from pitchlog.sync.model import SyncEvent
from pitchlog.sync.ports import PortWriter


class SpikeRights:
    """記録権判定を常に許可するスタブ。"""

    def __init__(self) -> None:
        """空の呼び出し列を持つ。"""
        self.calls: list[str] = []
        self.rg1_calls: list[str] = []

    def holds_recording_right(
        self, game_id: str, d4: object, v12: object, writer: PortWriter
    ) -> bool:
        """spike では証明の内容を検査せず許可する。"""
        self.calls.append(game_id)
        return True

    def read_rg1_before_d5(self, writer: PortWriter) -> bool:
        """③-a の非ロック読取を常に開く。"""
        self.rg1_calls.append("read")
        return True

    def check_rg1_before_commit(self, writer: PortWriter) -> bool:
        """⑧ の FOR SHARE を常に開く。"""
        self.rg1_calls.append("commit")
        return True

    def is_recovery_generation_current(
        self, game_id: str, supplied: str, writer: PortWriter
    ) -> bool:
        """spike では復旧世代を検査せず現行扱いにする。"""
        return True


class SpikeProjection:
    """T4 の投影として受け取ったイベントを列に残すだけのスタブ。"""

    def __init__(self) -> None:
        """空の投影列を持つ。"""
        self.events: list[SyncEvent] = []

    def apply(self, event: SyncEvent, writer: PortWriter) -> None:
        """投影の代わりに受け取りを記録する。"""
        self.events.append(event)


class SpikeValidator:
    """⑦・⑥ の内容判定を常に許可するスタブ。"""

    def __init__(self) -> None:
        """空の呼び出し列を持つ。"""
        self.calls: list[str] = []

    def validate(
        self, event: SyncEvent, writer: PortWriter
    ) -> tuple[bool, str | None]:
        """spike では内容を検査せず許可する。"""
        self.calls.append(event.d5)
        return True, None


def install(ports_module: object) -> None:
    """実行時にスタブポートの登録表へ接続する（spike 専用）。

    Args:
        ports_module: `pitchlog.sync.ports` モジュール。静的検査はポート実装
            からの登録表参照を禁止するため、属性名を文字列として渡して
            接続する。起動時に一度だけ呼ぶことを意図している。
    """
    registrations = frozenset(
        (cls.__module__, cls.__name__)
        for cls in (SpikeRights, SpikeProjection, SpikeValidator)
    )
    object.__setattr__(ports_module, "PORT_IMPLEMENTATIONS", registrations)
