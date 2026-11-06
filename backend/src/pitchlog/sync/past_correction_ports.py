"""P3内容Portは同一取引の真正再評価frameだけを読む。"""

from dataclasses import dataclass
from typing import final
from uuid import UUID

from pitchlog.repositories.tokens import TenantOperationResult, TenantOperationToken
from pitchlog.sync.model import SyncEvent
from pitchlog.sync.ports import PortWriter

_CONTENT_REJECTION_REASON = "P3変更内容が確定原本または有限対応範囲と不一致"


@dataclass(frozen=True, slots=True)
class ValidateP3CorrectionToken(TenantOperationToken):
    """実content phaseの元eventと同writerだけを指す。"""

    game_id: UUID
    d5: UUID
    event: SyncEvent
    writer: PortWriter

    @property
    def capability_id(self) -> str:
        """DB能力ではなく私有Port命令としてだけ受ける。"""
        return "CAP:sync_past_correction:validate_p3"


@dataclass(frozen=True, slots=True)
class ProjectP3CorrectionToken(TenantOperationToken):
    """T2済み実frameだけを同writerのT4へ渡す。"""

    game_id: UUID
    d5: UUID
    event: SyncEvent
    writer: PortWriter

    @property
    def capability_id(self) -> str:
        """未登録の自由SQLではなくP3私有Port命令。"""
        return "CAP:sync_past_correction:project_p3"


@final
class PastCorrectionContentValidationPort:
    """自由な正解値やframeを外から供給しないP3内容Port。"""

    def validate(self, event: SyncEvent, writer: PortWriter) -> tuple[bool, str | None]:
        """実content phaseの確定値だけを閉tupleとして返す。"""
        result = writer.run(
            ValidateP3CorrectionToken(
                UUID(event.game_id), UUID(event.d5), event, writer
            )
        )
        if (
            type(result) is not TenantOperationResult
            or type(result.rows) is not tuple
            or len(result.rows) != 1
            or type(result.rows[0]) is not tuple
            or len(result.rows[0]) != 2
        ):
            raise RuntimeError("P3内容Portの応答形が不一致")
        accepted, reason = result.rows[0]
        if (
            type(accepted) is not bool
            or (accepted and reason is not None)
            or (
                not accepted
                and (type(reason) is not str or reason != _CONTENT_REJECTION_REASON)
            )
        ):
            raise RuntimeError("P3内容Portの応答値が不一致")
        return accepted, reason if isinstance(reason, str) else None


@final
class PastCorrectionProjectionPort:
    """真正capsule/T5全値の一括保存だけを要求する。"""

    def apply(self, event: SyncEvent, writer: PortWriter) -> None:
        """返却された実保存receiptの閉形を確認する。"""
        result = writer.run(
            ProjectP3CorrectionToken(
                UUID(event.game_id), UUID(event.d5), event, writer
            )
        )
        if type(result) is not TenantOperationResult or result.rows != ((True,),):
            raise RuntimeError("P3 projection保存結果が不一致")
