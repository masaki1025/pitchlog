"""閉じた operation token だけを実行するリポジトリ基底を定義する。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, is_dataclass, replace
from datetime import date, datetime, time
from decimal import Decimal
from types import MappingProxyType
from typing import Any, cast, final
from uuid import UUID

from sqlalchemy import Column, Table
from sqlalchemy.engine import Result
from sqlalchemy.orm import Session
from sqlalchemy.sql import operators
from sqlalchemy.sql.dml import Insert, Update
from sqlalchemy.sql.elements import (
    BinaryExpression,
    BindParameter,
    BooleanClauseList,
    ColumnElement,
)
from sqlalchemy.sql.selectable import Select

from pitchlog.authz.capability_catalog import (
    CATALOG_SCHEMA_VERSION,
    CLASSIFICATION_SOURCE,
)
from pitchlog.authz.capability_registration import (
    CapabilityRegistrationError,
    validate_capability_registrations,
)
from pitchlog.repositories.binding import TenantBindingError, _tenant_transaction
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.operation_registration import (
    OperationRegistration,
    PreparedOperation,
)
from pitchlog.repositories.operation_registry import PRODUCT_OPERATIONS
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
    statement: Select[Any] | Insert | Update
    tenant_column: ColumnElement[object]

    def __post_init__(self) -> None:
        """SQL が明示的なテナント条件を持つことを検査する。"""
        if isinstance(self.statement, Insert):
            tenant_value = (
                self.statement._values.get("tenant_id")
                if self.statement._values
                else None
            )
            valid_tenant = (
                self.statement.table.c.tenant_id.compare(self.tenant_column)
                and isinstance(tenant_value, BindParameter)
                and tenant_value.key == "tenant_id"
            )
        elif isinstance(self.statement, (Select, Update)):
            valid_tenant = _has_required_bound_equality(
                self.statement.whereclause,
                self.tenant_column,
                "tenant_id",
            )
        else:
            valid_tenant = False
        if not valid_tenant:
            raise _TenantOperationError(
                "テナント所有操作には tenant_id = :tenant_id 条件が必要"
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


def _has_required_bound_equality(
    expression: ColumnElement[bool] | None,
    required_column: ColumnElement[object],
    parameter_name: str,
) -> bool:
    """最上位の AND 条件に指定列と bind の等価条件があるか判定する。"""
    if isinstance(expression, BinaryExpression):
        if expression.operator is not operators.eq:
            return False
        pairs = (
            (expression.left, expression.right),
            (expression.right, expression.left),
        )
        return any(
            candidate_column.compare(required_column)
            and isinstance(candidate_parameter, BindParameter)
            and candidate_parameter.key == parameter_name
            for candidate_column, candidate_parameter in pairs
        )
    if (
        isinstance(expression, BooleanClauseList)
        and expression.operator is operators.and_
    ):
        return any(
            _has_required_bound_equality(clause, required_column, parameter_name)
            for clause in expression.clauses
        )
    return False


def _validate_prepared_statement(
    spec: OperationRegistration,
    statement: Select[Any] | Insert | Update,
    parameters: Mapping[str, object] | None = None,
) -> None:
    """実行文を capability の操作・単一表と行識別条件へ閉じる。"""
    parts = spec.capability_id.split(":")
    tenant_column = spec.tenant_column
    if len(parts) != 3 or parts[0] != "CAP" or not isinstance(tenant_column, Column):
        raise _TenantOperationError("capability 登録の識別子またはテナント列が不正")
    tenant_table = tenant_column.table
    if not isinstance(tenant_table, Table) or tenant_table.name != parts[1]:
        raise _TenantOperationError("capability の対象表とテナント列の表が不一致")
    catalog: dict[str, object] = {
        "schema_version": CATALOG_SCHEMA_VERSION,
        "source_classification": CLASSIFICATION_SOURCE,
        "capabilities": [
            {
                "capability_id": spec.capability_id,
                "table_id": parts[1],
                "operation": parts[2],
            }
        ],
    }
    try:
        validate_capability_registrations(
            catalog=catalog,
            registrations=(replace(spec, statement=statement),),
        )
    except CapabilityRegistrationError as error:
        raise _TenantOperationError(str(error)) from error
    if isinstance(statement, Update) and not _has_required_bound_equality(
        statement.whereclause,
        tenant_table.c.id,
        "id",
    ):
        raise _TenantOperationError("UPDATE には対象表の id = :id 条件が必要")
    if isinstance(statement, Update):
        allowed_columns = spec.allowed_update_columns
        if not allowed_columns or not statement._values:
            raise _TenantOperationError("UPDATE SET には許可済み列が 1 件以上必要")
        set_columns: set[str] = set()
        for key in statement._values:
            column = (
                statement.table.c.get(key)
                if type(key) is str
                else key
                if isinstance(key, Column)
                else None
            )
            if not isinstance(column, Column) or column.table is not statement.table:
                raise _TenantOperationError("UPDATE SET に対象表以外の列がある")
            set_columns.add(column.key)
        if not set_columns <= allowed_columns:
            raise _TenantOperationError(
                f"UPDATE SET に未許可列がある: {sorted(set_columns - allowed_columns)}"
            )
    elif spec.allowed_update_columns is not None:
        raise _TenantOperationError("UPDATE 以外には SET 列の宣言を使えない")
    for required in spec.required_bindings:
        if isinstance(statement, Insert):
            column_key = required.column.key
            column = (
                statement.table.c.get(column_key)
                if isinstance(column_key, str)
                else None
            )
            bound_value = (
                statement._values.get(column_key)
                if statement._values and isinstance(column_key, str)
                else None
            )
            present = (
                column is not None
                and column.compare(required.column)
                and isinstance(bound_value, BindParameter)
                and bound_value.key == required.parameter_name
            )
        else:
            present = _has_required_bound_equality(
                statement.whereclause,
                required.column,
                required.parameter_name,
            )
        if not present:
            raise _TenantOperationError(
                f"{spec.capability_id} には {required.column.key} = "
                f":{required.parameter_name} 条件が必要"
            )
        if parameters is not None:
            value = parameters.get(required.parameter_name)
            if type(value) is not type(required.value) or value != required.value:
                raise _TenantOperationError(
                    f"{spec.capability_id} の {required.parameter_name} 束縛値が不正"
                )
    limit_parameter = spec.required_limit_parameter
    if limit_parameter is not None:
        max_limit = spec.required_limit_max
        if type(max_limit) is not int or max_limit < 1:
            raise _TenantOperationError("LIMIT の上限宣言は正の整数が必要")
        limit_clause = (
            statement._limit_clause if isinstance(statement, Select) else None
        )
        if not isinstance(limit_clause, BindParameter) or (
            limit_clause.key != limit_parameter
        ):
            raise _TenantOperationError(
                f"{spec.capability_id} には LIMIT :{limit_parameter} が必要"
            )
        if parameters is not None:
            limit_value = parameters.get(limit_parameter)
            if type(limit_value) is not int or not 1 <= limit_value <= max_limit:
                raise _TenantOperationError(f"LIMIT の束縛値は 1〜{max_limit} が必要")
    elif spec.required_limit_max is not None:
        raise _TenantOperationError("LIMIT の上限宣言には bind 名が必要")


def _build_operation_registry() -> Mapping[
    type[TenantOperationToken], OperationRegistration
]:
    """登録文を検査して token 型から引ける不変表を作る。"""
    registrations: dict[type[TenantOperationToken], OperationRegistration] = {}
    for registration in PRODUCT_OPERATIONS:
        _TenantScopedOperation(
            registration.capability_id,
            registration.statement,
            registration.tenant_column,
        )
        _validate_prepared_statement(registration, registration.statement)
        if registration.token_type in registrations:
            raise _TenantOperationError("operation token 型の登録が重複している")
        registrations[registration.token_type] = registration
    return MappingProxyType(registrations)


_OPERATION_REGISTRY = _build_operation_registry()


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


def _operation_spec(operation: TenantOperationToken) -> OperationRegistration:
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


def _prepare_operation(
    operation: TenantOperationToken,
    tenant_id: UUID,
) -> PreparedOperation:
    """Token から文と束縛値を作り、実行直前に全登録条件を検査する。"""
    spec = _operation_spec(operation)
    statement, prepared_parameters = spec.prepare(operation)
    parameters = dict(prepared_parameters)
    parameters["tenant_id"] = tenant_id
    _TenantScopedOperation(spec.capability_id, statement, spec.tenant_column)
    _validate_prepared_statement(spec, statement, parameters)
    return statement, parameters


def _materialize_execution_result(
    statement: Select[Any] | Insert | Update,
    execution_result: Result[Any],
) -> TenantOperationResult:
    """実行済みの結果を不変 DTO へ閉じる。"""
    if not isinstance(statement, Select):
        rowcount = getattr(execution_result, "rowcount", None)
        if type(rowcount) is not int:
            raise _TenantOperationError("更新件数を取得できない")
        return _materialize_rows(((rowcount,),))
    rows = tuple(tuple(row) for row in execution_result)
    return _materialize_rows(rows)


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
        if not context._has_valid_integrity_proof():
            raise TenantBindingError(
                "TenantContext の発行証跡が不一致のため業務 SQL を開始できない"
            )
        _operation_spec(operation)
        return _validated_result(self._execute_operation(context, operation))

    def _execute_operation(
        self,
        context: TenantContext,
        operation: TenantOperationToken,
    ) -> TenantOperationResult:
        """登録済み SQL を束縛済みトランザクション内だけで実行する。"""
        with _tenant_transaction(self._session, context):
            statement, parameters = _prepare_operation(operation, context.tenant_id)
            execution_result = self._session.execute(
                statement,
                parameters,
            )
            return _materialize_execution_result(statement, execution_result)
