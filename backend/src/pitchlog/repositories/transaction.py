"""複数のテナント operation を束ねるトランザクション単位を提供する。"""

from __future__ import annotations

from contextlib import AbstractContextManager, ExitStack
from types import TracebackType
from typing import final

from sqlalchemy.orm import Session

from pitchlog.db.engine import create_database_engine
from pitchlog.repositories.base import _materialize_rows, _operation_spec
from pitchlog.repositories.binding import _tenant_transaction
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.tokens import (
    TenantOperationResult,
    TenantOperationToken,
)

__all__ = ("TenantTransaction", "tenant_transaction_scope")


@final
class TenantTransaction:
    """束縛済み Session 上で閉じた operation token だけを実行する。"""

    __slots__ = ("_session", "_context")

    def __init__(self, session: Session, context: TenantContext) -> None:
        """トランザクション内だけで使う Session と文脈を保持する。

        Args:
            session: テナント文脈を束縛済みの Session。
            context: スコープ生成時に受け取ったテナント文脈。
        """
        self._session = session
        self._context = context

    def run(self, operation: TenantOperationToken) -> TenantOperationResult:
        """登録済み operation を実行して不変な行集合を返す。

        Args:
            operation: 生成済み registry が認識する operation token。

        Returns:
            トランザクション内で完全実体化した immutable な結果。

        Raises:
            RuntimeError: token が registry に無いか結果契約に違反する場合。
        """
        spec = _operation_spec(operation)
        execution_result = self._session.execute(
            spec.statement,
            {"tenant_id": self._context.tenant_id},
        )
        rows = tuple(tuple(row) for row in execution_result)
        return _materialize_rows(rows)


class _TenantTransactionScope(AbstractContextManager[TenantTransaction]):
    """Session の生成から close までを所有する内部 context manager。"""

    __slots__ = ("_context", "_exit_stack", "_session")

    def __init__(self, context: TenantContext) -> None:
        """スコープへ一度だけ渡されたテナント文脈を保持する。

        Args:
            context: API 層から引き渡されたテナント文脈。
        """
        self._context = context
        self._exit_stack: ExitStack | None = None
        self._session: Session | None = None

    def __enter__(self) -> TenantTransaction:
        """Session を生成し、トランザクション先頭で文脈を束縛する。

        Returns:
            束縛済み Session だけを内部保持する操作ハンドル。
        """
        if self._session is not None or self._exit_stack is not None:
            raise RuntimeError("同じトランザクションスコープへ再入できない")

        session = Session(create_database_engine())
        exit_stack = ExitStack()
        handle = TenantTransaction(session, self._context)
        self._session = session
        self._exit_stack = exit_stack
        try:
            ExitStack.enter_context(
                exit_stack,
                _tenant_transaction(session, self._context),
            )
        except BaseException:
            try:
                session.close()
            finally:
                self._exit_stack = None
                self._session = None
            raise
        return handle

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        """終了理由を既存境界へ渡し、成否にかかわらず Session を閉じる。

        Args:
            exception_type: スコープ内で発生した例外の型。
            exception: スコープ内で発生した例外。
            traceback: スコープ内で発生した例外の traceback。

        Returns:
            既存トランザクション境界の例外伝播判定。
        """
        session = self._session
        exit_stack = self._exit_stack
        if session is None or exit_stack is None:
            raise RuntimeError("開始していないトランザクションスコープを終了できない")

        try:
            return ExitStack.__exit__(
                exit_stack,
                exception_type,
                exception,
                traceback,
            )
        finally:
            try:
                session.close()
            finally:
                self._exit_stack = None
                self._session = None


def tenant_transaction_scope(
    context: TenantContext,
) -> AbstractContextManager[TenantTransaction]:
    """テナント文脈を一度だけ受け取るトランザクション単位を返す。

    Args:
        context: API 層から引き渡されたテナント文脈。

    Returns:
        Session の生成・束縛・確定・取消・close を所有するスコープ。
    """
    return _TenantTransactionScope(context)
