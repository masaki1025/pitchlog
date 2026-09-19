"""閉じた operation token だけを実行するリポジトリ基底を定義する。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, is_dataclass
from datetime import date, datetime, time
from decimal import Decimal
from types import MappingProxyType
from typing import cast, final
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy.sql import Select, operators
from sqlalchemy.sql.elements import (
    BinaryExpression,
    BindParameter,
    BooleanClauseList,
    ColumnElement,
)

from pitchlog.repositories.binding import TenantBindingError, _tenant_transaction
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.repository_contract import CROSS_TENANT_FUNCTIONS
from pitchlog.repositories.tokens import (
    ImmutableValue,
    TenantOperationResult,
    TenantOperationToken,
)

__all__ = ("CROSS_TENANT_FUNCTION_REGISTRY", "TenantRepositoryBase")

CROSS_TENANT_FUNCTION_REGISTRY: frozenset[str] = frozenset(CROSS_TENANT_FUNCTIONS)


class _TenantOperationError(RuntimeError):
    """閉じた operation 契約に適合しない実行要求または結果を表す。"""


@dataclass(frozen=True, slots=True)
class _TenantScopedOperation:
    """必須テナント条件を持つ生成済み SQL を保持する。"""

    capability_id: str
    statement: Select[tuple[object, ...]]
    tenant_column: ColumnElement[object]

    def __post_init__(self) -> None:
        """SQL が明示的なテナント条件を持つことを検査する。"""
        if not _has_required_tenant_predicate(
            self.statement.whereclause,
            self.tenant_column,
        ):
            raise _TenantOperationError(
                "テナント所有操作には tenant_id = :tenant_id 条件が必要"
            )


_OPERATION_REGISTRY: Mapping[type[TenantOperationToken], _TenantScopedOperation] = (
    MappingProxyType({})
)

_IMMUTABLE_SCALAR_TYPES = (
    bool,
    int,
    float,
    str,
    bytes,
    UUID,
    Decimal,
    date,
    datetime,
    time,
)


def _has_required_tenant_predicate(
    expression: ColumnElement[bool] | None,
    tenant_column: ColumnElement[object],
) -> bool:
    """最上位の AND 条件に必須テナント等価条件があるか判定する。"""
    if isinstance(expression, BinaryExpression):
        if expression.operator is not operators.eq:
            return False
        pairs = (
            (expression.left, expression.right),
            (expression.right, expression.left),
        )
        return any(
            candidate_column.compare(tenant_column)
            and isinstance(candidate_parameter, BindParameter)
            and candidate_parameter.key == "tenant_id"
            for candidate_column, candidate_parameter in pairs
        )
    if (
        isinstance(expression, BooleanClauseList)
        and expression.operator is operators.and_
    ):
        return any(
            _has_required_tenant_predicate(clause, tenant_column)
            for clause in expression.clauses
        )
    return False


def _materialize_value(value: object) -> ImmutableValue:
    """DB 値を許可済み immutable 型へ再帰的に閉じる。"""
    if value is None or type(value) in _IMMUTABLE_SCALAR_TYPES:
        return cast(ImmutableValue, value)
    if type(value) is tuple:
        return tuple(_materialize_value(item) for item in value)
    if type(value) is frozenset:
        return frozenset(_materialize_value(item) for item in value)
    raise _TenantOperationError(
        f"実行結果に許可されていない可変または遅延型が含まれる: {type(value)!r}"
    )


def _materialize_rows(
    rows: tuple[tuple[object, ...], ...],
) -> TenantOperationResult:
    """全行をトランザクション内で immutable な結果へ実体化する。"""
    return TenantOperationResult(
        rows=tuple(tuple(_materialize_value(value) for value in row) for row in rows)
    )


def _operation_spec(operation: TenantOperationToken) -> _TenantScopedOperation:
    """Token の exact 型から生成済み operation を解決する。"""
    operation_type = type(operation)
    spec = _OPERATION_REGISTRY.get(operation_type)
    if spec is None:
        raise _TenantOperationError("未登録または偽造された operation token")
    dataclass_parameters = getattr(operation_type, "__dataclass_params__", None)
    if not is_dataclass(operation_type) or not getattr(
        dataclass_parameters, "frozen", False
    ):
        raise _TenantOperationError("operation token は frozen dataclass が必要")
    if operation.capability_id != spec.capability_id:
        raise _TenantOperationError("operation token の capability ID が不一致")
    return spec


def _validated_result(value: object) -> TenantOperationResult:
    """公開境界を越える値を exact DTO と immutable 値へ再検査する。"""
    if type(value) is not TenantOperationResult:
        raise _TenantOperationError("実行器は許可済み immutable DTO だけを返せる")
    return _materialize_rows(value.rows)


class TenantRepositoryBase(ABC):
    """生の Session や任意 SQL を公開しないリポジトリ基底。"""

    @property
    @abstractmethod
    def _session(self) -> Session:
        """具象リポジトリが内部保持するリクエスト専用 Session を返す。"""

    @final
    def execute(
        self,
        context: TenantContext,
        operation: TenantOperationToken,
    ) -> TenantOperationResult:
        """登録済みの閉じた token をテナント文脈内で実行する。

        Args:
            context: API 層から引き渡されたテナント文脈。
            operation: 生成済み registry が認識する operation token。

        Returns:
            トランザクション内で完全実体化した immutable な結果。

        Raises:
            RuntimeError: token が registry に無いか結果契約に違反する場合。
        """
        if type(context) is not TenantContext:
            raise TenantBindingError("TenantContext が無いため業務 SQL を開始できない")
        _operation_spec(operation)
        return _validated_result(self._execute_operation(context, operation))

    def _execute_operation(
        self,
        context: TenantContext,
        operation: TenantOperationToken,
    ) -> TenantOperationResult:
        """登録済み SQL を束縛済みトランザクション内だけで実行する。"""
        spec = _operation_spec(operation)
        with _tenant_transaction(self._session, context):
            execution_result = self._session.execute(
                spec.statement,
                {"tenant_id": context.tenant_id},
            )
            rows = tuple(tuple(row) for row in execution_result)
            return _materialize_rows(rows)
