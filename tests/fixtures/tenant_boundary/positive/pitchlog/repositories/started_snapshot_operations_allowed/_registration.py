"""開始直後read登録の固定SELECT構築だけの正例。"""

from __future__ import annotations

from typing import Any

from pitchlog.repositories.operation_registration import (  # ty: ignore[unresolved-import]
    OperationRegistration,
)
from pitchlog.repositories.started_snapshot_operations import (  # ty: ignore[unresolved-import]
    _StartedReadToken,
)
from sqlalchemy import select


class started_snapshot_operations:
    """製品モジュールの登録symbolを表す。"""

    @staticmethod
    def _registration(
        token_type: type[_StartedReadToken],
        model: Any,
        *,
        lineups: bool = False,
    ) -> OperationRegistration:
        """固定表のSELECT構築だけを表す。"""
        del token_type, model, lineups
        return select(1)
