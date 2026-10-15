"""固定関数だけを同一テナントスコープで実行するための登録型。"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields, is_dataclass
from types import MappingProxyType
from typing import Any
from uuid import UUID

from sqlalchemy.sql.elements import BindParameter, Label
from sqlalchemy.sql.functions import Function
from sqlalchemy.sql.selectable import Select, TableValuedAlias
from sqlalchemy.sql.sqltypes import NullType

from pitchlog.repositories.tokens import TenantOperationResult, TenantOperationToken

_IDENTIFIER = re.compile(r"[a-z_][a-z0-9_]*\Z")


class FunctionOperationError(RuntimeError):
    """固定関数の登録、入力、結果の契約違反。"""


@dataclass(frozen=True, slots=True)
class FunctionOperationRegistration:
    """単一のschema修飾関数、exact bind、戻りdecoderを固定する。"""

    operation_id: str
    token_type: type[TenantOperationToken]
    capability_id: str
    function_id: str
    statement: Select[Any]
    input_fields: tuple[tuple[str, type], ...]
    result_fields: tuple[tuple[str, type], ...]
    min_rows: int
    max_rows: int
    decoder: Callable[[TenantOperationResult], TenantOperationResult]

    def __post_init__(self) -> None:
        """登録時に任意SQLや曖昧な入出力を拒否する。"""
        if not self.operation_id or not self.capability_id:
            raise FunctionOperationError("固定関数の識別子とcapability IDが必要")
        if (
            not isinstance(self.token_type, type)
            or not issubclass(self.token_type, TenantOperationToken)
            or not is_dataclass(self.token_type)
            or not getattr(
                getattr(self.token_type, "__dataclass_params__", None), "frozen", False
            )
        ):
            raise FunctionOperationError("固定関数tokenはfrozen dataclassが必要")
        if type(self.statement) is not Select or not callable(self.decoder):
            raise FunctionOperationError("固定関数には固定Selectとdecoderが必要")
        input_names = tuple(name for name, _ in self.input_fields)
        result_names = tuple(name for name, _ in self.result_fields)
        if (
            not self.result_fields
            or len(set(input_names)) != len(input_names)
            or len(set(result_names)) != len(result_names)
            or "tenant_id" in input_names
            or any(
                _IDENTIFIER.fullmatch(name) is None
                for name in (*input_names, *result_names)
            )
            or any(
                type(field_type) is not type
                for _, field_type in (*self.input_fields, *self.result_fields)
            )
            or type(self.min_rows) is not int
            or type(self.max_rows) is not int
            or not 0 <= self.min_rows <= self.max_rows
        ):
            raise FunctionOperationError("固定関数の入出力宣言が不正")
        token_fields = {field.name for field in fields(self.token_type)}
        if not set(input_names) <= token_fields:
            raise FunctionOperationError("固定関数入力がtokenに存在しない")
        parts = self.function_id.split(".")
        if len(parts) != 2 or any(
            _IDENTIFIER.fullmatch(part) is None for part in parts
        ):
            raise FunctionOperationError("DB関数identityにはschema修飾が必要")

        selected = tuple(self.statement.selected_columns)
        froms = self.statement.get_final_froms()
        function: Function[Any]
        if len(froms) == 0 and len(selected) == 1 and type(selected[0]) is Label:
            label = selected[0]
            if label.name != result_names[0] or type(label.element) is not Function:
                raise FunctionOperationError("関数戻り列が宣言と不一致")
            function = label.element
        elif len(froms) == 1 and type(froms[0]) is TableValuedAlias:
            table = froms[0]
            if (
                tuple(column.name for column in selected) != result_names
                or any(column.table is not table for column in selected)
                or type(table.element) is not Function
            ):
                raise FunctionOperationError("関数戻り列が宣言と不一致")
            function = table.element
        else:
            raise FunctionOperationError("単一の固定関数呼出しだけを許可する")
        if (
            self.statement.whereclause is not None
            or self.statement._limit_clause is not None
            or self.statement._offset_clause is not None
            or self.statement._order_by_clauses
            or self.statement._group_by_clauses
            or self.statement._having_criteria
            or self.statement._distinct
            or self.statement._prefixes
            or self.statement._suffixes
            or self.statement._hints
            or self.statement._statement_hints
            or self.statement._independent_ctes
            or self.statement._for_update_arg is not None
            or self.statement._fetch_clause is not None
            or (function.packagenames, function.name) != ((parts[0],), parts[1])
        ):
            raise FunctionOperationError("固定関数文に追加SQLまたはidentity不一致")
        arguments = tuple(function.clauses)
        if (
            len(arguments) != len(input_names) + 1
            or any(type(arg) is not BindParameter for arg in arguments)
            or tuple(arg.key for arg in arguments) != ("tenant_id", *input_names)
            or any(arg.literal_execute or arg.expanding for arg in arguments)
        ):
            raise FunctionOperationError("固定関数のbind集合・順序が不一致")
        for argument, expected_type in zip(
            arguments,
            (UUID, *(field_type for _, field_type in self.input_fields)),
            strict=True,
        ):
            if type(argument.type) is NullType:
                continue
            try:
                bound_type = argument.type.python_type
            except NotImplementedError as error:
                raise FunctionOperationError(
                    "固定関数bindの型を判定できない"
                ) from error
            if bound_type is not expected_type:
                raise FunctionOperationError("固定関数bindの型が入力宣言と不一致")


def build_function_registry(
    registrations: tuple[FunctionOperationRegistration, ...],
    dml_token_types: frozenset[type[TenantOperationToken]],
    dml_capability_ids: frozenset[str] = frozenset(),
) -> Mapping[type[TenantOperationToken], FunctionOperationRegistration]:
    """DMLと重複しない不変の固定関数registryを作る。"""
    registry: dict[type[TenantOperationToken], FunctionOperationRegistration] = {}
    operation_ids: set[str] = set()
    for registration in registrations:
        if (
            registration.token_type in dml_token_types
            or registration.token_type in registry
            or registration.operation_id in operation_ids
            or registration.operation_id in dml_capability_ids
            or registration.capability_id in dml_capability_ids
        ):
            raise FunctionOperationError("固定関数と既存DMLのIDまたはtoken型が重複")
        registry[registration.token_type] = registration
        operation_ids.add(registration.operation_id)
    return MappingProxyType(registry)


def prepare_function_operation(
    operation: TenantOperationToken,
    tenant_id: object,
    registry: Mapping[type[TenantOperationToken], FunctionOperationRegistration],
) -> tuple[FunctionOperationRegistration, dict[str, object]]:
    """Exact token型・capability・入力型を実行直前に検証する。"""
    spec = registry.get(type(operation))
    if spec is None:
        raise FunctionOperationError("未登録または偽造された固定関数token")
    if operation.capability_id != spec.capability_id:
        raise FunctionOperationError("固定関数tokenのcapability IDが不一致")
    parameters: dict[str, object] = {"tenant_id": tenant_id}
    for name, expected_type in spec.input_fields:
        value = getattr(operation, name)
        if type(value) is not expected_type:
            raise FunctionOperationError(f"固定関数入力{name}の型が不一致")
        parameters[name] = value
    return spec, parameters


def decode_function_result(
    spec: FunctionOperationRegistration,
    result: TenantOperationResult,
) -> TenantOperationResult:
    """固定decoderの前後で行数・列数・exact型を検査する。"""
    _validate_result_shape(spec, result)
    decoded = spec.decoder(result)
    if type(decoded) is not TenantOperationResult:
        raise FunctionOperationError("固定関数decoderの戻り型が不一致")
    _validate_result_shape(spec, decoded)
    return decoded


def _validate_result_shape(
    spec: FunctionOperationRegistration,
    result: TenantOperationResult,
) -> None:
    """登録済みの行数・列・exact型から外れた結果を拒否する。"""
    if not spec.min_rows <= len(result.rows) <= spec.max_rows:
        raise FunctionOperationError("固定関数の戻り行数が不一致")
    for row in result.rows:
        if len(row) != len(spec.result_fields) or any(
            type(value) is not expected_type
            for value, (_, expected_type) in zip(row, spec.result_fields, strict=True)
        ):
            raise FunctionOperationError("固定関数の戻り列または型が不一致")
