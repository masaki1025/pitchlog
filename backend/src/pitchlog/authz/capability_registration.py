"""Capability 登録とカタログの対応を SQLAlchemy 式木だけで検査する。"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Protocol, cast

from sqlalchemy.sql import visitors
from sqlalchemy.sql.dml import Delete, Insert, Update
from sqlalchemy.sql.elements import (
    BinaryExpression,
    BindParameter,
    BooleanClauseList,
    ClauseElement,
    ClauseList,
    False_,
    Grouping,
    Label,
    Null,
    True_,
    UnaryExpression,
)
from sqlalchemy.sql.functions import Function
from sqlalchemy.sql.schema import Column, Table
from sqlalchemy.sql.selectable import (
    CTE,
    Alias,
    Exists,
    Join,
    ScalarSelect,
    Select,
    Subquery,
    _OffsetLimitParam,
)

_CATALOG_SCHEMA_VERSION = 1
_CATALOG_OPERATIONS = frozenset({"read", "insert", "update"})
_EXPECTED_CATALOG_KEYS = frozenset(
    {"schema_version", "source_classification", "capabilities"}
)
_EXPECTED_CAPABILITY_KEYS = frozenset({"capability_id", "table_id", "operation"})

# SQLAlchemy が生成する具象型を exact match する。追加の式を許すときは、
# その意味と子ノードが可視であることを試験してから、この集合へ明示的に足す。
_ALLOWED_NODE_TYPES: frozenset[type[object]] = frozenset(
    {
        Alias,
        BinaryExpression,
        BindParameter,
        BooleanClauseList,
        ClauseList,
        Column,
        CTE,
        Exists,
        False_,
        Function,
        Grouping,
        Insert,
        Join,
        Label,
        Null,
        ScalarSelect,
        Select,
        Subquery,
        Table,
        True_,
        UnaryExpression,
        Update,
        _OffsetLimitParam,
    }
)

# 名前空間と名前の双方を閉じる。現在の仮登録が必要とする副作用のない最小集合。
_ALLOWED_PG_CATALOG_FUNCTIONS = frozenset({"lower"})


class CapabilityRegistration(Protocol):
    """検査対象の登録が公開する最小の読み取り専用面。"""

    @property
    def capability_id(self) -> str:
        """カタログに登録された capability ID を返す。"""

    @property
    def statement(self) -> ClauseElement:
        """実行せずに検査する SQLAlchemy 文を返す。"""


class CapabilityRegistrationError(ValueError):
    """Capability 登録の fail-closed 検査違反を表す。

    Attributes:
        violations: 検出順に並べた違反。
    """

    def __init__(self, violations: Iterable[str]) -> None:
        """空でない違反列を保持する。

        Args:
            violations: 検出した違反。
        """
        self.violations = tuple(violations)
        if not self.violations:
            raise ValueError("違反がない状態では例外を構築できない")
        super().__init__("capability登録が不正:\n- " + "\n- ".join(self.violations))


@dataclass(frozen=True, slots=True)
class _CatalogCapability:
    """検査に必要なカタログ 1 行を保持する。"""

    table_id: str
    operation: str


def _optional(value: Mapping[str, object], key: str) -> object:
    """Mapping の省略可能な値をメソッド呼び出しなしで返す。"""
    return value[key] if key in value else None


def _required_text(
    value: object,
    label: str,
    violations: list[str],
) -> str | None:
    """空でない文字列だけを返す。"""
    if not isinstance(value, str) or not value:
        violations.append(f"{label}は空でない文字列でなければならない")
        return None
    return value


def _catalog_rows(
    catalog: Mapping[str, object],
    violations: list[str],
) -> tuple[dict[str, object], ...]:
    """カタログの行を文字列キーの object に閉じる。"""
    raw_rows = _optional(catalog, "capabilities")
    if not isinstance(raw_rows, list):
        violations.append(
            "capability-catalog.capabilitiesはobject配列でなければならない"
        )
        return ()
    rows: list[dict[str, object]] = []
    for index, raw_row in enumerate(raw_rows):
        if not isinstance(raw_row, dict) or not all(
            isinstance(key, str) for key in raw_row
        ):
            violations.append(
                f"capability-catalog.capabilities[{index}]は"
                "文字列キーのobjectでなければならない"
            )
            continue
        rows.append(cast(dict[str, object], raw_row))
    return tuple(rows)


def _catalog_index(
    catalog: Mapping[str, object],
) -> dict[str, _CatalogCapability]:
    """カタログを capability ID で引ける検証済み索引へ変換する。"""
    violations: list[str] = []
    if frozenset(catalog) != _EXPECTED_CATALOG_KEYS:
        violations.append("capability-catalogのルートキーが閉じた集合と一致しない")
    if _optional(catalog, "schema_version") != _CATALOG_SCHEMA_VERSION:
        violations.append(
            f"capability-catalog.schema_versionは{_CATALOG_SCHEMA_VERSION}"
            "でなければならない"
        )

    index: dict[str, _CatalogCapability] = {}
    for row_index, row in enumerate(_catalog_rows(catalog, violations)):
        label = f"capability-catalog.capabilities[{row_index}]"
        if frozenset(row) != _EXPECTED_CAPABILITY_KEYS:
            violations.append(f"{label}のキーが閉じた集合と一致しない")
        capability_id = _required_text(
            _optional(row, "capability_id"),
            f"{label}.capability_id",
            violations,
        )
        table_id = _required_text(
            _optional(row, "table_id"),
            f"{label}.table_id",
            violations,
        )
        operation = _required_text(
            _optional(row, "operation"),
            f"{label}.operation",
            violations,
        )
        if operation not in _CATALOG_OPERATIONS:
            violations.append(f"{label}.operationが閉じた列挙にない: {operation!r}")
        if capability_id is None or table_id is None or operation is None:
            continue
        if capability_id in index:
            violations.append(f"カタログのcapability IDが重複している: {capability_id}")
            continue
        index[capability_id] = _CatalogCapability(table_id, operation)

    if violations:
        raise CapabilityRegistrationError(violations)
    return index


def _statement_operation(statement: ClauseElement) -> str | None:
    """最上位の文型からカタログ上の操作種別を返す。"""
    statement_type = type(statement)
    if statement_type is Select:
        return "read"
    if statement_type is Insert:
        return "insert"
    if statement_type is Update:
        return "update"
    return None


def _inspect_statement(
    statement: ClauseElement,
    label: str,
    violations: list[str],
) -> frozenset[str]:
    """文を実行せず再帰走査し、参照表の集合を返す。"""
    table_ids: set[str] = set()
    for node in visitors.iterate(statement):
        node_type = type(node)
        if node_type not in _ALLOWED_NODE_TYPES:
            violations.append(
                f"{label}に閉じた集合外のSQLAlchemyノードがある: "
                f"{node_type.__module__}.{node_type.__name__}"
            )
            continue

        if isinstance(node, Table):
            if node.schema not in {None, "public"}:
                violations.append(
                    f"{label}がpublic以外の表を参照している: {node.schema}.{node.name}"
                )
            table_ids.add(node.name)

        if isinstance(node, Function):
            namespace = tuple(node.packagenames)
            if namespace != ("pg_catalog",) or (
                node.name not in _ALLOWED_PG_CATALOG_FUNCTIONS
            ):
                qualified_name = ".".join((*namespace, node.name))
                violations.append(
                    f"{label}が許可されていない関数を呼び出している: {qualified_name}"
                )

        if isinstance(node, CTE) and isinstance(
            node.element,
            (Insert, Update, Delete),
        ):
            violations.append(f"{label}にDMLのCTEが含まれている: {node.name}")

    return frozenset(table_ids)


def validate_capability_registrations(
    *,
    catalog: Mapping[str, object],
    registrations: Iterable[CapabilityRegistration],
) -> None:
    """登録 ID と文が capability カタログの 1 行へ一致するか検査する。

    SQLAlchemy の式木だけをたどり、文のコンパイルや DB 呼び出しは行わない。

    Args:
        catalog: ``capability-catalog.json`` の JSON object。
        registrations: capability ID と SQLAlchemy 文を持つ登録。

    Raises:
        CapabilityRegistrationError: 未知または重複した ID、表・操作・式木の
            不一致を検出した場合。
    """
    catalog_by_id = _catalog_index(catalog)
    violations: list[str] = []
    seen_ids: set[str] = set()

    for index, registration in enumerate(registrations):
        label = f"registrations[{index}]"
        capability_id = registration.capability_id
        statement = registration.statement
        if not isinstance(capability_id, str) or not capability_id:
            violations.append(
                f"{label}.capability_idは空でない文字列でなければならない"
            )
            continue
        if capability_id in seen_ids:
            violations.append(f"登録のcapability IDが重複している: {capability_id}")
        seen_ids.add(capability_id)

        capability = (
            catalog_by_id[capability_id] if capability_id in catalog_by_id else None
        )
        if capability is None:
            violations.append(
                f"{label}のcapability IDがカタログにない: {capability_id}"
            )

        if not isinstance(statement, ClauseElement):
            violations.append(f"{label}.statementがSQLAlchemy文ではない")
            continue
        operation = _statement_operation(statement)
        if operation is None:
            violations.append(
                f"{label}.statementの最上位コマンドがSELECT/INSERT/UPDATEではない"
            )
        table_ids = _inspect_statement(statement, label, violations)

        if capability is None:
            continue
        expected_tables = frozenset({capability.table_id})
        if table_ids != expected_tables:
            violations.append(
                f"{label}の参照表がカタログの1表と一致しない: "
                f"期待={sorted(expected_tables)}, 実際={sorted(table_ids)}"
            )
        if operation != capability.operation:
            violations.append(
                f"{label}の操作種別がカタログと一致しない: "
                f"期待={capability.operation!r}, 実際={operation!r}"
            )

    if violations:
        raise CapabilityRegistrationError(violations)
