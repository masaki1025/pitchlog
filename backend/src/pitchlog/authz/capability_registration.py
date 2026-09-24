"""Capability 登録とカタログの対応を SQLAlchemy 式木だけで検査する。"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol, cast

import sqlalchemy
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import operators, visitors
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
    _anonymous_label,
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
    SelectLabelStyle,
    SelectState,
    Subquery,
    _CTEOpts,
    _OffsetLimitParam,
)
from sqlalchemy.sql.sqltypes import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Double,
    Integer,
    LargeBinary,
    NullType,
    Numeric,
    String,
    Text,
    Uuid,
    _Binary,
)
from sqlalchemy.sql.visitors import InternalTraversal

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

# この一覧はロック済み SQLAlchemy 2.0.52 の次の実装を読み合わせた結果である。
# - sql/visitors.py の InternalTraversal と sql/traversals.py の
#   _GetChildrenTraversal(visitor.iterate が子として返す状態)
# - engine/base.py の Connection._execute_clauseelement が呼ぶ
#   _execute_on_connection / _compile_w_cache
# - sql/elements.py の ClauseElement._compile_w_cache がインスタンスから読む
#   _compiler / _generate_cache_key
# - sql/cache_key.py の HasCacheKey._generate_cache_key と
#   MemoizedHasCacheKey のインスタンスメソッドキャッシュ
# - sql/selectable.py の HasPrefixes / HasSuffixes / HasHints / Select / CTE
# - sql/dml.py の Insert / Update
# - sql/elements.py の BindParameter / BinaryExpression / UnaryExpression
# - sql/functions.py の FunctionElement / Function
# - sql/base.py の Executable.execution_options / DialectKWArgs
# - sql/crud.py の _get_crud_params(表の列 default / onupdate・sentinel・
#   implicit_returning・_supplemental_returning)
# - sql/type_api.py の TypeEngine.with_variant
# - sql/compiler.py の visit_select / visit_insert / visit_update /
#   visit_binary / visit_unary / visit_function
#
# 正常な3登録を検査した後の遅延生成キーと、標準的な JOIN・サブクエリ・CTE
# などの構築例が持つキーを型ごとに採取し、下の instance exact-set へ固定した。
# 許可型の MRO に値を持つ __slots__ はなく、空の __slots__ だけであった。
# SQLAlchemy の版が変わった場合は再監査するまで拒否する。識別子は SQLAlchemy
# が引用する標準状態、型は下の組み込み型だけを許す。それ以外の状態は各検査
# 関数で空・None・標準値へ閉じる。
_AUDITED_SQLALCHEMY_VERSION = "2.0.52"
_TRAVERSED_CHILD_KINDS = (
    InternalTraversal.dp_clauseelement,
    InternalTraversal.dp_clauseelement_list,
    InternalTraversal.dp_clauseelement_tuple,
    InternalTraversal.dp_clauseelement_tuples,
    InternalTraversal.dp_string_clauseelement_dict,
    InternalTraversal.dp_fromclause_ordered_set,
    InternalTraversal.dp_setup_join_tuple,
    InternalTraversal.dp_memoized_select_entities,
    InternalTraversal.dp_dml_ordered_values,
    InternalTraversal.dp_dml_values,
)
_AUDITED_NON_CHILD_ATTRIBUTES: dict[type[object], tuple[str, ...]] = {
    Alias: ("name",),
    BinaryExpression: ("operator", "negate", "modifiers", "type"),
    BindParameter: ("key", "type", "callable", "value", "literal_execute"),
    BooleanClauseList: ("operator",),
    ClauseList: ("operator",),
    Column: ("name", "type", "is_literal"),
    CTE: ("name", "recursive", "nesting", "_prefixes", "_suffixes"),
    Exists: ("operator", "modifier"),
    False_: (),
    Function: (
        "_with_ordinality",
        "_table_value_type",
        "_with_options",
        "_with_context_options",
        "_propagate_attrs",
        "packagenames",
        "name",
        "type",
    ),
    Grouping: ("type",),
    Insert: (
        "_inline",
        "_select_names",
        "_multi_values",
        "_hints",
        "_return_defaults",
        "_sort_by_parameter_order",
        "_prefixes",
        "dialect_options",
        "_with_options",
        "_with_context_options",
        "_propagate_attrs",
        "_independent_ctes_opts",
    ),
    Join: ("isouter", "full"),
    Label: ("name", "type"),
    Null: (),
    ScalarSelect: ("type",),
    Select: (
        "_fetch_clause_options",
        "_distinct",
        "_label_style",
        "_independent_ctes_opts",
        "_prefixes",
        "_suffixes",
        "_statement_hints",
        "_hints",
        "_annotations",
        "_with_options",
        "_with_context_options",
        "_propagate_attrs",
        "dialect_options",
    ),
    Subquery: ("name",),
    Table: ("columns", "name", "schema"),
    True_: (),
    UnaryExpression: ("operator", "modifier"),
    Update: (
        "_inline",
        "_hints",
        "_return_defaults",
        "_prefixes",
        "dialect_options",
        "_with_options",
        "_with_context_options",
        "_propagate_attrs",
        "_independent_ctes_opts",
    ),
    _OffsetLimitParam: (
        "key",
        "type",
        "callable",
        "value",
        "literal_execute",
    ),
}

_ALLOWED_BINARY_OPERATOR_PAIRS = (
    (operators.eq, operators.ne),
    (operators.ne, operators.eq),
    (operators.lt, operators.ge),
    (operators.le, operators.gt),
    (operators.gt, operators.le),
    (operators.ge, operators.lt),
    (operators.is_, operators.is_not),
    (operators.is_not, operators.is_),
    (operators.in_op, operators.not_in_op),
    (operators.not_in_op, operators.in_op),
)
_ALLOWED_UNARY_OPERATOR_PAIRS = (
    (operators.inv, None),
    (operators.distinct_op, None),
    (None, operators.asc_op),
    (None, operators.desc_op),
    (None, operators.nulls_first_op),
    (None, operators.nulls_last_op),
)
_ALLOWED_SQL_TYPE_TYPES = (
    BigInteger,
    Boolean,
    DateTime,
    Double,
    Integer,
    JSONB,
    LargeBinary,
    NullType,
    Text,
    Uuid,
)
_ALLOWED_SQL_TYPE_STATE_KEYS: dict[type[object], tuple[str, ...]] = {
    BigInteger: (),
    Boolean: ("create_constraint", "name", "_create_events", "dispatch"),
    DateTime: ("timezone",),
    Double: ("precision", "asdecimal", "decimal_return_scale"),
    Integer: (),
    JSONB: ("none_as_null", "astext_type"),
    LargeBinary: ("length",),
    NullType: (),
    Text: ("length", "collation"),
    Uuid: ("as_uuid", "native_uuid"),
}
_EXPECTED_SQL_TYPE_AFFINITIES: dict[type[object], type[object]] = {
    BigInteger: Integer,
    Boolean: Boolean,
    DateTime: DateTime,
    Double: Numeric,
    Integer: Integer,
    JSONB: JSON,
    LargeBinary: _Binary,
    NullType: NullType,
    Text: String,
    Uuid: Uuid,
}
_SQL_TYPE_MEMOIZED_STATE_KEYS = ("_type_affinity", "_variant_mapping")
_ALLOWED_INSTANCE_STATE_KEYS: dict[type[object], frozenset[str]] = {
    Alias: frozenset({"_orig_name", "element", "name"}),
    BinaryExpression: frozenset(
        {
            "_is_implicitly_boolean",
            "_orig",
            "_propagate_attrs",
            "left",
            "modifiers",
            "negate",
            "operator",
            "right",
            "type",
        }
    ),
    BindParameter: frozenset(
        {
            "_identifying_key",
            "_is_clone_of",
            "_orig_key",
            "callable",
            "expand_op",
            "expanding",
            "isoutparam",
            "key",
            "literal_execute",
            "required",
            "type",
            "unique",
            "value",
        }
    ),
    BooleanClauseList: frozenset(
        {"_is_implicitly_boolean", "clauses", "group", "operator", "type"}
    ),
    ClauseList: frozenset(
        {
            "_is_implicitly_boolean",
            "_text_converter_role",
            "clauses",
            "group",
            "group_contents",
            "operator",
        }
    ),
    Column: frozenset(
        {
            "_creation_order",
            "_from_objects",
            "_insert_sentinel",
            "_memoized_keys",
            "_omit_from_statements",
            "_proxies",
            "_user_defined_nullable",
            "autoincrement",
            "base_columns",
            "comment",
            "comparator",
            "computed",
            "constraints",
            "default",
            "description",
            "dispatch",
            "doc",
            "foreign_keys",
            "identity",
            "index",
            "is_literal",
            "key",
            "name",
            "nullable",
            "onupdate",
            "primary_key",
            "proxy_set",
            "server_default",
            "server_onupdate",
            "system",
            "table",
            "type",
            "unique",
        }
    ),
    CTE: frozenset(
        {
            "_cte_alias",
            "_orig_name",
            "_restates",
            "element",
            "name",
            "nesting",
            "recursive",
        }
    ),
    Exists: frozenset({"_propagate_attrs", "element", "modifier", "operator", "type"}),
    False_: frozenset({"description", "proxy_set", "type"}),
    Function: frozenset(
        {
            "_has_args",
            "_memoized_keys",
            "clause_expr",
            "clauses",
            "name",
            "packagenames",
            "type",
        }
    ),
    Grouping: frozenset({"_propagate_attrs", "element", "type"}),
    Insert: frozenset({"_values", "dialect_options", "table"}),
    Join: frozenset({"full", "isouter", "left", "onclause", "right"}),
    Label: frozenset(
        {
            "_element",
            "_memoized_keys",
            "_proxies",
            "_tq_key_label",
            "_tq_label",
            "element",
            "key",
            "name",
            "type",
        }
    ),
    Null: frozenset({"description", "proxy_set", "type"}),
    ScalarSelect: frozenset({"_propagate_attrs", "element", "type"}),
    Select: frozenset(
        {
            "_fetch_clause",
            "_fetch_clause_options",
            "_from_obj",
            "_independent_ctes",
            "_independent_ctes_opts",
            "_label_style",
            "_limit_clause",
            "_order_by_clauses",
            "_raw_columns",
            "_where_criteria",
            "dialect_options",
        }
    ),
    Subquery: frozenset({"_orig_name", "element", "name"}),
    Table: frozenset(
        {
            "_columns",
            "_extra_dependencies",
            "_prefixes",
            "_sentinel_column",
            "c",
            "comment",
            "constraints",
            "description",
            "dispatch",
            "foreign_keys",
            "fullname",
            "implicit_returning",
            "indexes",
            "metadata",
            "name",
            "primary_key",
            "schema",
        }
    ),
    True_: frozenset({"description", "proxy_set", "type"}),
    UnaryExpression: frozenset(
        {"_propagate_attrs", "element", "modifier", "operator", "type"}
    ),
    Update: frozenset({"_values", "_where_criteria", "dialect_options", "table"}),
    _OffsetLimitParam: frozenset(
        {
            "_identifying_key",
            "_key_is_anon",
            "_orig_key",
            "callable",
            "expand_op",
            "expanding",
            "isoutparam",
            "key",
            "literal_execute",
            "required",
            "type",
            "unique",
            "value",
        }
    ),
}


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


def _reject_node_state(
    label: str,
    state_name: str,
    violations: list[str],
) -> None:
    """閉じた標準状態ではない属性を違反へ加える。"""
    violations.append(f"{label}に閉じた集合外のSQLAlchemy状態がある: {state_name}")


def _matches_sql_symbol_pair(
    operator: object,
    modifier: object,
    allowed_pairs: tuple[tuple[object, object], ...],
) -> bool:
    """演算子の組が許可した標準演算子と同一オブジェクトか確かめる。"""
    for allowed_operator, allowed_modifier in allowed_pairs:
        if operator is allowed_operator and modifier is allowed_modifier:
            return True
    return False


def _identifier_is_safe(value: object) -> bool:
    """引用指定に依存せず安全な識別子か、内部の匿名名だけを許す。"""
    if value.__class__ is _anonymous_label:
        return True
    if not isinstance(value, str) or not value:
        return False
    first = value[0]
    if not ("a" <= first <= "z" or first == "_"):
        return False
    for character in value[1:]:
        if not ("a" <= character <= "z" or "0" <= character <= "9" or character == "_"):
            return False
    return True


def _validate_traversal_contract(
    node_type: type[object],
    label: str,
    violations: list[str],
) -> None:
    """``iterate`` が返さない状態をソース監査済み一覧へ閉じる。"""
    audited_attributes = _AUDITED_NON_CHILD_ATTRIBUTES[node_type]
    audited_type = cast(Any, node_type)
    for attribute_name, traversal_kind in audited_type._traverse_internals:
        if traversal_kind in _TRAVERSED_CHILD_KINDS:
            continue
        if attribute_name not in audited_attributes:
            _reject_node_state(
                label,
                f"未監査の内部属性 {node_type.__name__}.{attribute_name}",
                violations,
            )


def _validate_sql_type(
    sql_type: object,
    label: str,
    violations: list[str],
) -> None:
    """コンパイルを差し替えられない SQLAlchemy 組み込み型だけを許す。"""
    type_class = sql_type.__class__
    if type_class not in _ALLOWED_SQL_TYPE_TYPES:
        _reject_node_state(
            label,
            f"標準外のSQL型 {type_class.__module__}.{type_class.__name__}",
            violations,
        )
        return

    standard_type = cast(Any, sql_type)
    allowed_state_keys = _ALLOWED_SQL_TYPE_STATE_KEYS[type_class]
    for state_key in standard_type.__dict__:
        if (
            state_key not in allowed_state_keys
            and state_key not in _SQL_TYPE_MEMOIZED_STATE_KEYS
        ):
            _reject_node_state(label, f"SQL型の未許可状態 {state_key}", violations)
    if (
        "_type_affinity" in standard_type.__dict__
        and standard_type.__dict__["_type_affinity"]
        is not _EXPECTED_SQL_TYPE_AFFINITIES[type_class]
    ):
        _reject_node_state(label, "SQL型の_type_affinity", violations)
    # sql/type_api.py の TypeEngine.with_variant は具象型を保ったまま方言別の
    # コンパイルを差し替えるため、標準型でも variant は空だけを許す。
    if standard_type._variant_mapping:
        _reject_node_state(label, "SQL型のvariant", violations)
    if type_class is Boolean and (
        standard_type.create_constraint is not False or standard_type.name is not None
    ):
        _reject_node_state(label, "Boolean型の追加状態", violations)
    elif type_class is Double and (
        standard_type.precision is not None
        or standard_type.asdecimal is not False
        or standard_type.decimal_return_scale is not None
    ):
        _reject_node_state(label, "Double型の追加状態", violations)
    elif type_class is JSONB:
        astext_type = standard_type.astext_type
        if (
            standard_type.none_as_null is not False
            or astext_type.__class__ is not Text
            or astext_type._variant_mapping
            or astext_type.length is not None
            or astext_type.collation is not None
        ):
            _reject_node_state(label, "JSONB型の追加状態", violations)
    elif type_class is LargeBinary and standard_type.length is not None:
        _reject_node_state(label, "LargeBinary型のlength", violations)
    elif type_class is Text and (
        standard_type.length is not None or standard_type.collation is not None
    ):
        _reject_node_state(label, "Text型のlength/collation", violations)
    elif type_class is Uuid and (
        standard_type.as_uuid is not True or standard_type.native_uuid is not True
    ):
        _reject_node_state(label, "Uuid型の追加状態", violations)


def _validate_common_node_state(
    node: ClauseElement,
    node_type: type[object],
    label: str,
    violations: list[str],
) -> None:
    """全ノードに共通するコンパイル拡張状態を拒否する。"""
    if node._annotations:
        _reject_node_state(label, "_annotations", violations)
    if node._propagate_attrs:
        _reject_node_state(label, "_propagate_attrs", violations)
    if node_type not in _ALLOWED_INSTANCE_STATE_KEYS:
        _reject_node_state(
            label,
            f"instance状態を未監査の型 {node_type.__name__}",
            violations,
        )
        return
    try:
        instance_state = node.__dict__
    except AttributeError:
        _reject_node_state(label, "instance __dict__の欠落", violations)
        return
    allowed_state_keys = _ALLOWED_INSTANCE_STATE_KEYS[node_type]
    for state_key in instance_state:
        if state_key not in allowed_state_keys:
            _reject_node_state(label, f"未許可のinstance {state_key}", violations)


def _validate_executable_state(
    node: Select | Insert | Update | Function,
    label: str,
    violations: list[str],
) -> None:
    """Executable の実行・コンパイル拡張を空へ閉じる。"""
    if node._execution_options:
        _reject_node_state(label, "execution_options", violations)
    if node._with_options:
        _reject_node_state(label, "_with_options", violations)
    if node._with_context_options:
        _reject_node_state(label, "_with_context_options", violations)


def _validate_cte_options(
    options: tuple[_CTEOpts, ...],
    label: str,
    violations: list[str],
) -> None:
    """独立 CTE の配置オプションを標準の非入れ子だけへ閉じる。"""
    for option in options:
        if option.__class__ is not _CTEOpts or option.nesting is not False:
            _reject_node_state(label, "_independent_ctes_opts", violations)


def _validate_select_state(
    node: Select,
    label: str,
    violations: list[str],
) -> None:
    """SELECT の非子状態を通常の SELECT / LIMIT / OFFSET へ閉じる。"""
    _validate_executable_state(node, label, violations)
    if node._compile_options is not SelectState.default_select_compile_options:
        _reject_node_state(label, "_compile_options", violations)
    if node._memoized_select_entities:
        _reject_node_state(label, "_memoized_select_entities", violations)
    if node._setup_joins:
        _reject_node_state(label, "_setup_joins", violations)
    if (
        node._correlate
        or node._correlate_except is not None
        or node._auto_correlate is not True
    ):
        _reject_node_state(label, "明示的な相関状態", violations)
    if node._fetch_clause is not None or node._fetch_clause_options is not None:
        _reject_node_state(label, "FETCH状態", violations)
    if node._for_update_arg is not None:
        _reject_node_state(label, "FOR UPDATE状態", violations)
    if node._distinct or node._distinct_on:
        _reject_node_state(label, "DISTINCT状態", violations)
    if node._label_style is not SelectLabelStyle.LABEL_STYLE_DISAMBIGUATE_ONLY:
        _reject_node_state(label, "select label style", violations)
    if node._prefixes:
        _reject_node_state(label, "prefix", violations)
    if node._suffixes:
        _reject_node_state(label, "suffix", violations)
    if node._statement_hints:
        _reject_node_state(label, "statement hint", violations)
    if node._hints:
        _reject_node_state(label, "table hint", violations)
    if node.dialect_options:
        _reject_node_state(label, "dialect_options", violations)
    _validate_cte_options(node._independent_ctes_opts, label, violations)


def _validate_dml_state(
    node: Insert | Update,
    label: str,
    violations: list[str],
) -> None:
    """INSERT / UPDATE の追加構文を空の既定状態へ閉じる。"""
    _validate_executable_state(node, label, violations)
    if node._inline:
        _reject_node_state(label, "inline", violations)
    if node._returning:
        _reject_node_state(label, "RETURNING", violations)
    if node._supplemental_returning is not None:
        _reject_node_state(label, "supplemental RETURNING", violations)
    if node._return_defaults or node._return_defaults_columns:
        _reject_node_state(label, "return_defaults", violations)
    if node._hints:
        _reject_node_state(label, "DML hint", violations)
    if node._prefixes:
        _reject_node_state(label, "DML prefix", violations)
    if node.dialect_options:
        _reject_node_state(label, "dialect_options", violations)
    if node._post_values_clause is not None:
        _reject_node_state(label, "post values clause", violations)
    _validate_cte_options(node._independent_ctes_opts, label, violations)

    if node.__class__ is Insert:
        if (
            node._select_names is not None
            or node.select is not None
            or node.include_insert_from_select_defaults is not False
        ):
            _reject_node_state(label, "INSERT FROM SELECT", violations)
        if node._multi_values:
            _reject_node_state(label, "複数VALUES", violations)
        if node._sort_by_parameter_order:
            _reject_node_state(label, "sort_by_parameter_order", violations)
    elif node._ordered_values is not None:
        _reject_node_state(label, "ordered_values", violations)


def _validate_bind_state(
    node: BindParameter[object],
    label: str,
    violations: list[str],
) -> None:
    """値以外の bind parameter の動的な描画・評価状態を拒否する。"""
    if node.callable is not None:
        _reject_node_state(label, "bind callable", violations)
    if node.literal_execute:
        _reject_node_state(label, "bind literal_execute", violations)
    if node.expanding:
        _reject_node_state(label, "bind expanding", violations)
    if node.expand_op is not None:
        _reject_node_state(label, "bind expand_op", violations)
    if node.isoutparam:
        _reject_node_state(label, "bind isoutparam", violations)
    if node._is_crud:
        _reject_node_state(label, "bind _is_crud", violations)


def _validate_node_state(
    node: ClauseElement,
    node_type: type[object],
    label: str,
    violations: list[str],
) -> None:
    """許可ノードについて式木外のコンパイル影響状態を検査する。"""
    _validate_traversal_contract(node_type, label, violations)
    _validate_common_node_state(node, node_type, label, violations)
    state_node = cast(Any, node)

    if node_type in {
        BinaryExpression,
        BindParameter,
        BooleanClauseList,
        Column,
        Exists,
        False_,
        Function,
        Grouping,
        Label,
        Null,
        ScalarSelect,
        True_,
        UnaryExpression,
        _OffsetLimitParam,
    }:
        _validate_sql_type(state_node.type, label, violations)

    if node_type is BinaryExpression:
        if not _matches_sql_symbol_pair(
            state_node.operator,
            state_node.negate,
            _ALLOWED_BINARY_OPERATOR_PAIRS,
        ):
            _reject_node_state(label, "binary operator/negate", violations)
        if state_node.modifiers:
            _reject_node_state(label, "binary modifiers", violations)
    elif node_type is BooleanClauseList:
        if (
            state_node.operator is not operators.and_
            and state_node.operator is not operators.or_
        ):
            _reject_node_state(label, "boolean operator", violations)
    elif node_type is ClauseList:
        if state_node.operator is not operators.comma_op:
            _reject_node_state(label, "clause-list operator", violations)
    elif node_type is UnaryExpression:
        if not _matches_sql_symbol_pair(
            state_node.operator,
            state_node.modifier,
            _ALLOWED_UNARY_OPERATOR_PAIRS,
        ):
            _reject_node_state(label, "unary operator/modifier", violations)
    elif node_type is Exists:
        if (
            state_node.operator is not operators.exists
            or state_node.modifier is not None
        ):
            _reject_node_state(label, "EXISTS operator/modifier", violations)
    elif node_type is BindParameter or node_type is _OffsetLimitParam:
        _validate_bind_state(state_node, label, violations)
    elif node_type is Column:
        if state_node.is_literal:
            _reject_node_state(label, "Column.is_literal", violations)
        if not _identifier_is_safe(state_node.name):
            _reject_node_state(label, "Column.name", violations)
    elif node_type is Function:
        _validate_executable_state(state_node, label, violations)
        if state_node._with_ordinality:
            _reject_node_state(label, "function WITH ORDINALITY", violations)
        if state_node._table_value_type is not None:
            _reject_node_state(label, "function table value type", violations)
        if state_node._has_args is not True or not state_node.clauses.clauses:
            _reject_node_state(label, "function argument state", violations)
    elif node_type is Select:
        _validate_select_state(state_node, label, violations)
    elif node_type is Insert or node_type is Update:
        _validate_dml_state(state_node, label, violations)
    elif node_type is CTE:
        if not _identifier_is_safe(state_node.name):
            _reject_node_state(label, "CTE.name", violations)
        if state_node.recursive:
            _reject_node_state(label, "recursive CTE", violations)
        if state_node.nesting:
            _reject_node_state(label, "nested CTE", violations)
        if state_node._cte_alias is not None or state_node._restates is not None:
            _reject_node_state(label, "CTE alias/restates", violations)
        if state_node._prefixes:
            _reject_node_state(label, "CTE prefix", violations)
        if state_node._suffixes:
            _reject_node_state(label, "CTE suffix", violations)
    elif node_type is Join:
        if (
            state_node.isouter is not False
            and state_node.isouter is not True
            or state_node.full is not False
            and state_node.full is not True
        ):
            _reject_node_state(label, "JOIN flags", violations)
    elif node_type is Alias or node_type is Subquery:
        if not _identifier_is_safe(state_node.name):
            _reject_node_state(label, f"{node_type.__name__}.name", violations)
    elif node_type is Label:
        if not _identifier_is_safe(state_node.name):
            _reject_node_state(label, "Label.name", violations)
    elif node_type is Table:
        if not _identifier_is_safe(state_node.name):
            _reject_node_state(label, "Table.name", violations)
        if state_node.implicit_returning is not True:
            _reject_node_state(label, "Table.implicit_returning", violations)
        if state_node._autoincrement_column is not None:
            _reject_node_state(label, "Table autoincrement column", violations)
        for column in state_node.columns:
            if column.default is not None or column.onupdate is not None:
                _reject_node_state(
                    label,
                    f"Table column default/onupdate {column.name}",
                    violations,
                )
            if column._omit_from_statements:
                _reject_node_state(
                    label,
                    f"Table column omit_from_statements {column.name}",
                    violations,
                )
            if column._insert_sentinel:
                _reject_node_state(
                    label,
                    f"Table column insert_sentinel {column.name}",
                    violations,
                )


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

        _validate_node_state(cast(ClauseElement, node), node_type, label, violations)

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
    if sqlalchemy.__version__ != _AUDITED_SQLALCHEMY_VERSION:
        raise CapabilityRegistrationError(
            (
                "SQLAlchemyの版がソース監査済み版と一致しない: "
                f"期待={_AUDITED_SQLALCHEMY_VERSION}, 実際={sqlalchemy.__version__}",
            )
        )
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
