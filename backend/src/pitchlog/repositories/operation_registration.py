"""製品 operation の文と束縛値を実行器へ渡す登録型。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.sql.dml import Insert, Update
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.selectable import Select

from pitchlog.repositories.tokens import TenantOperationToken

type PreparedOperation = tuple[Select[Any] | Insert | Update, dict[str, object]]


@dataclass(frozen=True, slots=True)
class RequiredBinding:
    """追加の列条件と、その bind に固定する値を宣言する。"""

    column: ColumnElement[object]
    parameter_name: str
    value: object


@dataclass(frozen=True, slots=True)
class OperationRegistration:
    """検査対象の文と実行時の文・パラメータ準備関数を束ねる。"""

    token_type: type[TenantOperationToken]
    capability_id: str
    statement: Select[Any] | Insert | Update
    tenant_column: ColumnElement[object]
    prepare: Callable[[TenantOperationToken], PreparedOperation]
    required_bindings: tuple[RequiredBinding, ...] = ()
    required_limit_parameter: str | None = None
    required_limit_max: int | None = None
    allowed_update_columns: frozenset[str] | None = None
