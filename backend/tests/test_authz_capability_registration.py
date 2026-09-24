"""Capability 登録の ID・表・操作・SQLAlchemy 式木を検査する。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pytest
import sqlalchemy
from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    SelectLabelStyle,
    Text,
    and_,
    bindparam,
    delete,
    desc,
    func,
    insert,
    literal_column,
    select,
    true,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import operators, quoted_name
from sqlalchemy.sql.base import ExecutableOption
from sqlalchemy.sql.elements import ClauseElement, UnaryExpression
from sqlalchemy.sql.schema import Table
from sqlalchemy.sql.selectable import CTE, Select
from sqlalchemy.sql.sqltypes import TableValueType
from sqlalchemy.types import UserDefinedType

from pitchlog.authz.capability_registration import (
    CapabilityRegistrationError,
    validate_capability_registrations,
)
from pitchlog.authz.classification import load_json_object
from pitchlog.db import all_models
from pitchlog.db.base import Base
from pitchlog.repositories import base as repository_base
from pitchlog.repositories import repository_contract

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_CATALOG_PATH = (
    _REPOSITORY_ROOT / "contracts" / "authz" / "product" / "capability-catalog.json"
)


@dataclass(frozen=True, slots=True)
class _Registration:
    """試験内だけで使う仮の capability 登録。"""

    capability_id: str
    statement: ClauseElement


class _CompileOption(ExecutableOption):
    """非既定のコンパイルオプションを再現する試験用オブジェクト。"""


class _OpaqueType(UserDefinedType[Any]):
    """独自コンパイルを持ち得る試験用 SQL 型。"""


@pytest.fixture(scope="module")
def catalog() -> dict[str, Any]:
    """検査対象の capability カタログを読み込む。"""
    return load_json_object(_CATALOG_PATH)


@pytest.fixture(scope="module")
def tables() -> tuple[Table, Table]:
    """モデル登録済み metadata から直接表と未宣言表を返す。"""
    assert all_models.IMPORTED_MODEL_MODULE_NAMES
    return Base.metadata.tables["games"], Base.metadata.tables["players"]


def _read_statement(games: Table) -> Select:
    return (
        select(
            games.c.id,
            func.pg_catalog.lower(games.c.game_number_label).label("game_number"),
        )
        .where(
            and_(
                games.c.tenant_id == bindparam("tenant_id"),
                games.c.status != bindparam("excluded_status"),
            )
        )
        .order_by(desc(games.c.id))
        .limit(100)
    )


def _valid_registrations(games: Table) -> tuple[_Registration, ...]:
    return (
        _Registration("CAP:games:read", _read_statement(games)),
        _Registration(
            "CAP:games:insert",
            insert(games).values(
                id=bindparam("game_id"),
                tenant_id=bindparam("tenant_id"),
            ),
        ),
        _Registration(
            "CAP:games:update",
            update(games)
            .where(
                and_(
                    games.c.id == bindparam("game_id"),
                    games.c.tenant_id == bindparam("tenant_id"),
                )
            )
            .values(status=bindparam("status")),
        ),
    )


def _assert_mutation_rejected(
    catalog: dict[str, Any],
    games: Table,
    registrations: tuple[_Registration, ...],
) -> CapabilityRegistrationError:
    """改変前の green を表明してから登録変異の拒否を確かめる。"""
    validate_capability_registrations(
        catalog=catalog,
        registrations=_valid_registrations(games),
    )
    with pytest.raises(CapabilityRegistrationError) as caught:
        validate_capability_registrations(
            catalog=catalog,
            registrations=registrations,
        )
    return caught.value


def _unknown_id(games: Table, _players: Table) -> tuple[_Registration, ...]:
    return (_Registration("CAP:not_cataloged:read", _read_statement(games)),)


def _different_table(_games: Table, players: Table) -> tuple[_Registration, ...]:
    return (_Registration("CAP:games:read", select(players.c.id)),)


def _different_operation(games: Table, _players: Table) -> tuple[_Registration, ...]:
    return (
        _Registration(
            "CAP:games:read",
            insert(games).values(id=bindparam("game_id")),
        ),
    )


def _undeclared_join(games: Table, players: Table) -> tuple[_Registration, ...]:
    statement = select(games.c.id).select_from(
        games.join(players, players.c.id == games.c.home_team_record_id)
    )
    return (_Registration("CAP:games:read", statement),)


def _undeclared_subquery(
    games: Table,
    players: Table,
) -> tuple[_Registration, ...]:
    player_id = select(players.c.id).where(
        players.c.tenant_id == bindparam("tenant_id")
    )
    statement = select(games.c.id).where(
        games.c.home_team_record_id == player_id.scalar_subquery()
    )
    return (_Registration("CAP:games:read", statement),)


def _duplicate_id(games: Table, _players: Table) -> tuple[_Registration, ...]:
    registration = _Registration("CAP:games:read", _read_statement(games))
    return registration, registration


_BINDING_MUTATIONS = (
    pytest.param(_unknown_id, id="unknown-capability-id"),
    pytest.param(_different_table, id="different-table"),
    pytest.param(_different_operation, id="different-operation"),
    pytest.param(_undeclared_join, id="undeclared-join"),
    pytest.param(_undeclared_subquery, id="undeclared-subquery"),
    pytest.param(_duplicate_id, id="duplicate-id"),
)


def test_valid_registrations_match_catalog(
    catalog: dict[str, Any],
    tables: tuple[Table, Table],
) -> None:
    """正しい ID は 1 表だけの同種コマンドへ登録できる。"""
    games, _players = tables

    validate_capability_registrations(
        catalog=catalog,
        registrations=_valid_registrations(games),
    )


@pytest.mark.parametrize("mutation", _BINDING_MUTATIONS)
def test_catalog_binding_mutation_is_rejected(
    catalog: dict[str, Any],
    tables: tuple[Table, Table],
    mutation: Callable[[Table, Table], tuple[_Registration, ...]],
) -> None:
    """未知・重複 ID と表・操作・再帰的な参照表の不一致を拒否する。"""
    games, players = tables

    _assert_mutation_rejected(catalog, games, mutation(games, players))


def _state_mutation_registration(
    mutation_name: str,
    games: Table,
    _players: Table,
) -> tuple[_Registration, ...]:
    """式木走査の外側にある状態を独立に変えた登録を作る。"""
    if mutation_name == "select-prefix":
        statement = _read_statement(games).prefix_with("/* opaque prefix */")
    elif mutation_name == "select-suffix":
        statement = _read_statement(games).suffix_with("/* opaque suffix */")
    elif mutation_name == "table-hint":
        statement = _read_statement(games).with_hint(
            games,
            "opaque table hint",
            dialect_name="postgresql",
        )
    elif mutation_name == "statement-hint":
        statement = _read_statement(games).with_statement_hint(
            "opaque statement hint",
            dialect_name="postgresql",
        )
    elif mutation_name == "schema-translate-map":
        statement = _read_statement(games).execution_options(
            schema_translate_map={None: "authz_private"}
        )
    elif mutation_name == "dialect-options":
        statement = _read_statement(games)
        statement.dialect_options["postgresql"]["opaque"] = "fragment"
    elif mutation_name == "binary-custom-operator":
        statement = select(games.c.id).where(
            games.c.id.op("opaque_operator")(bindparam("game_id"))
        )
    elif mutation_name == "unary-custom-operator":
        statement = select(games.c.id).order_by(
            UnaryExpression(
                games.c.id,
                modifier=operators.custom_op("opaque_modifier"),
            )
        )
    elif mutation_name == "binary-modifiers":
        condition = games.c.id == bindparam("game_id")
        cast(Any, condition).modifiers = {"opaque": "fragment"}
        statement = select(games.c.id).where(condition)
    elif mutation_name == "boolean-custom-operator":
        condition = and_(
            games.c.id == bindparam("game_id"),
            games.c.tenant_id == bindparam("tenant_id"),
        )
        cast(Any, condition).operator = operators.custom_op("opaque_boolean")
        statement = select(games.c.id).where(condition)
    elif mutation_name == "clause-list-custom-operator":
        function = func.pg_catalog.lower(games.c.game_number_label)
        cast(Any, function.clause_expr.element).operator = operators.custom_op(
            "opaque_list"
        )
        statement = select(games.c.id, function)
    elif mutation_name == "custom-sql-type":
        statement = select(
            games.c.id,
            bindparam("opaque", type_=_OpaqueType()),
        )
    elif mutation_name == "sql-type-variant":
        variant_type = Text().with_variant(_OpaqueType(), "postgresql")
        statement = select(
            games.c.id,
            bindparam("variant", type_=variant_type),
        )
    elif mutation_name == "jsonb-astext-type":
        statement = select(
            games.c.id,
            bindparam("jsonb_value", type_=JSONB(astext_type=_OpaqueType())),
        )
    elif mutation_name == "sql-type-instance-hook":
        hooked_type = Text()
        cast(Any, hooked_type).bind_expression = lambda _value: literal_column(
            "authz_private.evil()"
        )
        statement = select(
            games.c.id,
            bindparam("hooked_value", type_=hooked_type),
        )
    elif mutation_name == "unsafe-label-name":
        statement = select(
            games.c.id.label(quoted_name("id /* opaque */", quote=False))
        )
    elif mutation_name == "unsafe-alias-name":
        unsafe_alias = games.alias(quoted_name("g /* opaque */", quote=False))
        statement = select(games.c.id).select_from(unsafe_alias)
    elif mutation_name == "unsafe-cte-name":
        cte = select(games.c.id).cte(
            quoted_name("same_table /* opaque */", quote=False)
        )
        statement = select(games.c.id).add_cte(cte)
    elif mutation_name == "unsafe-column-name":
        unsafe_table = Table(
            "games",
            MetaData(),
            Column(quoted_name("id /* opaque */", quote=False), Text()),
        )
        statement = select(unsafe_table.c["id /* opaque */"])
    elif mutation_name == "select-distinct":
        statement = select(games.c.id).distinct()
    elif mutation_name == "select-fetch":
        statement = select(games.c.id).order_by(games.c.id).fetch(10)
    elif mutation_name == "select-correlation":
        correlated = select(games.c.id).correlate(games).scalar_subquery()
        statement = select(games.c.id).where(games.c.id == correlated)
    elif mutation_name == "select-label-style":
        statement = select(games.c.id).set_label_style(
            SelectLabelStyle.LABEL_STYLE_TABLENAME_PLUS_COL
        )
    elif mutation_name == "select-setup-join":
        statement = (
            select(games.c.id)
            .select_from(games)
            .join(
                games,
                games.c.id == games.c.id,
            )
        )
    elif mutation_name == "select-for-update":
        statement = select(games.c.id).with_for_update()
    elif mutation_name == "independent-cte-nesting":
        cte = select(games.c.id).cte("same_table")
        statement = select(games.c.id).add_cte(cte, nest_here=True)
    elif mutation_name == "recursive-cte":
        cte = select(games.c.id).cte("same_table", recursive=True)
        statement = select(games.c.id).add_cte(cte)
    elif mutation_name == "nested-cte":
        cte = select(games.c.id).cte("same_table", nesting=True)
        statement = select(games.c.id).add_cte(cte)
    elif mutation_name == "cte-prefix":
        cte = select(games.c.id).cte("same_table").prefix_with("MATERIALIZED")
        statement = select(games.c.id).add_cte(cte)
    elif mutation_name == "cte-restates":
        cte = select(games.c.id).cte("same_table")
        cast(Any, cte)._restates = select(games.c.id).cte("other_same_table")
        statement = select(games.c.id).add_cte(cte)
    elif mutation_name == "insert-inline":
        statement = insert(games).values(id=bindparam("game_id")).inline()
    elif mutation_name == "insert-returning":
        statement = insert(games).values(id=bindparam("game_id")).returning(games.c.id)
    elif mutation_name == "insert-return-defaults":
        statement = insert(games).values(id=bindparam("game_id")).return_defaults()
    elif mutation_name == "insert-supplemental-returning":
        statement = insert(games).values(id=bindparam("game_id"))
        cast(Any, statement)._supplemental_returning = (games.c.id,)
    elif mutation_name == "insert-multi-values":
        statement = insert(games).values(
            [
                {"id": bindparam("game_id_1")},
                {"id": bindparam("game_id_2")},
            ]
        )
    elif mutation_name == "insert-from-select":
        statement = insert(games).from_select(
            ["id"],
            select(games.c.id),
            include_defaults=False,
        )
    elif mutation_name == "insert-sort-parameters":
        statement = insert(games).returning(
            games.c.id,
            sort_by_parameter_order=True,
        )
    elif mutation_name == "insert-post-values":
        statement = insert(games).values(id=bindparam("game_id"))
        cast(Any, statement)._post_values_clause = true()
    elif mutation_name == "insert-table-client-default":
        unsafe_table = Table(
            "games",
            MetaData(),
            Column("id", Text(), default=literal_column("authz_private.evil()")),
        )
        statement = insert(unsafe_table)
    elif mutation_name == "insert-table-client-onupdate":
        unsafe_table = Table(
            "games",
            MetaData(),
            Column("id", Text(), onupdate=literal_column("authz_private.evil()")),
        )
        statement = insert(unsafe_table)
    elif mutation_name == "insert-table-implicit-returning":
        unsafe_table = Table(
            "games",
            MetaData(),
            Column("id", Text()),
            implicit_returning=False,
        )
        statement = insert(unsafe_table)
    elif mutation_name == "insert-table-autoincrement":
        unsafe_table = Table(
            "games",
            MetaData(),
            Column("id", Integer(), primary_key=True, autoincrement=True),
        )
        statement = insert(unsafe_table)
    elif mutation_name == "insert-column-omit":
        unsafe_table = Table(
            "games",
            MetaData(),
            Column("id", Text(), _omit_from_statements=True),
        )
        statement = insert(unsafe_table)
    elif mutation_name == "insert-column-sentinel":
        unsafe_table = Table(
            "games",
            MetaData(),
            Column("id", Text(), insert_sentinel=True),
        )
        statement = insert(unsafe_table)
    elif mutation_name == "update-ordered-values":
        statement = update(games).ordered_values(
            (games.c.status, bindparam("status")),
        )
    elif mutation_name == "dml-hint":
        statement = (
            update(games)
            .values(status=bindparam("status"))
            .with_hint(
                "opaque DML hint",
                dialect_name="postgresql",
            )
        )
    elif mutation_name == "bind-literal-execute":
        statement = select(
            games.c.id,
            bindparam("literal_value", literal_execute=True),
        )
    elif mutation_name == "bind-expanding":
        statement = select(
            games.c.id,
            bindparam("expanding_value", expanding=True),
        )
    elif mutation_name == "bind-callable":
        statement = select(
            games.c.id,
            bindparam("callable_value", callable_=lambda: "value"),
        )
    elif mutation_name == "bind-outparam":
        statement = select(
            games.c.id,
            bindparam("out_value", isoutparam=True),
        )
    elif mutation_name == "bind-crud-state":
        parameter = bindparam("crud_value")
        cast(Any, parameter)._is_crud = True
        statement = select(games.c.id, parameter)
    elif mutation_name == "function-ordinality":
        function = func.pg_catalog.lower(games.c.game_number_label)
        cast(Any, function)._with_ordinality = True
        statement = select(games.c.id, function)
    elif mutation_name == "function-table-value-type":
        function = func.pg_catalog.lower(games.c.game_number_label)
        cast(Any, function)._table_value_type = TableValueType("value")
        statement = select(games.c.id, function)
    elif mutation_name == "function-without-arguments":
        statement = select(games.c.id, func.pg_catalog.lower())
    elif mutation_name == "executable-options":
        statement = _read_statement(games).options(_CompileOption())
    elif mutation_name == "context-options":
        statement = _read_statement(games)
        cast(Any, statement)._with_context_options = ((lambda _state: None, None),)
    elif mutation_name == "propagate-attrs":
        statement = _read_statement(games)
        cast(Any, statement)._propagate_attrs = {"compile_state_plugin": "opaque"}
    elif mutation_name == "annotations":
        statement = _read_statement(games)
        cast(Any, statement)._annotations = {"opaque": True}
    elif mutation_name == "compiler-dispatch":
        statement = _read_statement(games)
        cast(Any, statement)._compiler_dispatch = lambda *_args, **_kwargs: "evil"
    elif mutation_name == "get-children-hook":
        statement = _read_statement(games)
        cast(Any, statement).get_children = lambda **_kwargs: ()
    elif mutation_name == "traverse-internals-hook":
        statement = _read_statement(games)
        cast(Any, statement)._traverse_internals = ()
    elif mutation_name == "compile-state-factory":
        statement = _read_statement(games)
        cast(Any, statement)._compile_state_factory = lambda *_args: None
    elif mutation_name == "compile-w-cache-hook":
        statement = _read_statement(games)
        cast(Any, statement)._compile_w_cache = lambda *_args, **_kwargs: None
    elif mutation_name == "execute-on-connection-hook":
        statement = _read_statement(games)
        cast(Any, statement)._execute_on_connection = lambda *_args: None
    elif mutation_name == "select-compile-options":
        statement = _read_statement(games)
        cast(Any, statement)._compile_options = object()
    elif mutation_name == "memoized-select-entities":
        statement = _read_statement(games)
        cast(Any, statement)._memoized_select_entities = (games.c.id,)
    else:
        raise AssertionError(f"未知の試験変異: {mutation_name}")

    operation = (
        "insert"
        if mutation_name.startswith("insert-")
        else "update"
        if mutation_name in {"update-ordered-values", "dml-hint"}
        else "read"
    )
    return (_Registration(f"CAP:games:{operation}", statement),)


_STATE_MUTATIONS = (
    pytest.param("select-prefix", "prefix", id="select-prefix"),
    pytest.param("select-suffix", "suffix", id="select-suffix"),
    pytest.param("table-hint", "table hint", id="table-hint"),
    pytest.param("statement-hint", "statement hint", id="statement-hint"),
    pytest.param(
        "schema-translate-map",
        "execution_options",
        id="schema-translate-map",
    ),
    pytest.param("dialect-options", "dialect_options", id="dialect-options"),
    pytest.param(
        "binary-custom-operator",
        "binary operator/negate",
        id="binary-custom-operator",
    ),
    pytest.param(
        "unary-custom-operator",
        "unary operator/modifier",
        id="unary-custom-operator",
    ),
    pytest.param("binary-modifiers", "binary modifiers", id="binary-modifiers"),
    pytest.param(
        "boolean-custom-operator",
        "boolean operator",
        id="boolean-custom-operator",
    ),
    pytest.param(
        "clause-list-custom-operator",
        "clause-list operator",
        id="clause-list-custom-operator",
    ),
    pytest.param("custom-sql-type", "標準外のSQL型", id="custom-sql-type"),
    pytest.param("sql-type-variant", "SQL型のvariant", id="sql-type-variant"),
    pytest.param(
        "jsonb-astext-type",
        "JSONB型の追加状態",
        id="jsonb-astext-type",
    ),
    pytest.param(
        "sql-type-instance-hook",
        "SQL型の未許可状態 bind_expression",
        id="sql-type-instance-hook",
    ),
    pytest.param("unsafe-label-name", "Label.name", id="unsafe-label-name"),
    pytest.param("unsafe-alias-name", "Alias.name", id="unsafe-alias-name"),
    pytest.param("unsafe-cte-name", "CTE.name", id="unsafe-cte-name"),
    pytest.param("unsafe-column-name", "Column.name", id="unsafe-column-name"),
    pytest.param("select-distinct", "DISTINCT状態", id="select-distinct"),
    pytest.param("select-fetch", "FETCH状態", id="select-fetch"),
    pytest.param("select-correlation", "明示的な相関状態", id="correlation"),
    pytest.param("select-label-style", "select label style", id="label-style"),
    pytest.param("select-setup-join", "_setup_joins", id="setup-join"),
    pytest.param("select-for-update", "FOR UPDATE状態", id="for-update"),
    pytest.param(
        "independent-cte-nesting",
        "_independent_ctes_opts",
        id="independent-cte-nesting",
    ),
    pytest.param("recursive-cte", "recursive CTE", id="recursive-cte"),
    pytest.param("nested-cte", "nested CTE", id="nested-cte"),
    pytest.param("cte-prefix", "CTE prefix", id="cte-prefix"),
    pytest.param("cte-restates", "CTE alias/restates", id="cte-restates"),
    pytest.param("insert-inline", "inline", id="insert-inline"),
    pytest.param("insert-returning", "RETURNING", id="insert-returning"),
    pytest.param(
        "insert-return-defaults",
        "return_defaults",
        id="insert-return-defaults",
    ),
    pytest.param(
        "insert-supplemental-returning",
        "supplemental RETURNING",
        id="insert-supplemental-returning",
    ),
    pytest.param("insert-multi-values", "複数VALUES", id="insert-multi-values"),
    pytest.param(
        "insert-from-select",
        "INSERT FROM SELECT",
        id="insert-from-select",
    ),
    pytest.param(
        "insert-sort-parameters",
        "sort_by_parameter_order",
        id="insert-sort-parameters",
    ),
    pytest.param(
        "insert-post-values",
        "post values clause",
        id="insert-post-values",
    ),
    pytest.param(
        "insert-table-client-default",
        "Table column default/onupdate",
        id="insert-table-client-default",
    ),
    pytest.param(
        "insert-table-client-onupdate",
        "Table column default/onupdate",
        id="insert-table-client-onupdate",
    ),
    pytest.param(
        "insert-table-implicit-returning",
        "Table.implicit_returning",
        id="insert-table-implicit-returning",
    ),
    pytest.param(
        "insert-table-autoincrement",
        "Table autoincrement column",
        id="insert-table-autoincrement",
    ),
    pytest.param(
        "insert-column-omit",
        "Table column omit_from_statements",
        id="insert-column-omit",
    ),
    pytest.param(
        "insert-column-sentinel",
        "Table column insert_sentinel",
        id="insert-column-sentinel",
    ),
    pytest.param(
        "update-ordered-values",
        "ordered_values",
        id="update-ordered-values",
    ),
    pytest.param("dml-hint", "DML hint", id="dml-hint"),
    pytest.param(
        "bind-literal-execute",
        "bind literal_execute",
        id="bind-literal-execute",
    ),
    pytest.param("bind-expanding", "bind expanding", id="bind-expanding"),
    pytest.param("bind-callable", "bind callable", id="bind-callable"),
    pytest.param("bind-outparam", "bind isoutparam", id="bind-outparam"),
    pytest.param("bind-crud-state", "bind _is_crud", id="bind-crud-state"),
    pytest.param(
        "function-ordinality",
        "function WITH ORDINALITY",
        id="function-ordinality",
    ),
    pytest.param(
        "function-table-value-type",
        "function table value type",
        id="function-table-value-type",
    ),
    pytest.param(
        "function-without-arguments",
        "function argument state",
        id="function-without-arguments",
    ),
    pytest.param("executable-options", "_with_options", id="executable-options"),
    pytest.param("context-options", "_with_context_options", id="context-options"),
    pytest.param("propagate-attrs", "_propagate_attrs", id="propagate-attrs"),
    pytest.param("annotations", "_annotations", id="annotations"),
    pytest.param(
        "compiler-dispatch",
        "instance _compiler_dispatch",
        id="compiler-dispatch",
    ),
    pytest.param(
        "get-children-hook",
        "instance get_children",
        id="get-children-hook",
    ),
    pytest.param(
        "traverse-internals-hook",
        "instance _traverse_internals",
        id="traverse-internals-hook",
    ),
    pytest.param(
        "compile-state-factory",
        "instance _compile_state_factory",
        id="compile-state-factory",
    ),
    pytest.param(
        "compile-w-cache-hook",
        "instance _compile_w_cache",
        id="compile-w-cache-hook",
    ),
    pytest.param(
        "execute-on-connection-hook",
        "instance _execute_on_connection",
        id="execute-on-connection-hook",
    ),
    pytest.param(
        "select-compile-options",
        "_compile_options",
        id="select-compile-options",
    ),
    pytest.param(
        "memoized-select-entities",
        "_memoized_select_entities",
        id="memoized-select-entities",
    ),
)


@pytest.mark.parametrize(("mutation_name", "expected_state"), _STATE_MUTATIONS)
def test_non_tree_sql_state_mutation_is_rejected(
    catalog: dict[str, Any],
    tables: tuple[Table, Table],
    mutation_name: str,
    expected_state: str,
) -> None:
    """式木の型が安全でも SQL を変える非既定状態を独立に拒否する。"""
    games, players = tables
    error = _assert_mutation_rejected(
        catalog,
        games,
        _state_mutation_registration(mutation_name, games, players),
    )

    assert any(expected_state in item for item in error.violations)


def test_unaudited_sqlalchemy_version_is_rejected(
    catalog: dict[str, Any],
    tables: tuple[Table, Table],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ソース未監査の SQLAlchemy 版へ更新した状態を拒否する。"""
    games, _players = tables
    validate_capability_registrations(
        catalog=catalog,
        registrations=_valid_registrations(games),
    )
    monkeypatch.setattr(sqlalchemy, "__version__", "unaudited-version")

    with pytest.raises(CapabilityRegistrationError, match="ソース監査済み版"):
        validate_capability_registrations(
            catalog=catalog,
            registrations=_valid_registrations(games),
        )


def test_user_defined_scalar_function_is_rejected(
    catalog: dict[str, Any],
    tables: tuple[Table, Table],
) -> None:
    """SELECT 句のユーザー定義スカラー関数を拒否する。"""
    games, _players = tables
    statement = select(
        games.c.id,
        func.authz_private.evil(games.c.id),
    )

    error = _assert_mutation_rejected(
        catalog,
        games,
        (_Registration("CAP:games:read", statement),),
    )

    assert any("許可されていない関数" in item for item in error.violations)


def test_user_defined_table_valued_function_is_rejected(
    catalog: dict[str, Any],
    tables: tuple[Table, Table],
) -> None:
    """FROM 句のユーザー定義テーブル関数を拒否する。"""
    games, _players = tables
    evil_rows = func.authz_private.evil().table_valued("value")
    statement = select(games.c.id).select_from(games.join(evil_rows, true()))

    error = _assert_mutation_rejected(
        catalog,
        games,
        (_Registration("CAP:games:read", statement),),
    )

    assert any("許可されていない関数" in item for item in error.violations)


def test_opaque_sql_fragment_is_rejected(
    catalog: dict[str, Any],
    tables: tuple[Table, Table],
) -> None:
    """Literal column に埋め込んだ不透明な SQL 断片を拒否する。"""
    games, _players = tables
    statement = select(
        games.c.id,
        literal_column("authz_private.evil()"),
    )

    error = _assert_mutation_rejected(
        catalog,
        games,
        (_Registration("CAP:games:read", statement),),
    )

    assert any("閉じた集合外" in item for item in error.violations)


def _insert_cte(games: Table) -> CTE:
    return insert(games).values(id=bindparam("side_effect_id")).cte("side_effect")


def _update_cte(games: Table) -> CTE:
    return (
        update(games)
        .where(games.c.id == bindparam("side_effect_id"))
        .values(status=bindparam("side_effect_status"))
        .cte("side_effect")
    )


def _delete_cte(games: Table) -> CTE:
    return (
        delete(games)
        .where(games.c.id == bindparam("side_effect_id"))
        .cte("side_effect")
    )


@pytest.mark.parametrize(
    "cte_factory",
    (
        pytest.param(_insert_cte, id="insert"),
        pytest.param(_update_cte, id="update"),
        pytest.param(_delete_cte, id="delete"),
    ),
)
def test_unreferenced_dml_cte_is_rejected(
    catalog: dict[str, Any],
    tables: tuple[Table, Table],
    cte_factory: Callable[[Table], CTE],
) -> None:
    """読み取り文へ add_cte した未参照の DML CTE を再帰的に拒否する。"""
    games, _players = tables
    statement = select(games.c.id).add_cte(cte_factory(games))

    error = _assert_mutation_rejected(
        catalog,
        games,
        (_Registration("CAP:games:read", statement),),
    )

    assert any("DMLのCTE" in item for item in error.violations)


def test_product_registries_remain_empty() -> None:
    """本ステップでは製品の capability と operation を登録しない。"""
    assert repository_contract.PRODUCT_CAPABILITY_IDS == ()
    assert repository_contract.PRODUCT_OPERATION_TOKEN_TYPES == ()
    assert repository_contract.CROSS_TENANT_FUNCTIONS == ()
    assert repository_base._OPERATION_REGISTRY == {}
