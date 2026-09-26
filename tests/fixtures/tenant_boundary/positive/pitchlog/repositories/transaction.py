"""テナントトランザクション操作ハンドルの許可契約を表す正例。"""

from typing import final

from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.tokens import (  # ty: ignore
    TenantOperationResult,
    TenantOperationToken,
)
from sqlalchemy.orm import Session  # ty: ignore


@final
class TenantTransaction:
    """束縛済み Session 上で閉じた operation token だけを実行する。"""

    __slots__ = ("_session", "_context")

    def __init__(self, session: Session, context: TenantContext) -> None:
        """検査用の Session とテナント文脈を保持する。"""
        self._session = session
        self._context = context

    def run(self, operation: TenantOperationToken) -> TenantOperationResult:
        """登録済み operation を実行して不変な行集合を返す。"""
        result = self._session.execute(
            operation._statement,
            {"tenant_id": self._context.tenant_id},
        )
        return TenantOperationResult(rows=tuple(tuple(row) for row in result))
