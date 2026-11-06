"""P3権利Port。現epochとV12を同writerの閉命令だけで判定する。"""

from typing import final
from uuid import UUID

from pitchlog.sync.first_ball_recording_rights import _one_bool
from pitchlog.sync.model import StageValue
from pitchlog.sync.ports import PortWriter
from pitchlog.sync.tokens import (
    PortP3PresentedRightToken,
    PortP3RecoveryCurrentToken,
    PortRG1CommitCheckToken,
    PortRG1PrecheckToken,
)


@final
class PastCorrectionRecordingRightsPort:
    """初球stampを発行せずP3専用の実判定へ渡す。"""

    def read_rg1_before_d5(self, writer: PortWriter) -> bool:
        """現借用の事前RG1を照合する。"""
        return _one_bool(writer.run(PortRG1PrecheckToken()))

    def check_rg1_before_commit(self, writer: PortWriter) -> bool:
        """コミット直前RG1とロックを照合する。"""
        return _one_bool(writer.run(PortRG1CommitCheckToken()))

    def is_recovery_generation_current(
        self, game_id: str, supplied: str, writer: PortWriter
    ) -> bool:
        """現RG1借用epochへP3原要求を照合する。"""
        try:
            parsed = UUID(game_id)
        except (ValueError, TypeError, AttributeError):
            raise ValueError("P3復旧照合の試合識別が不正") from None
        if (
            type(game_id) is not str
            or str(parsed) != game_id
            or type(supplied) is not str
            or not supplied
        ):
            raise ValueError("P3復旧照合の入力が不正")
        return _one_bool(writer.run(PortP3RecoveryCurrentToken(parsed, supplied)))

    def holds_recording_right(
        self, game_id: str, d4: StageValue, v12: StageValue, writer: PortWriter
    ) -> bool:
        """進行中P3だけの現D4と提示V12を無印DB関数へ渡す。"""
        try:
            parsed = UUID(game_id)
        except (ValueError, TypeError, AttributeError):
            raise ValueError("P3権利照合の試合識別が不正") from None
        if (
            type(game_id) is not str
            or str(parsed) != game_id
            or type(d4) is not str
            or not d4.isdecimal()
            or d4 == "0"
            or str(int(d4)) != d4
        ):
            raise ValueError("P3権利照合の現世代が不正")
        return _one_bool(writer.run(PortP3PresentedRightToken(parsed, d4, v12)))
