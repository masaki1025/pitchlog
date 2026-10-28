"""初球PlayRowの投影Port。核が束縛したframeを同TXで一回だけ保存する。"""

from __future__ import annotations

from typing import final
from uuid import UUID

from pitchlog.repositories.tokens import TenantOperationResult
from pitchlog.sync.model import SyncEvent
from pitchlog.sync.ports import PortWriter
from pitchlog.sync.tokens import PortProjectFirstBallToken


@final
class FirstBallProjectionPort:
    """採番済みeventの同一性だけを有限命令へ渡し、保存は核に閉じる。"""

    def apply(self, event: SyncEvent, writer: PortWriter) -> None:
        """同writer投影区間のframe一回消費とU06 INSERTを核へ要求する。

        Args:
            event: 採番後のイベント(D2確定済み)。
            writer: 同TXのwriter。

        Raises:
            RuntimeError: 核の応答形が閉形式でない場合。
        """
        result = writer.run(
            PortProjectFirstBallToken(
                UUID(event.game_id), UUID(event.d5), event, writer
            )
        )
        if (
            type(result) is not TenantOperationResult
            or type(result.rows) is not tuple
            or result.rows != ((True,),)
        ):
            raise RuntimeError("初球投影命令の応答形が不一致です")
