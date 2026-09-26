"""テナントトランザクション操作ハンドルの許可契約を表す正例。"""

from typing import final

from pitchlog.repositories.base import (
    _materialize_rows,  # ty: ignore[unresolved-import]
    _operation_spec,  # ty: ignore[unresolved-import]
    _TenantOperationError,  # ty: ignore[unresolved-import]
)
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.tokens import (  # ty: ignore
    TenantOperationResult,
    TenantOperationToken,
)
from sqlalchemy.orm import Session  # ty: ignore
from sqlalchemy.sql import Select  # ty: ignore


@final
class _TenantTransaction:
    """束縛済み Session 上で閉じた operation token だけを実行する。"""

    __slots__ = ("_session", "_context")

    def __init__(self, session: Session, context: TenantContext) -> None:
        """検査用の Session とテナント文脈を保持する。"""
        self._session = session
        self._context = context

    def run(self, operation: TenantOperationToken) -> TenantOperationResult:
        """登録済み operation を実行して不変な行集合を返す。"""
        spec = _operation_spec(operation)
        if not isinstance(spec.statement, Select):
            raise _TenantOperationError(
                "トランザクション operation は Select だけを実行できる"
            )
        result = self._session.execute(
            spec.statement,
            {"tenant_id": self._context.tenant_id},
        )
        rows = tuple(tuple(row) for row in result)
        return _materialize_rows(rows)
