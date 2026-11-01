"""記録後read登録の固定SELECT構築だけの正例。"""

from __future__ import annotations

from pitchlog.repositories.operation_registration import (  # ty: ignore[unresolved-import]
    OperationRegistration,
)
from pitchlog.repositories.recorded_snapshot_operations import (  # ty: ignore[unresolved-import]
    _RecordedReadToken,
)
from sqlalchemy import Table, select


class recorded_snapshot_operations:
    """製品モジュールの登録symbolを表す。"""

    @staticmethod
    def _registration(
        token_type: type[_RecordedReadToken],
        table: Table,
        order: tuple[str, ...],
    ) -> OperationRegistration:
        """固定表のSELECT構築だけを表す。"""
        del token_type, table, order
        return select(1)
