"""通常投球の元参照命令だけを同writerへ渡す実Port。"""

from typing import final
from uuid import UUID

from pitchlog.repositories.tokens import TenantOperationResult
from pitchlog.sync.model import SyncEvent
from pitchlog.sync.ordinary_pitch_tokens import (
    ProjectOrdinaryPitchToken,
    ValidateOrdinaryPitchToken,
)
from pitchlog.sync.ports import PortWriter


@final
class OrdinaryPitchContentValidationPort:
    """計算/SQL/frameを持たず、実核の内容評価結果だけを読む。"""

    def validate(self, event: SyncEvent, writer: PortWriter) -> tuple[bool, str | None]:
        """自由な成功boolを受け取らず元event参照を渡す。"""
        result = writer.run(
            ValidateOrdinaryPitchToken(
                UUID(event.game_id), UUID(event.d5), event, writer
            )
        )
        if (
            type(result) is not TenantOperationResult
            or type(result.rows) is not tuple
            or len(result.rows) != 1
            or len(result.rows[0]) != 2
        ):
            raise RuntimeError("通常内容命令の応答形が不一致")
        accepted, reason = result.rows[0]
        if (
            type(accepted) is not bool
            or (accepted and reason is not None)
            or (not accepted and (type(reason) is not str or not reason))
        ):
            raise RuntimeError("通常内容命令の応答値が不一致")
        if accepted:
            return True, None
        if type(reason) is not str:
            raise RuntimeError("通常内容拒否理由の型が不一致")
        return False, reason


@final
class OrdinaryPitchProjectionPort:
    """採番済みeventの真正frameと独立DB資格を核で一回だけ消費する。"""

    def apply(self, event: SyncEvent, writer: PortWriter) -> None:
        """保存値や成功boolを外から渡さず、実結果だけを確認する。"""
        result = writer.run(
            ProjectOrdinaryPitchToken(
                UUID(event.game_id), UUID(event.d5), event, writer
            )
        )
        if type(result) is not TenantOperationResult or result.rows != ((True,),):
            raise RuntimeError("通常投影命令の応答形が不一致")
