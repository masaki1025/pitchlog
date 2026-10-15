"""P1 の適用試験に限って接続する合成ポート。"""

from collections.abc import Callable

from pitchlog.sync.model import SyncEvent
from pitchlog.sync.ports import PortWriter


class PrefixRights:
    """記録権判定の呼び出しを記録する。"""

    def __init__(
        self,
        *,
        read_open: bool = True,
        commit_open: bool = True,
        fail_at: str | None = None,
    ) -> None:
        """ゲートの判定値と空の呼び出し列を持つ。"""
        self.calls: list[str] = []
        self.rg1_calls: list[str] = []
        self.read_open = read_open
        self.commit_open = commit_open
        self.fail_at = fail_at
        self.writer: PortWriter | None = None

    def holds_recording_right(
        self, game_id: str, d4: object, v12: object, writer: PortWriter
    ) -> bool:
        """合成試験では記録権を許す。"""
        self.calls.append(game_id)
        return True

    def read_rg1_before_d5(self, writer: PortWriter) -> bool:
        """合成試験では事前ゲートを通す。"""
        self.writer = writer
        self.rg1_calls.append("read")
        if self.fail_at == "read":
            raise RuntimeError("RG1 事前読取失敗")
        return self.read_open

    def check_rg1_before_commit(self, writer: PortWriter) -> bool:
        """合成試験ではコミット前ゲートを通す。"""
        assert writer is self.writer
        self.rg1_calls.append("commit")
        if self.fail_at == "commit":
            raise RuntimeError("RG1 コミット前読取失敗")
        return self.commit_open

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


class RejectPrefixValidator(PrefixValidator):
    """P5/T9 を実経路から起動する合成の内容拒否。"""

    def validate(self, event: SyncEvent, writer: PortWriter) -> tuple[bool, str | None]:
        """拒否原本に残す決定的な理由を返す。"""
        self.calls.append(event.d5)
        return False, "内容不正"


class PrefixProjection:
    """投影へ渡されたイベントを記録する。"""

    def __init__(self) -> None:
        """空の呼び出し列を持つ。"""
        self.events: list[SyncEvent] = []

    def apply(self, event: SyncEvent, writer: PortWriter) -> None:
        """渡されたイベントを保持する。"""
        self.events.append(event)


class FailingPrefixProjection(PrefixProjection):
    """再採番後の投影失敗でトランザクションを戻す合成ポート。"""

    def apply(self, event: SyncEvent, writer: PortWriter) -> None:
        """呼び出しを記録した後、確定を失敗させる。"""
        super().apply(event, writer)
        raise RuntimeError("合成投影失敗")


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


class GenerationRights(PrefixRights):
    """要求の D4 が DB の現世代と一致し、保持端末であるときだけ記録権を認める。

    故障系 runner が送信の直前に DB から読んだ現世代を受け取る。呼び出しの順を
    一つの列に残し、③-a・⑤・⑧ の順序を観測できるようにする。
    """

    def __init__(self, current_generation: int, *, holder: bool = True) -> None:
        """現世代と、送信端末が保持端末かを受け取る。"""
        super().__init__()
        self.current_generation = current_generation
        self.holder = holder
        self.sequence: list[str] = []
        self.verdict: bool | None = None

    def holds_recording_right(
        self, game_id: str, d4: object, v12: object, writer: PortWriter
    ) -> bool:
        """保持端末かつ現世代の D4 なら記録権ありとする。"""
        self.calls.append(game_id)
        self.sequence.append("holds")
        self.verdict = self.holder and str(d4) == str(self.current_generation)
        return self.verdict

    def read_rg1_before_d5(self, writer: PortWriter) -> bool:
        """③-a の読取を順序の列に残す。"""
        self.sequence.append("rg1_read")
        return super().read_rg1_before_d5(writer)

    def check_rg1_before_commit(self, writer: PortWriter) -> bool:
        """⑧ のコミット直前の再検証を順序の列に残す。"""
        self.sequence.append("rg1_commit")
        return super().check_rg1_before_commit(writer)
