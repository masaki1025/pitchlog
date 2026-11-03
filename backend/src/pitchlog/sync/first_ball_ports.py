"""初球内容の有限値命令だけを同writerへ渡す。計算/SQL/権利判断はしない。"""

from __future__ import annotations

from typing import final
from uuid import UUID

from pitchlog.repositories.tokens import TenantOperationResult
from pitchlog.sync.model import SyncEvent
from pitchlog.sync.ports import PortWriter
from pitchlog.sync.tokens import PortValidateFirstBallToken


@final
class FirstBallContentValidationPort:
    """実scope側で準備した初球内容だけを確認する。projectionは単位Bで別提供。"""

    def validate(self, event: SyncEvent, writer: PortWriter) -> tuple[bool, str | None]:
        """context/frame/sourceを受け取らず、元event参照だけを有限命令へ渡す。"""
        result = writer.run(
            PortValidateFirstBallToken(
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
            raise RuntimeError("初球内容命令の応答形が不一致です")
        accepted, reason = result.rows[0]
        if type(accepted) is not bool:
            raise RuntimeError("初球内容命令の真偽型が不一致です")
        if accepted:
            if reason is not None:
                raise RuntimeError("初球内容命令の成功理由が不一致です")
            return True, None
        if type(reason) is not str or not reason:
            raise RuntimeError("初球内容命令の拒否理由が不一致です")
        return False, reason
