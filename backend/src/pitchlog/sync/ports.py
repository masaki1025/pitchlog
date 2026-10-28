"""同期核のポートと登録表を定義する。

ポートが使う operation token 型は SQL と登録処理を import しないモジュールに置く。
文と準備関数は repositories 側で token 型を import して結び付ける。
静的検査は補助であり、安全の境界ではない。境界は sync-protocol の core-areas に
登録された本ファイルの PORT_IMPLEMENTATIONS の変更に対する敵対レビューと
人間の逐行確認、および U-X1 が本物の投影ポートで設ける適用核の印を要求する DB トリガ。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, final
from uuid import UUID

from pitchlog.repositories.tokens import TenantOperationResult, TenantOperationToken
from pitchlog.sync.model import StageValue, SyncEvent


class PortRegistrationError(RuntimeError):
    """未登録または禁止 import を持つポート実装を表す。"""


_WRITER_CREATION_TOKEN = object()


@final
class PortWriter:
    """適用核の既存トランザクションで operation token だけを実行する。"""

    __slots__ = ("_execute", "_active")

    def __init__(
        self,
        execute: Callable[[TenantOperationToken], TenantOperationResult],
        creation_token: object,
    ) -> None:
        """適用核だけが渡せる印を確認して発行する。"""
        if creation_token is not _WRITER_CREATION_TOKEN:
            raise PermissionError("PortWriter は適用核だけが発行できる")
        self._execute = execute
        self._active = True

    def run(self, operation: TenantOperationToken) -> TenantOperationResult:
        """閉鎖後と SQL 文を拒否し、operation token だけを実行する。"""
        if not self._active:
            raise RuntimeError("PortWriter のトランザクションは閉じている")
        if not isinstance(operation, TenantOperationToken):
            raise TypeError("PortWriter は operation token だけを受け付ける")
        return self._execute(operation)

    def _close(self) -> None:
        """発行元のトランザクション終了時に書き手を失効させる。"""
        self._active = False


def _issue_port_writer(
    execute: Callable[[TenantOperationToken], TenantOperationResult],
) -> PortWriter:
    """適用核の同一トランザクション用の書き手を発行する。"""
    return PortWriter(execute, _WRITER_CREATION_TOKEN)


class RecordingRightsPort(Protocol):
    """記録権証明・復旧世代・復元調整ゲートの所有者。"""

    def read_rg1_before_d5(self, writer: PortWriter) -> bool:
        """③-a の非ロック読取で、書き込み可能なら True を返す。"""
        ...

    def check_rg1_before_commit(self, writer: PortWriter) -> bool:
        """⑧ の FOR SHARE を取引終了まで保持し、開いていれば True を返す。"""
        ...

    def is_recovery_generation_current(
        self, game_id: str, supplied: str, writer: PortWriter
    ) -> bool:
        """要求作成時の復旧世代が現世代かを返す。"""
        ...

    def holds_recording_right(
        self, game_id: str, d4: StageValue, v12: StageValue, writer: PortWriter
    ) -> bool:
        """現 D4・現復旧世代・保持端末への結合を照合する。"""
        ...


class ProjectionPort(Protocol):
    """T4 の投影更新を所有する。"""

    def apply(self, event: SyncEvent, writer: PortWriter) -> None:
        """同じトランザクション内で投影を更新する。"""
        ...


class ContentValidationPort(Protocol):
    """D1 付き経路の⑦と P3 の⑥の内容判定を所有する。"""

    def validate(self, event: SyncEvent, writer: PortWriter) -> tuple[bool, str | None]:
        """受理可否と拒否理由を返す。"""
        ...


@dataclass(frozen=True, slots=True)
class DeliveryIntent:
    """配信先へ渡す同期意図の 1 行(テナントと範囲ごとの選択子)。

    意図 ID はテナント内でしか一意でないので、配信先の冪等キーは
    `(tenant_id, intent_id)` とする。選択子は data-model `B03` の「各行が選ぶ
    無効化先」に従い、範囲に関係しない成分は None。
    """

    tenant_id: UUID
    intent_id: str
    scope_kind: str
    game_id: UUID | None
    player_id: UUID | None
    group_id: UUID | None
    target_tenant_id: UUID | None
    period: object
    chart_kind: str | None


class InvalidationSinkPort(Protocol):
    """I5 で永続化された意図の配信先。"""

    def deliver(self, intent: DeliveryIntent) -> bool:
        """配信完了を返し、未完了なら再試行を許す。"""
        ...


# 実装を接続するまで空。クラスを module の属性から取得して同一性で照合する。
PORT_IMPLEMENTATIONS: frozenset[tuple[str, str]] = frozenset(
    {
        ("pitchlog.sync.first_ball_ports", "FirstBallContentValidationPort"),
    }
)
_PORT_VERIFIER: Callable[[object], None] | None = None


def require_registered_port(port: object) -> None:
    """検査器を通して、ポートを呼ぶ前に登録済みクラスを確認する。"""
    verifier = _PORT_VERIFIER
    if verifier is None:
        raise PortRegistrationError("ポート登録検査器が未接続")
    verifier(port)
