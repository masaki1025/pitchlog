"""SQL を import しない token と合成ポートを定義する。"""

from pitchlog.repositories.tokens import TenantOperationToken
from pitchlog.sync.model import SyncEvent
from pitchlog.sync.ports import PortWriter


class TokenOnlyOperation(TenantOperationToken):
    """テスト用の閉じた operation token。"""

    @property
    def capability_id(self) -> str:
        """合成 capability を返す。"""
        return "test-token-only"


class TokenOnlyProjection:
    """SQL 定義を import せず token だけを使用する合成ポート。"""

    def apply(self, event: SyncEvent, writer: PortWriter) -> None:
        """適用核から渡された書き手で token を実行する。"""
        writer.run(TokenOnlyOperation())
