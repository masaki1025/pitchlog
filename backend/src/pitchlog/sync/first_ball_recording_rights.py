"""初球P2の記録権命令を同writerへ渡す。資格/epoch/SQLを生成しない。"""

from typing import final
from uuid import UUID

from pitchlog.repositories.tokens import TenantOperationResult
from pitchlog.sync.model import StageValue
from pitchlog.sync.ports import PortWriter
from pitchlog.sync.tokens import (
    PortCheckPresentedRightToken,
    PortRG1CommitCheckToken,
    PortRG1PrecheckToken,
)


class FirstBallRecordingRightsError(RuntimeError):
    """入力を含めない記録権Portの固定失敗。"""


def _one_bool(result: TenantOperationResult) -> bool:
    """核が閉じたexact1bool以外を成功やfalseへ補完しない。"""
    if type(result) is not TenantOperationResult or (
        type(result.rows) is not tuple
        or len(result.rows) != 1
        or type(result.rows[0]) is not tuple
        or len(result.rows[0]) != 1
        or type(result.rows[0][0]) is not bool
    ):
        raise FirstBallRecordingRightsError("記録権命令の結果が不正")
    return result.rows[0][0]


@final
class FirstBallRecordingRightsPort:
    """既Port4ABIを保つP2専用のstateless実装。"""

    def read_rg1_before_d5(self, writer: PortWriter) -> bool:
        """その場の事前RG1命令からだけ結果を返す。"""
        return _one_bool(writer.run(PortRG1PrecheckToken()))

    def check_rg1_before_commit(self, writer: PortWriter) -> bool:
        """その場の最終RG1命令からだけ結果を返す。"""
        return _one_bool(writer.run(PortRG1CommitCheckToken()))

    def is_recovery_generation_current(
        self, game_id: str, supplied: str, writer: PortWriter
    ) -> bool:
        """P3の未供給を成功やfalseへ置き換えない。"""
        raise FirstBallRecordingRightsError("初球P2以外の復旧照合は未提供")

    def holds_recording_right(
        self, game_id: str, d4: StageValue, v12: StageValue, writer: PortWriter
    ) -> bool:
        """元提示V12を核へ送り、核の実検証結果だけを返す。"""
        try:
            parsed = UUID(game_id) if type(game_id) is str else None
            if (
                parsed is None
                or str(parsed) != game_id
                or type(d4) is not str
                or not d4
            ):
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            raise FirstBallRecordingRightsError("記録権命令の入力が不正") from None
        return _one_bool(writer.run(PortCheckPresentedRightToken(parsed, d4, v12)))
