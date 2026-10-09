"""製品カタログ検査の閉じた問い合わせ境界と exact-set を検査する。

対象モジュール外では公開名 exact-set の名前付き from import だけを許し、対象モジュール
名の属性参照と module・star・集合外 import を拒否する。内部では末端参照 exact-set と
単一リテラルの __all__ を構造で検査し、値の流れは追わない。
"""

from __future__ import annotations

import ast
import copy
import json
from collections.abc import Iterator
from enum import Enum
from pathlib import Path
from typing import Any, cast

import psycopg
import pytest
from db.test_product_authz_normalize_function import _normalizer_body_is_safe

from pitchlog.authz import product_catalog
from pitchlog.authz.asset_spec import PRODUCT_SPEC, validate_product_application_steps
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
_TARGET_MODULE_ATTRIBUTE = "product_catalog"
_PUBLIC_IMPORT_NAMES = frozenset(
    {
        "CatalogQueryId",
        "ProductCatalogReport",
        "ProductCatalogViolation",
        "inspect_migration_batch_role_catalog",
        "inspect_product_authz_catalog",
    }
)
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


def _assert_external_import_shape(
    module_name: str,
    path: Path,
    tree: ast.Module,
) -> None:
    """対象外モジュールでは公開 exact-set の名前付き import だけを許可する。"""
    if module_name == _TERMINAL_MODULE:
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == _TARGET_MODULE_ATTRIBUTE:
            raise AssertionError("製品カタログ名の属性参照は禁止")
        if isinstance(node, ast.Import):
            if any(
                alias.name == _TERMINAL_MODULE
                or alias.name.startswith(f"{_TERMINAL_MODULE}.")
                for alias in node.names
            ):
                raise AssertionError("製品カタログモジュール自体の import は禁止")
            continue
        if not isinstance(node, ast.ImportFrom):
            continue
        imported_from = _absolute_import_from(module_name, path, node)
        if imported_from is None:
            continue
        if imported_from == _TERMINAL_MODULE:
            if any(alias.name == "*" for alias in node.names):
                raise AssertionError("製品カタログモジュールの import * は禁止")
            unexpected_names = {
                alias.name
                for alias in node.names
                if alias.name not in _PUBLIC_IMPORT_NAMES
            }
            if unexpected_names:
                raise AssertionError(
                    "製品カタログモジュールの公開名 exact-set 外の import は禁止: "
                    f"{sorted(unexpected_names)}"
                )
            continue
        if any(
            f"{imported_from}.{alias.name}" == _TERMINAL_MODULE for alias in node.names
        ):
            raise AssertionError("製品カタログモジュール自体の from import は禁止")


def _assert_public_import_names_exist(tree: ast.Module) -> None:
    """許可した公開名が対象モジュールの最上位にすべて存在することを検査する。"""
    defined_names = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef))
    }
    if not _PUBLIC_IMPORT_NAMES <= defined_names:
        raise AssertionError("製品カタログの公開名 exact-set に存在しない名前がある")


def _assert_literal_module_all(tree: ast.Module) -> None:
    """__all__ を最上位の単一文字列リテラル代入だけに限定する。"""
    all_uses = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and node.id == "__all__"
    ]
    if not all_uses:
        return
    writes = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.NamedExpr))
        and any(
            isinstance(target_node, ast.Name) and target_node.id == "__all__"
            for target in (
                node.targets if isinstance(node, ast.Assign) else (node.target,)
            )
            for target_node in ast.walk(target)
        )
    ]
    mutations = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "__all__"
    ]
    if (
        len(writes) != 1
        or writes[0] not in tree.body
        or not isinstance(writes[0], ast.Assign)
        or len(writes[0].targets) != 1
        or not isinstance(writes[0].targets[0], ast.Name)
        or mutations
    ):
        raise AssertionError("製品カタログの __all__ は最上位の単一代入が必要")
    value = writes[0].value
    if not isinstance(value, (ast.List, ast.Tuple)) or not all(
        isinstance(element, ast.Constant) and isinstance(element.value, str)
        for element in value.elts
    ):
        raise AssertionError("製品カタログの __all__ は文字列リテラルだけが必要")
    exported_names = tuple(cast(ast.Constant, element).value for element in value.elts)
    if _TERMINAL_NAME in exported_names:
        raise AssertionError("製品カタログの末端を __all__ へ公開できない")


def _internal_terminal_references(
    tree: ast.Module,
) -> tuple[tuple[ast.expr, str], ...]:
    """対象モジュール内部にある末端名・属性の参照を全数返す。"""
    ancestors = _function_ancestors(tree)
    return tuple(
        (node, ancestors[node])
        for node in ast.walk(tree)
        if (
            isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Load)
            and node.id == _TERMINAL_NAME
        )
        or (
            isinstance(node, ast.Attribute)
            and isinstance(node.ctx, ast.Load)
            and node.attr == _TERMINAL_NAME
        )
    )


def _validate_terminal_boundary(source_root: Path) -> None:
    """全 backend/src で末端のシグネチャ・参照集合を検査する。"""
    modules = _source_modules(source_root)
    if _TERMINAL_MODULE not in modules:
        raise AssertionError("製品カタログモジュールが存在しない")
    trees = {
        module_name: ast.parse(source, filename=str(path))
        for module_name, (path, source) in modules.items()
    }
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

    for observed_module, module_tree in trees.items():
        _assert_external_import_shape(
            observed_module,
            modules[observed_module][0],
            module_tree,
        )
    _assert_public_import_names_exist(tree)
    _assert_literal_module_all(tree)

    parents = {
        child: parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }
    references: list[str] = []
    for node, function_name in _internal_terminal_references(tree):
        parent = parents.get(node)
        if not isinstance(parent, ast.Call) or parent.func is not node:
            raise AssertionError("製品カタログの DB 末端が直接呼び出し以外で参照された")
        references.append(function_name)
    if references != ["inspect_product_authz_catalog"]:
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
        CatalogQueryId.EXTENSIONS: list(expectations.extensions),
        CatalogQueryId.PGCRYPTO_MEMBER_ACL: [
            (
                200,
                "authn_crypto",
                "crypt",
                "text, text",
                "pitchlog_auth_fn_owner",
                "EXECUTE",
                False,
            )
        ],
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
    """製品資産と適用手順から全カタログ期待値を導出する。"""
    expectations = product_catalog._load_product_expectations()
    asset = product_catalog._load_product_asset()
    asset_roles = cast(list[dict[str, Any]], asset["roles"])
    asset_functions = cast(list[dict[str, Any]], asset["functions"])
    asset_table_acls = cast(list[dict[str, Any]], asset["acl_expectations"])
    asset_column_acls = cast(list[dict[str, Any]], asset["column_acl_expectations"])

    assert len(expectations.roles) == len(asset_roles)
    assert expectations.roles == expectations.semantic_roles
    assert len(expectations.tables) == 45
    assert len(expectations.policies) == 32
    assert len(expectations.functions) == len(asset_functions)
    assert len(expectations.trigger_function_keys) == sum(
        row["function_kind"] == "migration_trigger" for row in asset_functions
    )
    assert {key[2] for key in expectations.trigger_function_keys} == {""}
    assert {
        row[2]
        for row in expectations.functions
        if row[0:2] == ("authz_private", "tenant_has_effective_membership")
    } == {"uuid, boolean"}
    assert len(expectations.column_acl) == sum(
        len(row["privilege_ids"]) for row in asset_column_acls
    )
    assert len(expectations.table_acl) == sum(
        len(row["privilege_ids"]) for row in asset_table_acls
    )
    assert expectations.database_acl == (("pitchlog_app", "CONNECT", False),)
    assert tuple(
        step.sequence for step in expectations.application_steps.application_steps
    ) == tuple(range(1, len(expectations.application_steps.application_steps) + 1))
    assert expectations.application_steps.transaction == "single"


def test_definer_function_is_derived_from_test_asset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """definer関数のスキーマ・所有者・実行ACLを資産から導く。"""
    asset = copy.deepcopy(product_catalog._load_product_asset())
    rows = asset["functions"]
    assert isinstance(rows, list)
    definer = copy.deepcopy(
        next(row for row in rows if row["function_kind"] == "rls_helper")
    )
    definer.update(
        function_id="FUNCTION:authz_private:step3_definer(uuid, boolean)",
        function_name="step3_definer",
        function_kind="definer",
        acl_expectations=[
            {"grantee": "pitchlog_app", "privilege": "EXECUTE", "grantable": False}
        ],
    )
    rows.append(definer)
    assert PRODUCT_SPEC.application_steps_path is not None
    steps_asset = json.loads(
        (_REPOSITORY_ROOT / PRODUCT_SPEC.application_steps_path).read_text(
            encoding="utf-8"
        )
    )
    steps = validate_product_application_steps(steps_asset, asset, PRODUCT_SPEC)
    monkeypatch.setattr(product_catalog, "_load_product_asset", lambda: asset)
    monkeypatch.setattr(
        product_catalog, "load_product_application_steps", lambda root, spec: steps
    )

    expectations = product_catalog._load_product_expectations()
    assert (
        "authz_private",
        "step3_definer",
        "uuid, boolean",
        "pitchlog_shared_fn_owner",
        True,
    ) in expectations.functions
    assert (
        "authz_private",
        "step3_definer",
        "uuid, boolean",
        "pitchlog_app",
        "EXECUTE",
        False,
    ) in expectations.function_acl


def test_migration_regular_function_is_not_a_trigger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """通常関数は関数 ACL に含め、トリガ関数の集合から除く。"""
    asset = copy.deepcopy(product_catalog._load_product_asset())
    rows = cast(list[dict[str, Any]], asset["functions"])
    ordinary = copy.deepcopy(
        next(row for row in rows if row["function_kind"] == "migration_trigger")
    )
    ordinary.update(
        function_id="FUNCTION:public:step4_ordinary()",
        function_name="step4_ordinary",
        function_kind="migration_function",
    )
    rows.append(ordinary)
    assert PRODUCT_SPEC.application_steps_path is not None
    steps_asset = json.loads(
        (_REPOSITORY_ROOT / PRODUCT_SPEC.application_steps_path).read_text(
            encoding="utf-8"
        )
    )
    groups = steps_asset["application_steps"][-1]["element_groups"]
    if "functions:migration_function" not in groups:
        groups.append("functions:migration_function")
    steps = validate_product_application_steps(steps_asset, asset, PRODUCT_SPEC)
    monkeypatch.setattr(product_catalog, "_load_product_asset", lambda: asset)
    monkeypatch.setattr(
        product_catalog, "load_product_application_steps", lambda root, spec: steps
    )
    expectations = product_catalog._load_product_expectations()
    key = ("public", "step4_ordinary", "")
    assert (*key, "pitchlog_owner", False) in expectations.functions
    assert key not in expectations.trigger_function_keys
    assert len(expectations.trigger_function_keys) == sum(
        row["function_kind"] == "migration_trigger" for row in rows
    )


def test_fetch_terminal_has_registered_signature_and_one_exact_reference() -> None:
    """DB 末端は登録シグネチャを持ち、公開検査から 1 回だけ参照される。"""
    _validate_terminal_boundary(_SOURCE_ROOT)


def test_normalizer_body_allowlist_rejects_extra_calls() -> None:
    """追加の完全修飾・非修飾呼出しを字句全体の許可式が拒否する。"""
    # 詳細設計 10-1 節 ⑦ の 25 文字を、migration に依存せず指定する。
    white_space = (
        r"\0009\000A\000B\000C\000D\0020\0085\00A0"
        r"\1680\2000\2001\2002\2003\2004\2005\2006"
        r"\2007\2008\2009\200A\2028\2029\202F\205F\3000"
    )
    body = rf"""SELECT pg_catalog.lower(
        pg_catalog.btrim(pg_catalog."normalize"($1, 'NFKC'), U&'{white_space}')
        COLLATE pg_catalog.pg_c_utf8
    )"""
    assert _normalizer_body_is_safe(body)
    assert not _normalizer_body_is_safe(body + " || public.unapproved_helper($1)")
    assert not _normalizer_body_is_safe(body + " || upper($1)")


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
            "import pitchlog.authz.product_catalog\n",
            id="absolute-module-import",
        ),
        pytest.param(
            "from pitchlog.authz import product_catalog\n",
            id="from-parent-module-import",
        ),
        pytest.param(
            "from . import product_catalog\n",
            id="relative-module-import",
        ),
        pytest.param(
            "from pitchlog.authz.product_catalog import *\n",
            id="star-import",
        ),
        pytest.param(
            "from pitchlog.authz.product_catalog import _fetch_catalog_rows\n",
            id="terminal-import",
        ),
        pytest.param(
            "from pitchlog.authz.product_catalog import _CatalogRequest\n",
            id="other-private-import",
        ),
        pytest.param(
            "from pitchlog.authz.product_catalog import PRODUCT_SPEC\n",
            id="asset-spec-import",
        ),
        pytest.param(
            "from pitchlog.authz.product_catalog import "
            "load_product_application_steps\n",
            id="asset-loader-import",
        ),
        pytest.param(
            "from pitchlog.authz.product_catalog import ProductApplicationSteps\n",
            id="asset-type-import",
        ),
    ],
)
def test_external_import_shapes_outside_the_closed_rule_are_red(
    rogue_source: str,
    tmp_path: Path,
) -> None:
    """外部では公開名の名前付き from import 以外をすべて拒否する。"""
    target = tmp_path / "pitchlog/authz/product_catalog.py"
    target.parent.mkdir(parents=True)
    target.write_text(_SOURCE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    rogue = tmp_path / "pitchlog/authz/rogue.py"
    rogue.write_text(rogue_source, encoding="utf-8")

    with pytest.raises(AssertionError, match="import"):
        _validate_terminal_boundary(tmp_path)


@pytest.mark.parametrize("public_name", sorted(_PUBLIC_IMPORT_NAMES))
def test_public_named_import_from_another_module_is_green(
    public_name: str,
    tmp_path: Path,
) -> None:
    """外部から公開 exact-set の部分集合を名前付き import する形は許可する。"""
    target = tmp_path / "pitchlog/authz/product_catalog.py"
    target.parent.mkdir(parents=True)
    target.write_text(_SOURCE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    consumer = tmp_path / "pitchlog/consumer.py"
    consumer.write_text(
        f"from pitchlog.authz.product_catalog import {public_name} as public_api\n",
        encoding="utf-8",
    )

    _validate_terminal_boundary(tmp_path)


@pytest.mark.parametrize(
    "rogue_source",
    [
        pytest.param(
            "import pitchlog.authz\n_MODULE = pitchlog.authz.product_catalog\n",
            id="absolute-parent-attribute",
        ),
        pytest.param(
            "import pitchlog\n_MODULE = pitchlog.authz.product_catalog\n",
            id="absolute-root-attribute",
        ),
        pytest.param(
            "from .. import authz\n_MODULE = authz.product_catalog\n",
            id="relative-parent-attribute",
        ),
    ],
)
def test_target_module_name_attribute_reference_is_red(
    rogue_source: str,
    tmp_path: Path,
) -> None:
    """対象モジュール名と同じ属性の参照を由来によらず拒否する。"""
    target = tmp_path / "pitchlog/authz/product_catalog.py"
    target.parent.mkdir(parents=True)
    target.write_text(_SOURCE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    rogue = tmp_path / "pitchlog/authz/rogue.py"
    rogue.write_text(rogue_source, encoding="utf-8")

    with pytest.raises(AssertionError, match="属性参照"):
        _validate_terminal_boundary(tmp_path)


@pytest.mark.parametrize(
    "all_source",
    [
        pytest.param(
            '__all__ = ("_fetch_catalog_rows",)\n',
            id="terminal-literal",
        ),
        pytest.param(
            '_EXPORTED = ("_fetch_catalog_rows",)\n__all__ = _EXPORTED\n',
            id="name-indirection",
        ),
        pytest.param(
            '__all__ = ("_fetch_" + "catalog_rows",)\n',
            id="string-concatenation",
        ),
        pytest.param(
            '__all__ = ("inspect_product_authz_catalog",)\n'
            '__all__ += ("_fetch_catalog_rows",)\n',
            id="augmented-assignment",
        ),
        pytest.param(
            '__all__ = ["inspect_product_authz_catalog"]\n'
            '__all__.append("_fetch_catalog_rows")\n',
            id="append",
        ),
        pytest.param(
            '__all__ = ["inspect_product_authz_catalog"]\n'
            '__all__.extend(["_fetch_catalog_rows"])\n',
            id="extend",
        ),
    ],
)
def test_nonliteral_or_terminal_module_all_is_red(
    all_source: str,
    tmp_path: Path,
) -> None:
    """__all__ の間接構築・追記・末端公開を拒否する。"""
    source = _SOURCE_PATH.read_text(encoding="utf-8")
    mutated = f"{source}\n{all_source}"
    target = tmp_path / "pitchlog/authz/product_catalog.py"
    target.parent.mkdir(parents=True)
    target.write_text(mutated, encoding="utf-8")

    with pytest.raises(AssertionError, match="__all__"):
        _validate_terminal_boundary(tmp_path)


def test_literal_public_module_all_is_green(tmp_path: Path) -> None:
    """公開名だけの単一リテラル __all__ は許可する。"""
    source = _SOURCE_PATH.read_text(encoding="utf-8")
    exports = ", ".join(repr(name) for name in sorted(_PUBLIC_IMPORT_NAMES))
    target = tmp_path / "pitchlog/authz/product_catalog.py"
    target.parent.mkdir(parents=True)
    target.write_text(f"{source}\n__all__ = ({exports},)\n", encoding="utf-8")

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
        CatalogQueryId.EXTENSIONS,
        CatalogQueryId.PGCRYPTO_MEMBER_ACL,
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
    assert len(report.checked_ids) == 26


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


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("missing_function", "署名"),
        ("wrong_grantee", "付与先"),
        ("wrong_monitor_grantee", "付与先"),
        ("wrong_extension_schema", "拡張"),
        ("missing_table_grant", "表 ACL"),
    ],
)
def test_authn_asset_mutations_fail_independent_contract(
    mutation: str, message: str
) -> None:
    """認証資産の関数・権限・拡張を独立した意味集合へ照合する。"""
    from pitchlog.authz.product_authn_contract import validate_authn_asset

    asset = cast(dict[str, Any], copy.deepcopy(product_catalog._load_product_asset()))
    validate_authn_asset(asset)
    if mutation == "missing_function":
        asset["functions"] = [
            row for row in asset["functions"] if row["function_name"] != "login_attempt"
        ]
    elif mutation == "wrong_grantee":
        function = next(
            row for row in asset["functions"] if row["function_name"] == "login_attempt"
        )
        function["acl_expectations"][0]["grantee"] = "pitchlog_management_fn_owner"
    elif mutation == "wrong_monitor_grantee":
        function = next(
            row
            for row in asset["functions"]
            if row["function_name"] == "observe_rate_limit_counters"
        )
        function["acl_expectations"][0]["grantee"] = "pitchlog_app"
    elif mutation == "wrong_extension_schema":
        asset["extensions"][0]["schema_name"] = "public"
    else:
        asset["acl_expectations"] = [
            row
            for row in asset["acl_expectations"]
            if row["object_id"] != "rate_limit_counters"
            or row["grantee_role_id"] != "pitchlog_auth_fn_owner"
        ]
    with pytest.raises(ValueError, match=message):
        validate_authn_asset(asset)


def test_missing_role_is_rejected_before_dependent_authn_grants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ロールと依存する付与を消しても独立のロール集合で拒否する。"""
    role_name = "pitchlog_management_fn_owner"
    asset = cast(dict[str, Any], copy.deepcopy(product_catalog._load_product_asset()))
    asset["roles"] = [row for row in asset["roles"] if row["role_id"] != role_name]
    for section in ("schemas", "functions"):
        for row in asset[section]:
            for field in ("acl_expectations", "revoked_acl_expectations"):
                row[field] = [
                    grant for grant in row[field] if grant["grantee"] != role_name
                ]
    monkeypatch.setattr(product_catalog, "_load_product_asset", lambda: asset)
    with pytest.raises(ProductCatalogError, match="独立の意味契約"):
        product_catalog._load_product_expectations()


@pytest.mark.parametrize(
    ("mutation", "check_id"),
    [
        ("extra_member_public", "PRODUCT-CATALOG:PGCRYPTO-MEMBER-ACL-INDEPENDENT"),
        ("wrong_extension_schema", "PRODUCT-CATALOG:AUTHN-EXTENSION-INDEPENDENT"),
        ("missing_app_grant", "PRODUCT-CATALOG:AUTHN-GRANTS-INDEPENDENT"),
        (
            "missing_normalizer_grant",
            "PRODUCT-CATALOG:AUTHN-NORMALIZER-EXECUTE-INDEPENDENT",
        ),
    ],
)
def test_authn_catalog_mutations_fail_independent_checks(
    mutation: str, check_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """実カタログの認証権限変異を資産由来でない期待集合が拒否する。"""
    rows = _raw_catalog_rows(900)
    if mutation == "extra_member_public":
        rows[CatalogQueryId.PGCRYPTO_MEMBER_ACL].append(
            (200, "authn_crypto", "crypt", "text, text", "PUBLIC", "EXECUTE", False)
        )
    elif mutation == "wrong_extension_schema":
        rows[CatalogQueryId.EXTENSIONS][0] = ("pgcrypto", "public")
    elif mutation == "missing_app_grant":
        rows[CatalogQueryId.FUNCTION_ACL] = [
            row
            for row in rows[CatalogQueryId.FUNCTION_ACL]
            if row[:3] != ("authn", "login_attempt", "text, text, text")
        ]
    else:
        rows[CatalogQueryId.FUNCTION_ACL] = [
            row
            for row in rows[CatalogQueryId.FUNCTION_ACL]
            if row[:3] != ("public", "authn_normalize_team_name", "text")
            or row[3] != "pitchlog_auth_fn_owner"
        ]
    _install_catalog_rows(monkeypatch, rows)
    report = inspect_product_authz_catalog(
        cast(psycopg.Connection[Any], object()),
        privileged_role_oids=frozenset({900}),
    )
    assert check_id in {violation.check_id for violation in report.violations}


def test_authn_bcrypt_cost_is_twelve_in_all_hash_paths() -> None:
    """ダミーハッシュと実ハッシュ生成の bcrypt コストを同じ 12 に固定する。"""
    directory = _REPOSITORY_ROOT / "contracts/authz/product/function-bodies/functions"
    login = (
        directory / "FUNCTION:authn:login_attempt(text, text, text).sql"
    ).read_text(encoding="utf-8")
    assert "$2a$12$" in login
    for filename in (
        "FUNCTION:authn:change_password(uuid, text, text).sql",
        "FUNCTION:authn:issue_initial_password(uuid, text).sql",
        "FUNCTION:authn:reset_password(uuid, text).sql",
    ):
        body = (directory / filename).read_text(encoding="utf-8")
        assert "authn_crypto.gen_salt('bf', 12)" in body
