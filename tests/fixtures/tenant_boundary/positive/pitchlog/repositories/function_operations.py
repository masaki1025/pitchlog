"""検証済みの固定関数文を組み立てる箇所だけの正例。"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import bindparam, select  # ty: ignore[unresolved-import]
from sqlalchemy.sql.functions import Function  # ty: ignore[unresolved-import]
from sqlalchemy.sql.selectable import Select  # ty: ignore[unresolved-import]
from sqlalchemy.sql.sqltypes import (  # ty: ignore[unresolved-import]
    Boolean,
    Integer,
    LargeBinary,
    String,
    Uuid,
)


def _build_fixed_function_statement(
    schema: str,
    function_name: str,
    input_fields: tuple[tuple[str, type], ...],
    result_names: tuple[str, ...],
    table_valued: bool,
) -> Select[Any]:
    """このシンボル内だけでSELECTを構築する。"""
    safe_arguments = (
        _canonical_bind("tenant_id", UUID),
        *(_canonical_bind(name, field_type) for name, field_type in input_fields),
    )
    safe_function = Function(function_name, *safe_arguments, packagenames=(schema,))
    if not table_valued:
        return select(safe_function.label(result_names[0]))
    safe_table = safe_function.table_valued(*result_names)
    return select(*(safe_table.c[name] for name in result_names))


def _canonical_bind(name: str, expected_type: type) -> Any:
    """正例fixtureの型参照を解決する。"""
    if expected_type is UUID:
        return bindparam(name, type_=Uuid())
    if expected_type is str:
        return bindparam(name, type_=String())
    if expected_type is int:
        return bindparam(name, type_=Integer())
    if expected_type is bool:
        return bindparam(name, type_=Boolean())
    if expected_type is bytes:
        return bindparam(name, type_=LargeBinary())
    raise FunctionOperationError("固定関数入力に未対応の型")


class FunctionOperationError(RuntimeError):
    """正例fixtureで未対応の型を表す。"""


def prepare_function_operation(*args: Any) -> tuple[Any, Any]:
    """別の正例fixtureからの参照を型検査時だけ解決する。"""
    return None, None


def decode_function_result(*args: Any) -> Any:
    """別の正例fixtureからの参照を型検査時だけ解決する。"""
    return None
