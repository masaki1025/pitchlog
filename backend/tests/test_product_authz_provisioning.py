"""製品認可 DDL の適用器が閉じた実行経路だけを持つことを検査する。

対象モジュール外では公開名 exact-set の名前付き from import だけを許し、対象モジュール
名の属性参照と module・star・集合外 import を拒否する。内部では末端参照 exact-set と
単一リテラルの __all__ を構造で検査し、値の流れは追わない。
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from pathlib import Path, PurePosixPath
from typing import Any, cast

import psycopg
import pytest
from psycopg import pq

from pitchlog.authz import product_provisioning
from pitchlog.authz.asset_spec import (
    PRODUCT_SPEC,
    ProductApplicationSteps,
    load_product_application_steps,
)
from pitchlog.authz.product_provisioning import (
    ProductOperation,
    ProductProvisioningError,
    apply_product_authz_ddl,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_SOURCE_ROOT = _REPOSITORY_ROOT / "backend/src"
_SOURCE_PATH = _REPOSITORY_ROOT / "backend/src/pitchlog/authz/product_provisioning.py"
_TERMINAL_MODULE = "pitchlog.authz.product_provisioning"
_TERMINAL_NAME = "_run_product_operation"
_TARGET_MODULE_ATTRIBUTE = "product_provisioning"
_PUBLIC_IMPORT_NAMES = frozenset(
    {
        "ProductOperation",
        "apply_product_authz_ddl",
        "unapply_product_authz_ddl",
    }
)
_EXPECTED_TERMINAL_SIGNATURE = (
    "_run_product_operation(connection: psycopg.Connection[Any], "
    "operation: ProductOperation) -> None"
)
_DB_METHOD_NAMES = {"cursor", "execute", "commit", "rollback"}


class _FakeInfo:
    """Psycopg 接続情報のうち適用器が読む状態だけを持つ。"""

    def __init__(
        self,
        connection: _FakeConnection,
        transaction_status: pq.TransactionStatus,
    ) -> None:
        self._connection = connection
        self.transaction_status = transaction_status

    def parameter_status(self, name: str) -> str | None:
        """サーバーが通知する接続主体の状態を試験値から返す。"""
        self._connection.parameter_status_calls.append(name)
        if name == "session_authorization":
            return self._connection.session_user
        if name == "is_superuser":
            return "on" if self._connection.is_superuser else "off"
        return None


class _FakeCursor:
    """識別問い合わせと生成 DDL を区別して記録する cursor。"""

    def __init__(self, connection: _FakeConnection) -> None:
        self._connection = connection
        self._rows: tuple[tuple[object, ...], ...] = ()

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
        return iter(self._rows)

    def execute(self, query: object) -> None:
        """識別問い合わせへ行を返し、それ以外を生成 DDL として記録する。"""
        self._connection.execute_calls.append(query)
        if query == product_provisioning._IDENTITY_QUERY:
            self._connection.identity_query_count += 1
            default_row = (
                self._connection.current_user,
                self._connection.session_user,
                self._connection.is_superuser,
            )
            self._rows = (
                self._connection.identity_overrides.get(
                    self._connection.identity_query_count,
                    default_row,
                ),
            )
            return
        self._rows = ()
        self._connection.executed_statements.append(query)


class _FakeConnection:
    """公開経路の前提・commit・rollback を観測する最小接続。"""

    def __init__(
        self,
        *,
        closed: bool = False,
        autocommit: bool = False,
        transaction_status: pq.TransactionStatus = pq.TransactionStatus.IDLE,
        current_user: str = "external_superuser",
        session_user: str = "external_superuser",
        is_superuser: bool = True,
    ) -> None:
        self.closed = closed
        self.autocommit = autocommit
        self.current_user = current_user
        self.session_user = session_user
        self.is_superuser = is_superuser
        self.info = _FakeInfo(self, transaction_status)
        self.execute_calls: list[object] = []
        self.executed_statements: list[object] = []
        self.parameter_status_calls: list[str] = []
        self.identity_query_count = 0
        self.identity_overrides: dict[int, tuple[object, ...]] = {}
        self.commit_count = 0
        self.rollback_count = 0

    def cursor(self) -> _FakeCursor:
        """試験用 cursor を返す。"""
        return _FakeCursor(self)

    def execute(self, query: object) -> _FakeCursor:
        """Connection.execute も cursor と同じ全数記録へ含める。"""
        cursor = self.cursor()
        cursor.execute(query)
        return cursor

    def commit(self) -> None:
        """Commit 呼び出し回数を記録する。"""
        self.commit_count += 1

    def rollback(self) -> None:
        """Rollback 呼び出し回数を記録する。"""
        self.rollback_count += 1


@pytest.fixture(scope="module")
def application_steps() -> ProductApplicationSteps:
    """正規の単一 transaction 手順を返す。"""
    return load_product_application_steps(_REPOSITORY_ROOT, PRODUCT_SPEC)


def _small_operation_plan(
    steps: ProductApplicationSteps,
) -> tuple[ProductApplicationSteps, tuple[product_provisioning._ProductStatement, ...]]:
    """公開経路の制御だけを観測する 7 手順の小さな計画を返す。"""
    statements = tuple(
        product_provisioning._ProductStatement(
            sequence=sequence,
            sql=f"SELECT {sequence}",
        )
        for sequence in range(1, 8)
    )
    return steps, statements


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


def _parse_source(source: str) -> ast.Module:
    """製品適用器ソースを AST として読む。"""
    return ast.parse(source, filename=str(_SOURCE_PATH))


def _as_psycopg_connection(
    connection: _FakeConnection,
) -> psycopg.Connection[Any]:
    """試験用接続を公開 API の型境界へ明示的に渡す。"""
    return cast(psycopg.Connection[Any], connection)


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
            raise AssertionError("製品適用器名の属性参照は禁止")
        if isinstance(node, ast.Import):
            if any(
                alias.name == _TERMINAL_MODULE
                or alias.name.startswith(f"{_TERMINAL_MODULE}.")
                for alias in node.names
            ):
                raise AssertionError("製品適用器モジュール自体の import は禁止")
            continue
        if not isinstance(node, ast.ImportFrom):
            continue
        imported_from = _absolute_import_from(module_name, path, node)
        if imported_from is None:
            continue
        if imported_from == _TERMINAL_MODULE:
            if any(alias.name == "*" for alias in node.names):
                raise AssertionError("製品適用器モジュールの import * は禁止")
            unexpected_names = {
                alias.name
                for alias in node.names
                if alias.name not in _PUBLIC_IMPORT_NAMES
            }
            if unexpected_names:
                raise AssertionError(
                    "製品適用器モジュールの公開名 exact-set 外の import は禁止: "
                    f"{sorted(unexpected_names)}"
                )
            continue
        if any(
            f"{imported_from}.{alias.name}" == _TERMINAL_MODULE for alias in node.names
        ):
            raise AssertionError("製品適用器モジュール自体の from import は禁止")


def _assert_public_import_names_exist(tree: ast.Module) -> None:
    """許可した公開名が対象モジュールの最上位にすべて存在することを検査する。"""
    defined_names = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef))
    }
    if not _PUBLIC_IMPORT_NAMES <= defined_names:
        raise AssertionError("製品適用器の公開名 exact-set に存在しない名前がある")


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
        raise AssertionError("製品適用器の __all__ は最上位の単一代入が必要")
    value = writes[0].value
    if not isinstance(value, (ast.List, ast.Tuple)) or not all(
        isinstance(element, ast.Constant) and isinstance(element.value, str)
        for element in value.elts
    ):
        raise AssertionError("製品適用器の __all__ は文字列リテラルだけが必要")
    exported_names = tuple(cast(ast.Constant, element).value for element in value.elts)
    if _TERMINAL_NAME in exported_names:
        raise AssertionError("製品適用器の末端を __all__ へ公開できない")


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
        raise AssertionError("製品適用器モジュールが存在しない")
    trees = {
        module_name: ast.parse(source, filename=str(path))
        for module_name, (path, source) in modules.items()
    }
    tree = trees[_TERMINAL_MODULE]
    terminals = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_run_product_operation"
    ]
    if len(terminals) != 1:
        raise AssertionError("製品適用器の末端関数が一意でない")
    terminal = terminals[0]
    if terminal.returns is None:
        raise AssertionError("製品適用器の末端に戻り値注釈がない")
    rendered_signature = (
        f"{terminal.name}({ast.unparse(terminal.args)}) -> "
        f"{ast.unparse(terminal.returns)}"
    )
    if rendered_signature != _EXPECTED_TERMINAL_SIGNATURE:
        raise AssertionError("製品適用器の末端シグネチャが登録値と一致しない")

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
            raise AssertionError("製品適用器の末端が直接呼び出し以外で参照された")
        references.append(function_name)
    if sorted(references) != [
        "apply_product_authz_ddl",
        "unapply_product_authz_ddl",
    ]:
        raise AssertionError("製品適用器の末端を参照する関数が exact-set でない")

    ancestors = _function_ancestors(tree)
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _DB_METHOD_NAMES
        ):
            continue
        if ancestors[node] != "_run_product_operation":
            raise AssertionError("DB 呼び出しが製品適用器の末端外にある")


def test_terminal_boundary_is_closed_and_has_exact_references() -> None:
    """末端は登録シグネチャを持ち、公開 2 関数だけから直接参照される。"""
    _validate_terminal_boundary(_SOURCE_ROOT)


def test_adding_statement_or_asset_path_argument_is_red(tmp_path: Path) -> None:
    """末端に文や資産の置き場を渡せる引数を足す変異を拒否する。"""
    source = _SOURCE_PATH.read_text(encoding="utf-8")
    mutated = source.replace(
        "    operation: ProductOperation,\n) -> None:",
        "    operation: ProductOperation,\n    asset_root: Path,\n) -> None:",
        1,
    )
    target = tmp_path / "pitchlog/authz/product_provisioning.py"
    target.parent.mkdir(parents=True)
    target.write_text(mutated, encoding="utf-8")
    with pytest.raises(AssertionError, match="シグネチャ"):
        _validate_terminal_boundary(tmp_path)


@pytest.mark.parametrize(
    "extra_reference",
    [
        pytest.param("_run_product_operation", id="name"),
        pytest.param(
            "product_provisioning._run_product_operation",
            id="attribute",
        ),
    ],
)
def test_adding_a_terminal_reference_is_red(
    extra_reference: str,
    tmp_path: Path,
) -> None:
    """同じモジュール内に末端の名前・属性参照を足す変異を拒否する。"""
    source = _SOURCE_PATH.read_text(encoding="utf-8")
    mutated = f"{source}\n_EXTRA_RUNNER = {extra_reference}\n"
    target = tmp_path / "pitchlog/authz/product_provisioning.py"
    target.parent.mkdir(parents=True)
    target.write_text(mutated, encoding="utf-8")
    with pytest.raises(AssertionError, match="直接呼び出し"):
        _validate_terminal_boundary(tmp_path)


def test_calling_terminal_through_an_alias_is_red(tmp_path: Path) -> None:
    """公開関数が末端を別名へ代入して呼ぶ変異を拒否する。"""
    source = _SOURCE_PATH.read_text(encoding="utf-8")
    mutated = source.replace(
        "    _run_product_operation(connection, ProductOperation.APPLY)",
        "    runner = _run_product_operation\n"
        "    runner(connection, ProductOperation.APPLY)",
        1,
    )
    target = tmp_path / "pitchlog/authz/product_provisioning.py"
    target.parent.mkdir(parents=True)
    target.write_text(mutated, encoding="utf-8")
    with pytest.raises(AssertionError, match="直接呼び出し"):
        _validate_terminal_boundary(tmp_path)


@pytest.mark.parametrize(
    "rogue_source",
    [
        pytest.param(
            "import pitchlog.authz.product_provisioning\n",
            id="absolute-module-import",
        ),
        pytest.param(
            "from pitchlog.authz import product_provisioning\n",
            id="from-parent-module-import",
        ),
        pytest.param(
            "from . import product_provisioning\n",
            id="relative-module-import",
        ),
        pytest.param(
            "from pitchlog.authz.product_provisioning import *\n",
            id="star-import",
        ),
        pytest.param(
            "from pitchlog.authz.product_provisioning import _run_product_operation\n",
            id="terminal-import",
        ),
        pytest.param(
            "from pitchlog.authz.product_provisioning import _ProductStatement\n",
            id="other-private-import",
        ),
        pytest.param(
            "from pitchlog.authz.product_provisioning import PRODUCT_SPEC\n",
            id="asset-spec-import",
        ),
        pytest.param(
            "from pitchlog.authz.product_provisioning import "
            "load_product_application_steps\n",
            id="asset-loader-import",
        ),
        pytest.param(
            "from pitchlog.authz.product_provisioning import generate_authz_ddl\n",
            id="statement-generator-import",
        ),
    ],
)
def test_external_import_shapes_outside_the_closed_rule_are_red(
    rogue_source: str,
    tmp_path: Path,
) -> None:
    """外部では公開名の名前付き from import 以外をすべて拒否する。"""
    target = tmp_path / "pitchlog/authz/product_provisioning.py"
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
    target = tmp_path / "pitchlog/authz/product_provisioning.py"
    target.parent.mkdir(parents=True)
    target.write_text(_SOURCE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    consumer = tmp_path / "pitchlog/consumer.py"
    consumer.write_text(
        "from pitchlog.authz.product_provisioning import "
        f"{public_name} as public_api\n",
        encoding="utf-8",
    )

    _validate_terminal_boundary(tmp_path)


@pytest.mark.parametrize(
    "rogue_source",
    [
        pytest.param(
            "import pitchlog.authz\n_MODULE = pitchlog.authz.product_provisioning\n",
            id="absolute-parent-attribute",
        ),
        pytest.param(
            "import pitchlog\n_MODULE = pitchlog.authz.product_provisioning\n",
            id="absolute-root-attribute",
        ),
        pytest.param(
            "from .. import authz\n_MODULE = authz.product_provisioning\n",
            id="relative-parent-attribute",
        ),
    ],
)
def test_target_module_name_attribute_reference_is_red(
    rogue_source: str,
    tmp_path: Path,
) -> None:
    """対象モジュール名と同じ属性の参照を由来によらず拒否する。"""
    target = tmp_path / "pitchlog/authz/product_provisioning.py"
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
            '__all__ = ("_run_product_operation",)\n',
            id="terminal-literal",
        ),
        pytest.param(
            '_EXPORTED = ("_run_product_operation",)\n__all__ = _EXPORTED\n',
            id="name-indirection",
        ),
        pytest.param(
            '__all__ = ("_run_" + "product_operation",)\n',
            id="string-concatenation",
        ),
        pytest.param(
            '__all__ = ("apply_product_authz_ddl",)\n'
            '__all__ += ("_run_product_operation",)\n',
            id="augmented-assignment",
        ),
        pytest.param(
            '__all__ = ["apply_product_authz_ddl"]\n'
            '__all__.append("_run_product_operation")\n',
            id="append",
        ),
        pytest.param(
            '__all__ = ["apply_product_authz_ddl"]\n'
            '__all__.extend(["_run_product_operation"])\n',
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
    target = tmp_path / "pitchlog/authz/product_provisioning.py"
    target.parent.mkdir(parents=True)
    target.write_text(mutated, encoding="utf-8")

    with pytest.raises(AssertionError, match="__all__"):
        _validate_terminal_boundary(tmp_path)


def test_literal_public_module_all_is_green(tmp_path: Path) -> None:
    """公開名だけの単一リテラル __all__ は許可する。"""
    source = _SOURCE_PATH.read_text(encoding="utf-8")
    exports = ", ".join(repr(name) for name in sorted(_PUBLIC_IMPORT_NAMES))
    target = tmp_path / "pitchlog/authz/product_provisioning.py"
    target.parent.mkdir(parents=True)
    target.write_text(f"{source}\n__all__ = ({exports},)\n", encoding="utf-8")

    _validate_terminal_boundary(tmp_path)


def test_generated_apply_and_unapply_statements_never_change_subject() -> None:
    """正規資産から作る適用・取り外し文に主体変更が 1 件もない。"""
    for operation in ProductOperation:
        steps, statements = product_provisioning._build_operation_statements(operation)
        assert steps.transaction == "single"
        assert {statement.sequence for statement in statements} == set(range(1, 8))
        product_provisioning._assert_no_subject_change(statements)

    _, apply_statements = product_provisioning._build_operation_statements(
        ProductOperation.APPLY
    )
    policy_statements = tuple(
        statement for statement in apply_statements if statement.sequence == 5
    )
    assert policy_statements
    assert all(
        statement.sql.startswith("DROP POLICY IF EXISTS")
        for statement in policy_statements
    )

    _, unapply_statements = product_provisioning._build_operation_statements(
        ProductOperation.UNAPPLY
    )
    policy_sequences = {
        statement.sequence
        for statement in unapply_statements
        if "DROP POLICY" in statement.sql
    }
    helper_sequences = {
        statement.sequence
        for statement in unapply_statements
        if "tenant_has_effective_membership" in statement.sql
    }
    assert policy_sequences == {3}
    assert helper_sequences == {5}
    assert all(
        "DROP ROLE IF EXISTS pitchlog_owner" not in row.sql
        for row in unapply_statements
    )


def test_generated_unapply_statements_use_structured_quoted_identifiers() -> None:
    """取り外し全文は要素 ID を SQL に流さず全識別子を正しく引用する。"""
    _, statements = product_provisioning._build_operation_statements(
        ProductOperation.UNAPPLY
    )
    sql_texts = tuple(statement.sql for statement in statements)
    assert sql_texts
    assert all(
        "FUNCTION:" not in sql_text and ":" not in sql_text for sql_text in sql_texts
    )

    trigger_function_grants = tuple(
        sql_text
        for sql_text in sql_texts
        if sql_text.startswith("GRANT EXECUTE ON FUNCTION")
    )
    assert len(trigger_function_grants) == 37
    trigger_function_pattern = re.compile(
        r'^GRANT EXECUTE ON FUNCTION "public"\."[a-z0-9_]+"\(\) TO PUBLIC;$'
    )
    assert all(
        trigger_function_pattern.fullmatch(sql_text) is not None
        for sql_text in trigger_function_grants
    )

    assert (
        'DROP FUNCTION IF EXISTS "authz_private".'
        '"tenant_has_effective_membership"(uuid, boolean);' in sql_texts
    )

    assert 'DROP ROLE IF EXISTS "pitchlog_app";' in sql_texts
    assert 'DROP SCHEMA IF EXISTS "authz_private";' in sql_texts
    assert any(
        'ALTER TABLE "public"."tenants" NO FORCE ROW LEVEL SECURITY;' in sql_text
        for sql_text in sql_texts
    )
    assert (
        'DROP POLICY IF EXISTS "pitchlog_app_self_tenant_row" '
        'ON "public"."tenants";' in sql_texts
    )
    assert (
        'REVOKE ALL PRIVILEGES ON TABLE "public"."team_records" '
        'FROM "pitchlog_app";' in sql_texts
    )
    assert (
        'REVOKE SELECT ("id") ON TABLE "public"."tenants" '
        'FROM "pitchlog_shared_fn_owner";' in sql_texts
    )
    database_statements = tuple(
        sql_text for sql_text in sql_texts if "ON DATABASE %I" in sql_text
    )
    assert len(database_statements) == 1
    for role_id in (
        "pitchlog_app",
        "pitchlog_shared_fn_owner",
        "pitchlog_management_fn_owner",
    ):
        assert f'"{role_id}"' in database_statements[0]


def test_definer_unapplication_never_restores_public_execute() -> None:
    """definerの取り外しは関数を落とし、PUBLIC実行権を復帰しない。"""
    from pitchlog.authz.ddl import DDLStatement

    fields: dict[str, object] = {
        "schema_name": "authn",
        "function_name": "test_definer",
        "identity_args": "text",
        "function_kind": "definer",
    }
    element = product_provisioning._ProductElement(
        "function", "FUNCTION:authn:test_definer(text)", fields
    )
    statement = DDLStatement(
        element_type="function",
        element_id=element.element_id,
        source_path=PurePosixPath(
            "contracts/authz/product/function-bodies/functions/test.sql"
        ),
        sql=(
            "CREATE FUNCTION authn.test_definer(text) RETURNS text "
            "LANGUAGE sql AS 'SELECT $1';"
        ),
    )
    sql_text = product_provisioning._unapplication_sql(
        statement, element, (element,), ()
    )
    assert sql_text == 'DROP FUNCTION IF EXISTS "authn"."test_definer"(text);'
    assert "TO PUBLIC" not in sql_text


def test_product_identifier_quoting_escapes_embedded_double_quotes() -> None:
    """識別子引用は PostgreSQL の二重引用符規則に従う。"""
    assert product_provisioning._quote_identifier('schema"name') == ('"schema""name"')


def test_apply_and_unapply_sql_assembly_never_reads_element_id() -> None:
    """適用・取り外しの SQL 組み立ては要素 ID の分解へ依存しない。"""
    tree = _parse_source(_SOURCE_PATH.read_text(encoding="utf-8"))
    assembly_functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name in {"_application_statements", "_unapplication_sql"}
    }
    assert set(assembly_functions) == {
        "_application_statements",
        "_unapplication_sql",
    }
    for function in assembly_functions.values():
        element_id_reads = tuple(
            node
            for node in ast.walk(function)
            if isinstance(node, ast.Attribute)
            and isinstance(node.ctx, ast.Load)
            and node.attr == "element_id"
        )
        assert element_id_reads == ()


def test_public_apply_executes_the_canonical_generated_plan() -> None:
    """公開適用経路が正規資産の生成結果を実際の実行文として使う。"""
    connection = _FakeConnection()

    apply_product_authz_ddl(_as_psycopg_connection(connection))

    assert len(connection.executed_statements) == 158
    decoded = tuple(
        statement.decode("utf-8")
        for statement in connection.executed_statements
        if isinstance(statement, bytes)
    )
    assert len(decoded) == len(connection.executed_statements)
    helper_position = next(
        index
        for index, statement in enumerate(decoded)
        if "CREATE OR REPLACE FUNCTION authz_private.tenant_has_effective_membership"
        in statement
    )
    first_policy_position = next(
        index
        for index, statement in enumerate(decoded)
        if statement.startswith("DROP POLICY IF EXISTS")
    )
    assert helper_position < first_policy_position
    assert connection.commit_count == 1
    assert connection.rollback_count == 0


def test_apply_uses_one_transaction_and_checks_identity_at_every_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
    application_steps: ProductApplicationSteps,
) -> None:
    """公開適用経路は 7 手順を 1 回だけ commit し全記録点で主体を検査する。"""
    connection = _FakeConnection()
    checkpoints: list[str] = []
    monkeypatch.setattr(
        product_provisioning,
        "_build_operation_statements",
        lambda operation: _small_operation_plan(application_steps),
    )
    monkeypatch.setattr(
        product_provisioning,
        "_record_product_checkpoint",
        checkpoints.append,
    )

    apply_product_authz_ddl(_as_psycopg_connection(connection))

    assert connection.executed_statements == [
        f"SELECT {sequence}".encode() for sequence in range(1, 8)
    ]
    assert connection.commit_count == 1
    assert connection.rollback_count == 0
    assert connection.autocommit is False
    assert checkpoints == [
        "product:1:after",
        "product:3:after_helper_function_creation",
        "product:4:after",
        "product:5:after_policy_creation",
        "product:6:during",
        "product:7:after_commit",
    ]
    assert connection.identity_query_count == len(checkpoints)
    assert connection.parameter_status_calls == [
        "session_authorization",
        "is_superuser",
    ]


@pytest.mark.parametrize(
    ("identity_query_number", "expected_commit_count", "expected_rollback_count"),
    [
        pytest.param(1, 0, 1, id="step-1"),
        pytest.param(2, 0, 1, id="step-3-helper"),
        pytest.param(3, 0, 1, id="step-4"),
        pytest.param(4, 0, 1, id="step-5-policy"),
        pytest.param(5, 0, 1, id="step-6-during"),
        pytest.param(6, 1, 0, id="after-commit"),
    ],
)
def test_identity_mismatch_at_each_checkpoint_is_red_through_public_path(
    identity_query_number: int,
    expected_commit_count: int,
    expected_rollback_count: int,
    monkeypatch: pytest.MonkeyPatch,
    application_steps: ProductApplicationSteps,
) -> None:
    """各記録点で current_user が変わる変異を公開適用経路が拒否する。"""
    connection = _FakeConnection()
    connection.identity_overrides[identity_query_number] = (
        "changed_subject",
        "external_superuser",
        True,
    )
    monkeypatch.setattr(
        product_provisioning,
        "_build_operation_statements",
        lambda operation: _small_operation_plan(application_steps),
    )

    with pytest.raises(ProductProvisioningError, match="current_user"):
        apply_product_authz_ddl(_as_psycopg_connection(connection))

    assert connection.commit_count == expected_commit_count
    assert connection.rollback_count == expected_rollback_count


def test_identity_mismatch_after_rollback_is_red_through_public_path(
    monkeypatch: pytest.MonkeyPatch,
    application_steps: ProductApplicationSteps,
) -> None:
    """故障後の rollback 記録点でも主体不一致を公開経路が拒否する。"""
    connection = _FakeConnection()
    connection.identity_overrides[2] = (
        "changed_subject",
        "external_superuser",
        True,
    )
    monkeypatch.setattr(
        product_provisioning,
        "_build_operation_statements",
        lambda operation: _small_operation_plan(application_steps),
    )

    def fail_at_checkpoint(checkpoint_id: str) -> None:
        raise RuntimeError(checkpoint_id)

    monkeypatch.setattr(
        product_provisioning,
        "_record_product_checkpoint",
        fail_at_checkpoint,
    )

    with pytest.raises(ProductProvisioningError, match="current_user"):
        apply_product_authz_ddl(_as_psycopg_connection(connection))

    assert connection.commit_count == 0
    assert connection.rollback_count == 1
    assert connection.autocommit is False


@pytest.mark.parametrize(
    ("connection", "message"),
    [
        pytest.param(_FakeConnection(closed=True), "閉じた接続", id="closed"),
        pytest.param(_FakeConnection(autocommit=True), "autocommit", id="autocommit"),
        pytest.param(
            _FakeConnection(transaction_status=pq.TransactionStatus.INTRANS),
            "進行中のトランザクション",
            id="transaction-not-idle",
        ),
        pytest.param(
            _FakeConnection(is_superuser=False),
            "superuser",
            id="not-superuser",
        ),
        pytest.param(
            _FakeConnection(
                current_user="pitchlog_app",
                session_user="pitchlog_app",
                is_superuser=True,
            ),
            "pitchlog_app",
            id="pitchlog-app",
        ),
    ],
)
def test_each_connection_precondition_rejects_before_generated_statements(
    connection: _FakeConnection,
    message: str,
    monkeypatch: pytest.MonkeyPatch,
    application_steps: ProductApplicationSteps,
) -> None:
    """各接続前提の違反は公開経路で DDL・commit・rollback より先に拒否する。"""
    monkeypatch.setattr(
        product_provisioning,
        "_build_operation_statements",
        lambda operation: _small_operation_plan(application_steps),
    )

    with pytest.raises(ProductProvisioningError, match=message):
        apply_product_authz_ddl(_as_psycopg_connection(connection))

    assert connection.executed_statements == []
    assert connection.execute_calls == []
    assert connection.commit_count == 0
    assert connection.rollback_count == 0


def test_missing_session_authorization_is_fail_closed_without_execute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """接続主体の通知値が欠けても SQL を使った推測へ進まず拒否する。"""
    connection = _FakeConnection()

    def parameter_status(name: str) -> str | None:
        return None if name == "session_authorization" else "on"

    monkeypatch.setattr(connection.info, "parameter_status", parameter_status)

    with pytest.raises(ProductProvisioningError, match="session_authorization"):
        apply_product_authz_ddl(_as_psycopg_connection(connection))

    assert connection.execute_calls == []
    assert connection.commit_count == 0
    assert connection.rollback_count == 0


def test_subject_change_inside_one_step_is_red_through_public_path(
    monkeypatch: pytest.MonkeyPatch,
    application_steps: ProductApplicationSteps,
) -> None:
    """途中だけ SET/RESET ROLE する文も公開適用経路が実行前に拒否する。"""
    connection = _FakeConnection()
    _, statements = _small_operation_plan(application_steps)
    mutated = tuple(
        product_provisioning._ProductStatement(
            sequence=statement.sequence,
            sql=(
                f"SET ROLE pitchlog_owner;\n{statement.sql};\nRESET ROLE;"
                if statement.sequence == 4
                else statement.sql
            ),
        )
        for statement in statements
    )
    monkeypatch.setattr(
        product_provisioning,
        "_build_operation_statements",
        lambda operation: (application_steps, mutated),
    )

    with pytest.raises(ProductProvisioningError, match="適用主体を変更"):
        apply_product_authz_ddl(_as_psycopg_connection(connection))

    assert connection.executed_statements == []
    assert connection.execute_calls == []
    assert connection.commit_count == 0
    assert connection.rollback_count == 0
