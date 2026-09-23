"""将来のリポジトリ基底シンボル契約を表す正例。"""

from pitchlog.repositories.binding import _tenant_transaction
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.tokens import (  # ty: ignore
    TenantOperationResult,
    TenantOperationToken,
)
from sqlalchemy.orm import Session  # ty: ignore


class TenantRepositoryBase:
    """閉じた operation token だけを実行する将来の基底。"""

    def __init__(self, session: Session) -> None:
        """検査用のセッションを保持する。"""
        self._session = session

    def _execute_operation(
        self,
        context: TenantContext,
        operation: TenantOperationToken,
    ) -> TenantOperationResult:
        """契約済み token をテナント文脈内で実行する。"""
        with _tenant_transaction(self._session, context):
            result = self._session.execute(
                operation._statement,
                {"tenant_id": context.tenant_id},
            )
            return TenantOperationResult(rows=tuple(tuple(row) for row in result))
