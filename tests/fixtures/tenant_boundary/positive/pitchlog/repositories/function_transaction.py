"""固定関数ハンドルだけのSession.execute許可を表す正例。"""

from pitchlog.repositories.function_operations import (
    decode_function_result,
    prepare_function_operation,
)
from pitchlog.repositories.tokens import (  # ty: ignore[unresolved-import]
    TenantOperationResult,
    TenantOperationToken,
)
from sqlalchemy.orm import Session  # ty: ignore[unresolved-import]


class _TenantTransaction:
    """固定関数実行の正例。"""

    def __init__(self, session: Session, tenant_id: object, registry: object) -> None:
        """検査に必要な閉じた状態だけを保持する。"""
        self._session = session
        self._tenant_id = tenant_id
        self._registry = registry

    def run_function(self, operation: TenantOperationToken) -> TenantOperationResult:
        """登録済み関数文だけを実行する。"""
        spec, parameters = prepare_function_operation(
            operation, self._tenant_id, self._registry
        )
        result = self._session.execute(spec.statement, parameters)
        rows = TenantOperationResult(rows=tuple(tuple(row) for row in result))
        return decode_function_result(spec, rows)
