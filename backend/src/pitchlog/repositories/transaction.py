"""複数のテナント operation を束ねるトランザクション単位を提供する。"""

from __future__ import annotations

from contextlib import AbstractContextManager, ExitStack
from types import TracebackType
from typing import final
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from pitchlog.db.engine import create_database_engine
from pitchlog.repositories.base import (
    _materialize_rows,
    _operation_spec,
    _TenantOperationError,
)
from pitchlog.repositories.binding import TenantBindingError, _tenant_transaction
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.tokens import (
    TenantOperationResult,
    TenantOperationToken,
)

__all__ = ("tenant_transaction_scope",)

_HANDLE_CREATION_TOKEN = object()
_TransactionRuntime = tuple[Session, ExitStack]
_TRANSACTION_RUNTIMES: dict[object, _TransactionRuntime] = {}


@final
class _TenantTransaction:
    """束縛済み Session 上で閉じた operation token だけを実行する。"""

    __slots__ = (
        "_state_key",
        "_context",
        "_bound_tenant_id",
        "_bound_integrity_proof",
    )

    def __init__(
        self,
        context: TenantContext,
        state_key: object,
        bound_tenant_id: UUID,
        bound_integrity_proof: bytes,
        creation_token: object,
    ) -> None:
        """Scope が発行した実行状態への不透明キーと文脈を保持する。

        Args:
            context: スコープ生成時に受け取ったテナント文脈。
            state_key: モジュール私有レジストリ上の実行状態キー。
            bound_tenant_id: 束縛時点で固定したテナント ID。
            bound_integrity_proof: 束縛時点で固定した発行証跡。
            creation_token: Scope だけが渡すモジュール私有センチネル。

        Raises:
            RuntimeError: Scope 外からの生成、または未登録状態を検出した場合。
        """
        if creation_token is not _HANDLE_CREATION_TOKEN:
            raise RuntimeError("トランザクションハンドルは scope だけが生成できる")
        if state_key not in _TRANSACTION_RUNTIMES:
            raise RuntimeError("scope が登録していない実行状態から生成できない")
        self._state_key: object | None = state_key
        self._context = context
        self._bound_tenant_id = bound_tenant_id
        self._bound_integrity_proof = bound_integrity_proof

    def _expire(self) -> object | None:
        """実行状態との対応を破棄し、ハンドルを永久に失効させる。"""
        state_key = self._state_key
        self._state_key = None
        return state_key

    def run(self, operation: TenantOperationToken) -> TenantOperationResult:
        """登録済み operation を実行して不変な行集合を返す。

        Args:
            operation: 生成済み registry が認識する operation token。

        Returns:
            トランザクション内で完全実体化した immutable な結果。

        Raises:
            RuntimeError: ハンドルが失効済み、token が registry に無い、または
                結果契約に違反する場合。
        """
        state_key = self._state_key
        if state_key is None:
            raise RuntimeError("トランザクションハンドルは失効している")
        runtime = _TRANSACTION_RUNTIMES.get(state_key)
        if runtime is None:
            self._state_key = None
            raise RuntimeError("トランザクションハンドルは失効している")
        if (
            type(self._context) is not TenantContext
            or self._context.tenant_id != self._bound_tenant_id
            or self._context._integrity_proof != self._bound_integrity_proof
            or not self._context._has_valid_integrity_proof()
        ):
            raise TenantBindingError(
                "TenantContext の発行証跡が不一致のため業務 SQL を開始できない"
            )

        spec = _operation_spec(operation)
        if not isinstance(spec.statement, Select):
            raise _TenantOperationError(
                "トランザクション operation は Select だけを実行できる"
            )
        session, _ = runtime
        execution_result = session.execute(
            spec.statement,
            {"tenant_id": self._bound_tenant_id},
        )
        rows = tuple(tuple(row) for row in execution_result)
        return _materialize_rows(rows)


class _TenantTransactionScope(AbstractContextManager[_TenantTransaction]):
    """Session の生成から close までを所有する内部 context manager。"""

    __slots__ = ("_context", "_handle")

    def __init__(self, context: TenantContext) -> None:
        """スコープへ一度だけ渡されたテナント文脈を保持する。

        Args:
            context: API 層から引き渡されたテナント文脈。
        """
        self._context = context
        self._handle: _TenantTransaction | None = None

    def __enter__(self) -> _TenantTransaction:
        """Session を生成し、トランザクション先頭で文脈を束縛する。

        Returns:
            Session を公開せず、束縛済み実行状態だけを参照する操作ハンドル。
        """
        if self._handle is not None:
            raise RuntimeError("同じトランザクションスコープへ再入できない")
        if type(self._context) is not TenantContext:
            raise TenantBindingError("TenantContext が無いため業務 SQL を開始できない")
        if not self._context._has_valid_integrity_proof():
            raise TenantBindingError(
                "TenantContext の発行証跡が不一致のため業務 SQL を開始できない"
            )

        bound_tenant_id = self._context.tenant_id
        bound_integrity_proof = self._context._integrity_proof

        session = Session(create_database_engine())
        exit_stack = ExitStack()
        state_key = object()
        _TRANSACTION_RUNTIMES[state_key] = (session, exit_stack)
        handle: _TenantTransaction | None = None
        try:
            handle = _TenantTransaction(
                self._context,
                state_key,
                bound_tenant_id,
                bound_integrity_proof,
                _HANDLE_CREATION_TOKEN,
            )
            self._handle = handle
            ExitStack.enter_context(
                exit_stack,
                _tenant_transaction(session, self._context),
            )
        except BaseException as primary_error:
            expired_key = state_key if handle is None else handle._expire()
            runtime = _TRANSACTION_RUNTIMES.pop(expired_key, None)
            self._handle = None
            runtime_session = session if runtime is None else runtime[0]
            try:
                runtime_session.close()
            except BaseException as close_error:
                raise primary_error from close_error
            raise
        if handle is None:
            raise RuntimeError("トランザクションハンドルを生成できない")
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
        handle = self._handle
        if handle is None:
            raise RuntimeError("開始していないトランザクションスコープを終了できない")

        expired_key = handle._expire()
        self._handle = None
        runtime = _TRANSACTION_RUNTIMES.pop(expired_key, None)
        if runtime is None:
            raise RuntimeError("トランザクションハンドルの実行状態が既に失効している")
        session, exit_stack = runtime
        try:
            exit_result = ExitStack.__exit__(
                exit_stack,
                exception_type,
                exception,
                traceback,
            )
        except BaseException as primary_error:
            try:
                session.close()
            except BaseException as close_error:
                raise primary_error from close_error
            raise

        try:
            session.close()
        except BaseException as close_error:
            if exception is not None and not exit_result:
                raise exception.with_traceback(traceback) from close_error
            raise
        return exit_result


def tenant_transaction_scope(
    context: TenantContext,
) -> AbstractContextManager[_TenantTransaction]:
    """テナント文脈を一度だけ受け取るトランザクション単位を返す。

    Args:
        context: API 層から引き渡されたテナント文脈。

    Returns:
        Session の生成・束縛・確定・取消・close を所有するスコープ。
    """
    return _TenantTransactionScope(context)
