"""取消Portは元参照命令だけを既writerへ渡し、資格を作らない。"""

from dataclasses import dataclass
from typing import final
from uuid import UUID

from pitchlog.repositories.tokens import TenantOperationResult, TenantOperationToken
from pitchlog.sync.model import SyncEvent
from pitchlog.sync.ports import PortWriter

# 内容不一致だけの有限理由。資格/host/DB不可用をこの値へ変換しない。
_UNDO_CONTENT_REJECTION_REASON = "取消内容が確定原本または実評価値と不一致"


@dataclass(frozen=True, slots=True)
class ValidateUndoToken(TenantOperationToken):
    """実content phaseの同event/同writerだけを指す。"""

    game_id: UUID
    d5: UUID
    event: SyncEvent
    writer: PortWriter

    @property
    def capability_id(self):
        """未登録能力を勝手に登録しない。"""
        return "CAP:sync_nonplay:validate_undo"


@dataclass(frozen=True, slots=True)
class ProjectUndoToken(TenantOperationToken):
    """実核projection区間の元参照だけを渡す。"""

    game_id: UUID
    d5: UUID
    event: SyncEvent
    writer: PortWriter

    @property
    def capability_id(self):
        """未登録能力を勝手に登録しない。"""
        return "CAP:sync_nonplay:project_undo"


@final
class UndoContentValidationPort:
    """実評価済み状態だけを核へ要求する。"""

    def validate(self, event: SyncEvent, writer: PortWriter) -> tuple[bool, str | None]:
        """未知命令/破損結果を成功や内容拒否へ補完しない。"""
        result = writer.run(
            ValidateUndoToken(UUID(event.game_id), UUID(event.d5), event, writer)
        )
        if (
            type(result) is not TenantOperationResult
            or type(result.rows) is not tuple
            or len(result.rows) != 1
            or type(result.rows[0]) is not tuple
            or len(result.rows[0]) != 2
        ):
            raise RuntimeError("取消content応答形が不一致です")
        accepted, reason = result.rows[0]
        if (
            type(accepted) is not bool
            or (accepted and reason is not None)
            or (
                not accepted
                and (
                    type(reason) is not str or reason != _UNDO_CONTENT_REJECTION_REASON
                )
            )
        ):
            raise RuntimeError("取消content応答値が不一致です")
        if accepted:
            return True, None
        if type(reason) is not str:
            raise RuntimeError("取消拒否理由の型が不一致です")
        return False, reason


@final
class UndoProjectionPort:
    """opaque資格と実SQL成功を核で消費する。"""

    def apply(self, event: SyncEvent, writer: PortWriter) -> None:
        """自由boolを受けず、実consumeの閉応答だけを確認する。"""
        result = writer.run(
            ProjectUndoToken(UUID(event.game_id), UUID(event.d5), event, writer)
        )
        if (
            type(result) is not TenantOperationResult
            or type(result.rows) is not tuple
            or len(result.rows) != 1
            or type(result.rows[0]) is not tuple
            or len(result.rows[0]) != 1
            or type(result.rows[0][0]) is not bool
            or result.rows[0][0] is not True
        ):
            raise RuntimeError("取消projection応答が不一致です")
