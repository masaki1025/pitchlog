"""製品カタログ検査の閉じた問い合わせ境界と exact-set を検査する。

保証する参照は静的な絶対・別名・相対・名前付き再 export とモジュール属性までとする。
文字列 getattr・importlib・__import__・globals による動的な参照は保証しない。
"""

from __future__ import annotations

import ast
import json
from collections.abc import Iterator
from enum import Enum
from pathlib import Path
from typing import Any, cast

import psycopg
import pytest

from pitchlog.authz import product_catalog
from pitchlog.authz.asset_spec import PRODUCT_SPEC
from pitchlog.authz.product_catalog import (
    CatalogQueryId,
    ProductCatalogError,
    inspect_product_authz_catalog,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_SOURCE_ROOT = _REPOSITORY_ROOT / "backend/src"
_SOURCE_PATH = _REPOSITORY_ROOT / "backend/src/pitchlog/authz/product_catalog.py"
_TERMINAL_MODULE = "pitchlog.authz.product_catalog"
_TERMINAL_NAME = "_fetch_catalog_rows"
_EXPECTED_TERMINAL_SIGNATURE = (
    "_fetch_catalog_rows(connection: psycopg.Connection[Any], "
    "query_id: CatalogQueryId, params: tuple[object, ...]) -> "
    "list[tuple[object, ...]]"
)
_DB_METHOD_NAMES = {"cursor", "execute", "commit", "rollback"}


class _FakeCursor:
    """末端が選んだ問い合わせと束縛値を記録する cursor。"""

    def __init__(self, connection: _FakeConnection) -> None:
        self._connection = connection

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object,
    ) -> None:
        del exc_type, exc_value, traceback

    def __iter__(self) -> Iterator[tuple[object, ...]]:
        return iter(self._connection.rows)

    def execute(self, query: object, params: tuple[object, ...]) -> None:
        """固定 SQL と束縛値を記録する。"""
        self._connection.executions.append((query, params))


class _FakeConnection:
    """末端の cursor 呼び出しだけを観測する試験用接続。"""

    def __init__(self, rows: list[tuple[object, ...]] | None = None) -> None:
        self.rows = [] if rows is None else rows
        self.cursor_count = 0
        self.executions: list[tuple[object, tuple[object, ...]]] = []

    def cursor(self) -> _FakeCursor:
        """試験用 cursor を返す。"""
        self.cursor_count += 1
        return _FakeCursor(self)


def _as_psycopg_connection(
    connection: _FakeConnection,
) -> psycopg.Connection[Any]:
    """試験用接続を公開 API の型境界へ明示的に渡す。"""
    return cast(psycopg.Connection[Any], connection)


def _module_name(source_root: Path, path: Path) -> str:
    """Backend source のパスを import 可能なモジュール名へ変換する。"""
    relative = path.relative_to(source_root).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _source_modules(source_root: Path) -> dict[str, tuple[Path, str]]:
    """Source root 以下の全 Python モジュールを機械的に読む。"""
    return {
        _module_name(source_root, path): (path, path.read_text(encoding="utf-8"))
        for path in source_root.rglob("*.py")
    }


def _dotted_name(node: ast.expr) -> str | None:
    """Name/Attribute だけの式をドット区切り名へ戻す。"""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _dotted_name(node.value)
        if prefix is not None:
            return f"{prefix}.{node.attr}"
    return None


def _function_ancestors(tree: ast.Module) -> dict[ast.AST, str]:
    """各 AST node を包含する最内の関数名へ対応付ける。"""
    result: dict[ast.AST, str] = {}

    def visit(node: ast.AST, function_name: str = "<module>") -> None:
        next_name = node.name if isinstance(node, ast.FunctionDef) else function_name
        result[node] = next_name
        for child in ast.iter_child_nodes(node):
            visit(child, next_name)

    visit(tree)
    return result


def _absolute_import_from(
    module_name: str,
    path: Path,
    node: ast.ImportFrom,
) -> str | None:
    """ImportFrom の level と現在位置から import 元の絶対名を返す。"""
    if node.level == 0:
        return node.module
    current_package = (
        module_name if path.name == "__init__.py" else module_name.rpartition(".")[0]
    )
    package_parts = current_package.split(".") if current_package else []
    parent_count = node.level - 1
    if parent_count > len(package_parts):
        return None
    base_parts = package_parts[: len(package_parts) - parent_count]
    if node.module is not None:
        base_parts.extend(node.module.split("."))
    return ".".join(base_parts) if base_parts else None


def _static_import_bindings(
    modules: dict[str, tuple[Path, str]],
    trees: dict[str, ast.Module],
) -> dict[str, dict[str, tuple[str, str]]]:
    """静的 import と名前付き再 export の由来を固定点まで解決する。"""
    bindings: dict[str, dict[str, tuple[str, str]]] = {
        module_name: {} for module_name in modules
    }
    bindings[_TERMINAL_MODULE][_TERMINAL_NAME] = (
        "symbol",
        f"{_TERMINAL_MODULE}.{_TERMINAL_NAME}",
    )
    for module_name, tree in trees.items():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Import):
                continue
            for alias in node.names:
                local_name = alias.asname or alias.name.partition(".")[0]
                imported_module = alias.name if alias.asname else local_name
                bindings[module_name][local_name] = ("module", imported_module)

    changed = True
    while changed:
        changed = False
        for module_name, tree in trees.items():
            path = modules[module_name][0]
            for node in ast.walk(tree):
                if not isinstance(node, ast.ImportFrom):
                    continue
                imported_from = _absolute_import_from(module_name, path, node)
                if imported_from is None:
                    continue
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    local_name = alias.asname or alias.name
                    imported_name = f"{imported_from}.{alias.name}"
                    origin: tuple[str, str] | None = None
                    if imported_name in modules:
                        origin = ("module", imported_name)
                    elif imported_from in bindings:
                        origin = bindings[imported_from].get(alias.name)
                    if (
                        origin is None
                        or bindings[module_name].get(local_name) == origin
                    ):
                        continue
                    bindings[module_name][local_name] = origin
                    changed = True
    return bindings


def _resolve_dotted_binding(
    module_name: str,
    dotted: str,
    bindings: dict[str, dict[str, tuple[str, str]]],
    module_names: frozenset[str],
) -> tuple[str, str] | None:
    """モジュール属性と再 export を辿ってドット式の由来を返す。"""
    parts = dotted.split(".")
    origin = bindings[module_name].get(parts[0])
    if origin is None:
        return ("symbol", dotted)
    for attribute in parts[1:]:
        origin_kind, origin_name = origin
        if origin_kind != "module":
            return None
        exported = bindings.get(origin_name, {}).get(attribute)
        if exported is not None:
            origin = exported
            continue
        candidate = f"{origin_name}.{attribute}"
        if candidate in module_names or _TERMINAL_MODULE.startswith(f"{candidate}."):
            origin = ("module", candidate)
        else:
            origin = ("symbol", candidate)
    return origin


def _terminal_references(
    module_name: str,
    tree: ast.Module,
    bindings: dict[str, dict[str, tuple[str, str]]],
    module_names: frozenset[str],
) -> tuple[tuple[ast.expr, str], ...]:
    """静的 import の由来を解決して末端シンボルの全参照を返す。"""
    terminal_symbol = ("symbol", f"{_TERMINAL_MODULE}.{_TERMINAL_NAME}")
    ancestors = _function_ancestors(tree)
    references: list[tuple[ast.expr, str]] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Load)
            and bindings[module_name].get(node.id) == terminal_symbol
        ):
            references.append((node, ancestors[node]))
            continue
        if not isinstance(node, ast.Attribute) or not isinstance(node.ctx, ast.Load):
            continue
        dotted = _dotted_name(node)
        if dotted is None:
            continue
        resolved = _resolve_dotted_binding(
            module_name,
            dotted,
            bindings,
            module_names,
        )
        if resolved == terminal_symbol or (
            module_name == _TERMINAL_MODULE and node.attr == _TERMINAL_NAME
        ):
            references.append((node, ancestors[node]))
    return tuple(references)


def _validate_terminal_boundary(source_root: Path) -> None:
    """全 backend/src で末端のシグネチャ・参照集合を検査する。"""
    modules = _source_modules(source_root)
    if _TERMINAL_MODULE not in modules:
        raise AssertionError("製品カタログモジュールが存在しない")
    trees = {
        module_name: ast.parse(source, filename=str(path))
        for module_name, (path, source) in modules.items()
    }
    bindings = _static_import_bindings(modules, trees)
    module_names = frozenset(modules)
    tree = trees[_TERMINAL_MODULE]
    terminals = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_fetch_catalog_rows"
    ]
    if len(terminals) != 1:
        raise AssertionError("製品カタログの DB 末端が一意でない")
    terminal = terminals[0]
    if terminal.returns is None:
        raise AssertionError("製品カタログの DB 末端に戻り値注釈がない")
    signature = (
        f"{terminal.name}({ast.unparse(terminal.args)}) -> "
        f"{ast.unparse(terminal.returns)}"
    )
    if signature != _EXPECTED_TERMINAL_SIGNATURE:
        raise AssertionError("製品カタログの DB 末端シグネチャが登録値と違う")

    references: list[str] = []
    for observed_module, module_tree in trees.items():
        parents = {
            child: parent
            for parent in ast.walk(module_tree)
            for child in ast.iter_child_nodes(parent)
        }
        for node, function_name in _terminal_references(
            observed_module,
            module_tree,
            bindings,
            module_names,
        ):
            parent = parents.get(node)
            if not isinstance(parent, ast.Call) or parent.func is not node:
                raise AssertionError(
                    "製品カタログの DB 末端が直接呼び出し以外で参照された"
                )
            references.append(f"{observed_module}.{function_name}")
    if references != ["pitchlog.authz.product_catalog.inspect_product_authz_catalog"]:
        raise AssertionError("製品カタログの DB 末端参照が exact-set でない")

    ancestors = _function_ancestors(tree)
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _DB_METHOD_NAMES
        ):
            continue
        if ancestors[node] != "_fetch_catalog_rows":
            raise AssertionError("DB 呼び出しが製品カタログの末端外にある")


def _asset_policy_expressions() -> dict[tuple[str, str], tuple[object, object]]:
    """Staged 資産のポリシー式を PostgreSQL 観測値の原文として返す。"""
    asset_path = _REPOSITORY_ROOT / PRODUCT_SPEC.ddl_elements_path
    asset = json.loads(asset_path.read_text(encoding="utf-8"))
    assert isinstance(asset, dict)
    policies = asset.get("policies")
    assert isinstance(policies, list)
    assert all(isinstance(row, dict) for row in policies)
    return {
        (str(row["table_id"]), f"pitchlog_app_{row['profile']}"): (
            row.get("using_expression"),
            row.get("with_check_expression"),
        )
        for row in policies
        if isinstance(row, dict)
    }


def _raw_catalog_rows(
    privileged_role_oid: int,
) -> dict[CatalogQueryId, list[tuple[object, ...]]]:
    """正規資産の期待値と一致する PostgreSQL 形式の観測行を作る。"""
    expectations = product_catalog._load_product_expectations()
    role_rows: list[tuple[object, ...]] = []
    owner_oid = 100
    for index, role in enumerate(expectations.roles):
        role_oid = owner_oid if role[0] == "pitchlog_owner" else owner_oid + index + 1
        role_rows.append((role_oid, *role))

    command_codes = {
        "all": "*",
        "select": "r",
        "insert": "a",
        "update": "w",
        "delete": "d",
    }
    policy_expressions = _asset_policy_expressions()
    policy_rows: list[tuple[object, ...]] = [
        (
            row[0],
            row[1],
            row[2],
            command_codes[str(row[3])],
            list(cast(tuple[object, ...], row[4])),
            row[5] == "permissive",
            policy_expressions[(str(row[1]), str(row[2]))][0],
            policy_expressions[(str(row[1]), str(row[2]))][1],
        )
        for row in expectations.policies
    ]
    return {
        CatalogQueryId.ROLES: role_rows,
        CatalogQueryId.DATABASE: [("pitchlog_product", expectations.database_owner)],
        CatalogQueryId.DATABASE_ACL: list(expectations.database_acl),
        CatalogQueryId.SCHEMAS: list(expectations.schemas),
        CatalogQueryId.SCHEMA_ACL: list(expectations.schema_acl),
        CatalogQueryId.TABLES: list(expectations.tables),
        CatalogQueryId.POLICIES: policy_rows,
        CatalogQueryId.TABLE_ACL: list(expectations.table_acl),
        CatalogQueryId.COLUMN_ACL: list(expectations.column_acl),
        CatalogQueryId.FUNCTIONS: list(expectations.functions),
        CatalogQueryId.FUNCTION_ACL: list(expectations.function_acl),
        CatalogQueryId.MEMBERSHIPS: [],
        CatalogQueryId.DANGEROUS_LOGIN_ROLES: [
            (owner_oid, "pitchlog_owner"),
            (privileged_role_oid, "external_superuser"),
        ],
        CatalogQueryId.UNAUTHORIZED_LOGIN_BYPASSRLS: [],
    }


def _install_catalog_rows(
    monkeypatch: pytest.MonkeyPatch,
    rows_by_query: dict[CatalogQueryId, list[tuple[object, ...]]],
) -> list[CatalogQueryId]:
    """公開経路が使う末端を問い合わせ ID ごとの観測値へ差し替える。"""
    calls: list[CatalogQueryId] = []

    def fetch(
        connection: psycopg.Connection[Any],
        query_id: CatalogQueryId,
        params: tuple[object, ...],
    ) -> list[tuple[object, ...]]:
        del connection, params
        calls.append(query_id)
        return rows_by_query[query_id]

    monkeypatch.setattr(product_catalog, "_fetch_catalog_rows", fetch)
    return calls


def test_product_expectations_cover_every_catalog_surface() -> None:
    """Staged 資産と適用手順から全件数と 7 手順を導出する。"""
    expectations = product_catalog._load_product_expectations()

    assert len(expectations.roles) == 4
    assert len(expectations.tables) == 45
    assert len(expectations.policies) == 32
    assert len(expectations.functions) == 38
    assert len(expectations.trigger_function_keys) == 37
    assert {key[2] for key in expectations.trigger_function_keys} == {""}
    assert {
        row[2]
        for row in expectations.functions
        if row[0:2] == ("authz_private", "tenant_has_effective_membership")
    } == {"uuid, boolean"}
    assert len(expectations.column_acl) == 8
    assert expectations.database_acl == (("pitchlog_app", "CONNECT", False),)
    assert tuple(
        step.sequence for step in expectations.application_steps.application_steps
    ) == tuple(range(1, 8))
    assert expectations.application_steps.transaction == "single"


def test_fetch_terminal_has_registered_signature_and_one_exact_reference() -> None:
    """DB 末端は登録シグネチャを持ち、公開検査から 1 回だけ参照される。"""
    _validate_terminal_boundary(_SOURCE_ROOT)


@pytest.mark.parametrize(
    "extra_reference",
    [
        pytest.param("_fetch_catalog_rows", id="name"),
        pytest.param("product_catalog._fetch_catalog_rows", id="attribute"),
    ],
)
def test_adding_a_fetch_terminal_reference_is_red(
    extra_reference: str,
    tmp_path: Path,
) -> None:
    """DB 末端の名前・属性参照を 1 つ足す変異を拒否する。"""
    source = _SOURCE_PATH.read_text(encoding="utf-8")
    mutated = f"{source}\n_EXTRA_FETCHER = {extra_reference}\n"
    target = tmp_path / "pitchlog/authz/product_catalog.py"
    target.parent.mkdir(parents=True)
    target.write_text(mutated, encoding="utf-8")
    with pytest.raises(AssertionError, match="直接呼び出し"):
        _validate_terminal_boundary(tmp_path)


def test_calling_fetch_terminal_through_an_alias_is_red(tmp_path: Path) -> None:
    """公開検査が DB 末端を別名へ代入して呼ぶ変異を拒否する。"""
    source = _SOURCE_PATH.read_text(encoding="utf-8")
    mutated = source.replace(
        "            rows = _fetch_catalog_rows(\n",
        "            fetcher = _fetch_catalog_rows\n            rows = fetcher(\n",
        1,
    )
    target = tmp_path / "pitchlog/authz/product_catalog.py"
    target.parent.mkdir(parents=True)
    target.write_text(mutated, encoding="utf-8")
    with pytest.raises(AssertionError, match="直接呼び出し"):
        _validate_terminal_boundary(tmp_path)


@pytest.mark.parametrize(
    "rogue_source",
    [
        pytest.param(
            "from pitchlog.authz.product_catalog import "
            "_fetch_catalog_rows as fetch\n\n"
            "def rogue(connection, query_id, params):\n"
            "    fetch(connection, query_id, params)\n",
            id="from-import-alias",
        ),
        pytest.param(
            "import pitchlog.authz.product_catalog as catalog\n\n"
            "def rogue(connection, query_id, params):\n"
            "    catalog._fetch_catalog_rows(connection, query_id, params)\n",
            id="module-attribute",
        ),
    ],
)
def test_fetch_reference_from_another_backend_module_is_red(
    rogue_source: str,
    tmp_path: Path,
) -> None:
    """別モジュールから通常に import した末端参照も exact-set 違反になる。"""
    target = tmp_path / "pitchlog/authz/product_catalog.py"
    target.parent.mkdir(parents=True)
    target.write_text(_SOURCE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    rogue = tmp_path / "pitchlog/rogue.py"
    rogue.write_text(rogue_source, encoding="utf-8")

    with pytest.raises(AssertionError, match="exact-set"):
        _validate_terminal_boundary(tmp_path)


def test_relative_fetch_import_from_another_module_is_red(
    tmp_path: Path,
) -> None:
    """相対 import で持ち込んだ DB 末端の呼び出しも拒否する。"""
    target = tmp_path / "pitchlog/authz/product_catalog.py"
    target.parent.mkdir(parents=True)
    target.write_text(_SOURCE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    rogue = tmp_path / "pitchlog/authz/relative_reader.py"
    rogue.write_text(
        "from .product_catalog import _fetch_catalog_rows as fetch\n\n"
        "def rogue(connection, query_id, params):\n"
        "    fetch(connection, query_id, params)\n",
        encoding="utf-8",
    )

    with pytest.raises(AssertionError, match="exact-set"):
        _validate_terminal_boundary(tmp_path)


def test_named_fetch_reexport_from_another_module_is_red(
    tmp_path: Path,
) -> None:
    """名前付き from import の再 export を介した DB 末端呼び出しも拒否する。"""
    target = tmp_path / "pitchlog/authz/product_catalog.py"
    target.parent.mkdir(parents=True)
    target.write_text(_SOURCE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    bridge = tmp_path / "pitchlog/authz/catalog_bridge.py"
    bridge.write_text(
        "from pitchlog.authz.product_catalog import "
        "_fetch_catalog_rows as exported_fetch\n",
        encoding="utf-8",
    )
    rogue = tmp_path / "pitchlog/rogue.py"
    rogue.write_text(
        "from pitchlog.authz.catalog_bridge import exported_fetch as fetch\n\n"
        "def rogue(connection, query_id, params):\n"
        "    fetch(connection, query_id, params)\n",
        encoding="utf-8",
    )

    with pytest.raises(AssertionError, match="exact-set"):
        _validate_terminal_boundary(tmp_path)


def test_every_closed_query_id_selects_module_sql_and_bound_params() -> None:
    """全問い合わせ ID が固定 SQL を選び、文字列を受け取らない。"""
    executed_queries: set[object] = set()
    for query_id in CatalogQueryId:
        connection = _FakeConnection(rows=[("row",)])
        params: tuple[object, ...] = (query_id.value,)

        result = product_catalog._fetch_catalog_rows(
            _as_psycopg_connection(connection),
            query_id,
            params,
        )

        assert result == [("row",)]
        assert connection.cursor_count == 1
        assert len(connection.executions) == 1
        query, actual_params = connection.executions[0]
        assert isinstance(query, str)
        assert actual_params == params
        executed_queries.add(query)
    assert len(executed_queries) == len(CatalogQueryId)


def test_policy_query_fixes_and_restores_search_path_in_one_statement() -> None:
    """ポリシー逆解析だけを完全修飾にし、元の search_path へ戻す。"""
    query = product_catalog._query_for_id(CatalogQueryId.POLICIES)

    assert "original_search_path AS MATERIALIZED" in query
    assert "catalog_search_path AS MATERIALIZED" in query
    assert "observed_policies AS MATERIALIZED" in query
    assert "restored_search_path AS MATERIALIZED" in query
    assert query.count("pg_catalog.set_config(") == 2
    assert "'search_path', 'pg_catalog', true" in query
    assert "completed_observation.observed_count >= 0" in query
    assert "restored_search_path.value IS NOT NULL" in query


def test_function_queries_compare_argument_types_without_argument_names() -> None:
    """関数本体と ACL の識別には proargtypes の型名だけを使う。"""
    functions_query = product_catalog._query_for_id(CatalogQueryId.FUNCTIONS)
    function_acl_query = product_catalog._query_for_id(CatalogQueryId.FUNCTION_ACL)

    assert functions_query.count("pg_catalog.oidvectortypes(routine.proargtypes)") == 2
    assert (
        function_acl_query.count("pg_catalog.oidvectortypes(routine.proargtypes)") == 1
    )
    assert "pg_get_function_identity_arguments" not in functions_query
    assert "pg_get_function_identity_arguments" not in function_acl_query


@pytest.mark.parametrize(
    ("query_id", "acl_column", "object_kind", "owner_column"),
    [
        pytest.param(
            CatalogQueryId.DATABASE_ACL,
            "database.datacl",
            "d",
            "database.datdba",
            id="database",
        ),
        pytest.param(
            CatalogQueryId.SCHEMA_ACL,
            "namespace.nspacl",
            "n",
            "namespace.nspowner",
            id="schema",
        ),
        pytest.param(
            CatalogQueryId.TABLE_ACL,
            "relation.relacl",
            "r",
            "relation.relowner",
            id="table",
        ),
        pytest.param(
            CatalogQueryId.FUNCTION_ACL,
            "routine.proacl",
            "f",
            "routine.proowner",
            id="function",
        ),
    ],
)
def test_null_object_acl_is_expanded_from_postgresql_defaults(
    query_id: CatalogQueryId,
    acl_column: str,
    object_kind: str,
    owner_column: str,
) -> None:
    """NULL の object ACL は owner 別の PostgreSQL 既定値として観測する。"""
    query = " ".join(product_catalog._query_for_id(query_id).split())

    assert (
        "pg_catalog.aclexplode( COALESCE( "
        f"{acl_column}, pg_catalog.acldefault('{object_kind}', {owner_column}) ) )"
        in query
    )


def test_null_column_acl_remains_no_column_level_grant() -> None:
    """列 ACL の NULL は既定値を展開せず、列単位付与なしとして観測する。"""
    query = product_catalog._query_for_id(CatalogQueryId.COLUMN_ACL)

    assert "pg_catalog.aclexplode(attribute.attacl)" in query
    assert "acldefault" not in query


class _UnknownQueryId(Enum):
    """閉じた列挙外の問い合わせ ID を表す試験用の型。"""

    UNKNOWN = "roles"


@pytest.mark.parametrize(
    "unknown_query_id",
    [
        pytest.param("SELECT * FROM pg_authid", id="sql-string"),
        pytest.param(_UnknownQueryId.UNKNOWN, id="foreign-enum"),
    ],
)
def test_unknown_or_string_query_id_is_red_without_a_db_call(
    unknown_query_id: object,
) -> None:
    """文字列 SQL と列挙外 ID は cursor を開く前に拒否する。"""
    connection = _FakeConnection()
    with pytest.raises(ProductCatalogError, match="未知"):
        product_catalog._fetch_catalog_rows(
            _as_psycopg_connection(connection),
            cast(CatalogQueryId, unknown_query_id),
            (),
        )
    assert connection.cursor_count == 0
    assert connection.executions == []


def test_public_inspection_is_green_for_asset_exact_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """定常状態の全問い合わせが資産期待値と一致すると green になる。"""
    privileged_role_oid = 900
    rows_by_query = _raw_catalog_rows(privileged_role_oid)
    calls = _install_catalog_rows(monkeypatch, rows_by_query)

    report = inspect_product_authz_catalog(
        cast(psycopg.Connection[Any], object()),
        privileged_role_oids=frozenset({privileged_role_oid}),
    )

    assert report.ok
    assert report.violations == ()
    assert calls == [
        CatalogQueryId.ROLES,
        CatalogQueryId.DATABASE,
        CatalogQueryId.DATABASE_ACL,
        CatalogQueryId.SCHEMAS,
        CatalogQueryId.SCHEMA_ACL,
        CatalogQueryId.TABLES,
        CatalogQueryId.POLICIES,
        CatalogQueryId.TABLE_ACL,
        CatalogQueryId.COLUMN_ACL,
        CatalogQueryId.FUNCTIONS,
        CatalogQueryId.FUNCTION_ACL,
        CatalogQueryId.MEMBERSHIPS,
        CatalogQueryId.DANGEROUS_LOGIN_ROLES,
        CatalogQueryId.UNAUTHORIZED_LOGIN_BYPASSRLS,
    ]
    assert len(report.checked_ids) == 15


def test_unqualified_public_relation_in_policy_is_red(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """期待側の public 修飾を消さず、未修飾の逆解析結果を拒否する。"""
    privileged_role_oid = 900
    rows_by_query = _raw_catalog_rows(privileged_role_oid)
    policy_rows = rows_by_query[CatalogQueryId.POLICIES]
    for index, row in enumerate(policy_rows):
        if row[1] != "sharing_grants":
            continue
        using_expression = str(row[6])
        assert "public.group_memberships" in using_expression
        policy_rows[index] = (
            *row[:6],
            using_expression.replace("public.group_memberships", "group_memberships"),
            row[7],
        )
        break
    else:  # pragma: no cover - 正規資産の内部不整合を明示する。
        raise AssertionError("sharing_grants のポリシーがない")
    _install_catalog_rows(monkeypatch, rows_by_query)

    report = inspect_product_authz_catalog(
        cast(psycopg.Connection[Any], object()),
        privileged_role_oids=frozenset({privileged_role_oid}),
    )

    assert not report.ok
    assert "PRODUCT-CATALOG:POLICIES" in {
        violation.check_id for violation in report.violations
    }


@pytest.mark.parametrize(
    ("mutation", "expected_check_id"),
    [
        pytest.param(
            lambda rows: rows[CatalogQueryId.MEMBERSHIPS].append(
                (
                    "pitchlog_shared_fn_owner",
                    "catalog_intruder",
                    "external_superuser",
                    True,
                    False,
                    False,
                )
            ),
            "PRODUCT-CATALOG:MEMBERSHIPS",
            id="admin-only-edge",
        ),
        pytest.param(
            lambda rows: rows[CatalogQueryId.MEMBERSHIPS].append(
                (
                    "catalog_parent",
                    "pitchlog_app",
                    "external_superuser",
                    False,
                    False,
                    False,
                )
            ),
            "PRODUCT-CATALOG:MEMBERSHIPS",
            id="edge-from-product-role",
        ),
        pytest.param(
            lambda rows: rows[CatalogQueryId.DANGEROUS_LOGIN_ROLES].append(
                (901, "unauthorized_login_bypassrls")
            ),
            "PRODUCT-CATALOG:DANGEROUS-LOGIN-ROLES",
            id="unknown-login-bypassrls",
        ),
        pytest.param(
            lambda rows: rows[CatalogQueryId.DANGEROUS_LOGIN_ROLES].append(
                (902, "unlisted_superuser")
            ),
            "PRODUCT-CATALOG:DANGEROUS-LOGIN-ROLES",
            id="unlisted-superuser",
        ),
        pytest.param(
            lambda rows: rows[CatalogQueryId.UNAUTHORIZED_LOGIN_BYPASSRLS].append(
                (903, "leftover_migration_role")
            ),
            "PRODUCT-CATALOG:UNAUTHORIZED-LOGIN-BYPASSRLS",
            id="leftover-login-bypassrls",
        ),
    ],
)
def test_security_mutations_are_red_through_public_inspection(
    mutation: Any,
    expected_check_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """辺と危険ロールの変異を公開検査の exact-set が拒否する。"""
    privileged_role_oid = 900
    rows_by_query = _raw_catalog_rows(privileged_role_oid)
    mutation(rows_by_query)
    _install_catalog_rows(monkeypatch, rows_by_query)

    report = inspect_product_authz_catalog(
        cast(psycopg.Connection[Any], object()),
        privileged_role_oids=frozenset({privileged_role_oid}),
    )

    assert not report.ok
    assert expected_check_id in {violation.check_id for violation in report.violations}


def test_security_definer_trigger_is_red_through_public_inspection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Migration trigger を SECURITY DEFINER にする変異を公開検査が拒否する。"""
    privileged_role_oid = 900
    rows_by_query = _raw_catalog_rows(privileged_role_oid)
    expectations = product_catalog._load_product_expectations()
    trigger_key = expectations.trigger_function_keys[0]
    function_rows = rows_by_query[CatalogQueryId.FUNCTIONS]
    for index, row in enumerate(function_rows):
        if tuple(str(value) for value in row[:3]) == trigger_key:
            function_rows[index] = (*row[:4], True)
            break
    else:  # pragma: no cover - 正規資産の内部不整合を明示する。
        raise AssertionError("migration trigger の観測行がない")
    _install_catalog_rows(monkeypatch, rows_by_query)

    report = inspect_product_authz_catalog(
        cast(psycopg.Connection[Any], object()),
        privileged_role_oids=frozenset({privileged_role_oid}),
    )

    assert not report.ok
    assert "PRODUCT-CATALOG:TRIGGER-SECURITY-INVOKER" in {
        violation.check_id for violation in report.violations
    }


def test_default_public_execute_on_trigger_function_is_red(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """NULL ACL から展開された trigger 関数の PUBLIC EXECUTE を拒否する。"""
    privileged_role_oid = 900
    rows_by_query = _raw_catalog_rows(privileged_role_oid)
    expectations = product_catalog._load_product_expectations()
    trigger_key = expectations.trigger_function_keys[0]
    rows_by_query[CatalogQueryId.FUNCTION_ACL].append(
        (*trigger_key, "PUBLIC", "EXECUTE", False)
    )
    _install_catalog_rows(monkeypatch, rows_by_query)

    report = inspect_product_authz_catalog(
        cast(psycopg.Connection[Any], object()),
        privileged_role_oids=frozenset({privileged_role_oid}),
    )

    assert not report.ok
    assert "PRODUCT-CATALOG:FUNCTION-ACL" in {
        violation.check_id for violation in report.violations
    }


@pytest.mark.parametrize(
    "privileged_role_oids",
    [
        pytest.param(frozenset(), id="empty"),
        pytest.param(cast(frozenset[int], (900,)), id="not-frozenset"),
        pytest.param(frozenset({True}), id="bool"),
        pytest.param(frozenset({0}), id="not-positive"),
    ],
)
def test_invalid_privileged_role_oids_are_red_before_catalog_access(
    privileged_role_oids: frozenset[int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """環境の特権ロール入力は正の OID の非空集合だけを許可する。"""
    called = False

    def fail_if_called(
        connection: psycopg.Connection[Any],
        query_id: CatalogQueryId,
        params: tuple[object, ...],
    ) -> list[tuple[object, ...]]:
        del connection, query_id, params
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(product_catalog, "_fetch_catalog_rows", fail_if_called)
    with pytest.raises(ProductCatalogError, match="privileged_role_oids"):
        inspect_product_authz_catalog(
            cast(psycopg.Connection[Any], object()),
            privileged_role_oids=privileged_role_oids,
        )
    assert not called
