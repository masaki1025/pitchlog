"""条件 5 で基底自身も除外されないことを表す負例。"""

from pitchlog.repositories.tokens import (  # ty: ignore
    TenantOperationResult,
    TenantOperationToken,
)
from sqlalchemy import text  # ty: ignore
from sqlalchemy.orm import Session  # ty: ignore


class TenantRepositoryBase:
    """許可関数内の禁止束縛と追加関数の直 SQL を持つ変異。"""

    def __init__(self, session: Session) -> None:
        """検査用のセッションを保持する。"""
        self._session = session

    def _execute_operation(
        self, operation: TenantOperationToken
    ) -> TenantOperationResult:
        """非局所の GUC 設定を混入する。"""
        self._session.execute(
            text("SELECT set_config('app.tenant_id', :tenant_id, false)"),
            {"tenant_id": operation.tenant_id},
        )
        return TenantOperationResult(rows=())

    def _unlisted_query(self) -> tuple[object, ...]:
        """同じ基底ファイルの未許可関数から DB を呼ぶ。"""
        return tuple(self._session.execute(text("SELECT 1")))
