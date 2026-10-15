"""登録表の正例に使う合成投影ポート。"""

from pitchlog.sync.model import SyncEvent
from pitchlog.sync.ports import PortWriter


class SafeProjection:
    """ポート呼び出しの有無を記録する。"""

    def __init__(self) -> None:
        """呼び出し回数を初期化する。"""
        self.calls = 0

    def apply(self, event: SyncEvent, writer: PortWriter) -> None:
        """合成投影を呼び出したことだけを記録する。"""
        self.calls += 1
