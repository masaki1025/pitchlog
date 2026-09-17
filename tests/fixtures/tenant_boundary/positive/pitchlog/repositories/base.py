"""将来のリポジトリ基底シンボル契約を表す正例。"""

from pitchlog.repositories.tokens import (  # ty: ignore
    TenantOperationResult,
    TenantOperationToken,
)
from sqlalchemy import text  # ty: ignore
from sqlalchemy.orm import Session  # ty: ignore


class TenantRepositoryBase:
    """閉じた operation token だけを実行する将来の基底。"""

    def __init__(self, session: Session) -> None:
        """検査用のセッションを保持する。"""
        self._session = session

    def _execute_operation(
        self, operation: TenantOperationToken
    ) -> TenantOperationResult:
        """契約済み token をテナント文脈内で実行する。"""
        self._session.execute(
            text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
            {"tenant_id": operation.tenant_id},
        )
        result = self._session.execute(operation.statement, operation.parameters)
        return TenantOperationResult(rows=tuple(tuple(row) for row in result))
