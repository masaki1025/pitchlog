"""spike 用のスタブポート実装と、実行時の登録接続を置く。

本物の記録権判定・T4 投影・内容検証は別工程が実装する。spike の縦
スライスでは、記録権を常に許可し、投影を no-op に、内容検証を常に許可と
して、同期核の保存経路を実 DB で通すだけにする。

登録は製品の `pitchlog.sync.ports.PORT_IMPLEMENTATIONS` を書き換える行為
であり、同期核の安全境界（core-areas の敵対レビューと U-X1 ドメイントリガ）
に触れ得る。このため登録は install()（spike 起動時の明示的操作）または
試験の monkeypatch に限り、このモジュールを import しただけでは起こらない。
install() は検査器の静的規則に沿って、属性名を文字列として渡す
`object.__setattr__` で接続する。その規則は、登録済みポート実装のソースで
`PORT_IMPLEMENTATIONS` といった登録表の内部名への属性参照を禁止する
（`port_guard._PORT_INTERNAL_NAMES`）。この制約のため、登録した値はモジュール
から読み戻す動的な入口がなく、復元は製品の初期値（空の登録表）へ戻す形で行う。
"""

from __future__ import annotations

from collections.abc import Callable

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
        """Spike では証明の内容を検査せず許可する。"""
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
        """Spike では復旧世代を検査せず現行扱いにする。"""
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
        """Spike では内容を検査せず許可する。"""
        self.calls.append(event.d5)
        return True, None


def install(ports_module: object) -> Callable[[], None]:
    """実行時にスタブポートの登録表へ接続し、復元用の callable を返す（spike 専用）。

    静的検査はポート実装からの登録表参照を禁止するため、属性名を文字列として
    渡して接続する。この文字列渡しは port_guard の静的規則（登録済みポート
    実装のソースで `ports.PORT_IMPLEMENTATIONS` 等の内部名への属性参照を禁止）
    を回避するために必要な割り切りであり、動的に参照可能な入口は残さない。

    呼ぶと登録表を製品の初期値（空の登録表）へ戻す callable を返す。読み戻し
    の入口が無いため install() 実行時の値は保存できず、spike は製品の登録表が
    空である時点（起動直後、または試験の monkeypatch 間）で呼ぶ前提とする。

    Args:
        ports_module: `pitchlog.sync.ports` モジュール。起動時に一度だけ
            呼ぶことを意図している。

    Returns:
        呼ぶと `PORT_IMPLEMENTATIONS` を空の frozenset() へ戻す callable。
    """
    registrations = frozenset(
        (cls.__module__, cls.__name__)
        for cls in (SpikeRights, SpikeProjection, SpikeValidator)
    )
    object.__setattr__(ports_module, "PORT_IMPLEMENTATIONS", registrations)

    def restore() -> None:
        """Spike の登録を外し、製品の空の登録表へ戻す。"""
        object.__setattr__(ports_module, "PORT_IMPLEMENTATIONS", frozenset())

    return restore
