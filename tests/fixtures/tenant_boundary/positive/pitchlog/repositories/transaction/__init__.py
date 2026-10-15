"""テナント操作の SAVEPOINT を許す正例。"""

from pitchlog.repositories.tokens import TenantOperationResult, TenantOperationToken  # ty: ignore
from sqlalchemy.orm import Session  # ty: ignore


class _TenantTransaction:
    """既存ハンドルが持つ Session を使う。"""

    _session: Session

    def run(self, operation: TenantOperationToken) -> TenantOperationResult:
        """同じハンドル上の登録済み操作へ委譲する。"""
        raise NotImplementedError

    def run_in_savepoint(
        self, operation: TenantOperationToken
    ) -> TenantOperationResult:
        """失敗した単一 operation だけを戻す。"""
        with self._session.begin_nested():
            return self.run(operation)
