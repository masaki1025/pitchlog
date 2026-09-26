"""製品認可 DDL の適用器が閉じた実行経路だけを持つことを検査する。"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path
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
_SOURCE_PATH = _REPOSITORY_ROOT / "backend/src/pitchlog/authz/product_provisioning.py"
_EXPECTED_TERMINAL_SIGNATURE = (
    "_run_product_operation(connection: psycopg.Connection[Any], "
    "operation: ProductOperation) -> None"
)
_DB_METHOD_NAMES = {"cursor", "execute", "commit", "rollback"}


class _FakeInfo:
    """Psycopg 接続情報のうち適用器が読む状態だけを持つ。"""

    def __init__(self, transaction_status: pq.TransactionStatus) -> None:
        self.transaction_status = transaction_status


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
        self.info = _FakeInfo(transaction_status)
        self.current_user = current_user
        self.session_user = session_user
        self.is_superuser = is_superuser
        self.executed_statements: list[object] = []
        self.identity_query_count = 0
        self.identity_overrides: dict[int, tuple[object, ...]] = {}
        self.commit_count = 0
        self.rollback_count = 0

    def cursor(self) -> _FakeCursor:
        """試験用 cursor を返す。"""
        return _FakeCursor(self)

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


def _parse_source(source: str) -> ast.Module:
    """適用器ソースを AST として読む。"""
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


def _validate_terminal_boundary(source: str) -> None:
    """末端のシグネチャ・参照集合・DB 呼び出し所属を検査する。"""
    tree = _parse_source(source)
    parents = {
        child: parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }
    ancestors = _function_ancestors(tree)
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

    references: list[str] = []
    for node in ast.walk(tree):
        is_name_reference = (
            isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Load)
            and node.id == "_run_product_operation"
        )
        is_attribute_reference = (
            isinstance(node, ast.Attribute)
            and isinstance(node.ctx, ast.Load)
            and node.attr == "_run_product_operation"
        )
        if not is_name_reference and not is_attribute_reference:
            continue
        parent = parents.get(node)
        if not isinstance(parent, ast.Call) or parent.func is not node:
            raise AssertionError("製品適用器の末端が直接呼び出し以外で参照された")
        references.append(ancestors[node])
    if sorted(references) != [
        "apply_product_authz_ddl",
        "unapply_product_authz_ddl",
    ]:
        raise AssertionError("製品適用器の末端を参照する関数が exact-set でない")

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
    _validate_terminal_boundary(_SOURCE_PATH.read_text(encoding="utf-8"))


def test_adding_statement_or_asset_path_argument_is_red() -> None:
    """末端に文や資産の置き場を渡せる引数を足す変異を拒否する。"""
    source = _SOURCE_PATH.read_text(encoding="utf-8")
    mutated = source.replace(
        "    operation: ProductOperation,\n) -> None:",
        "    operation: ProductOperation,\n    asset_root: Path,\n) -> None:",
        1,
    )
    with pytest.raises(AssertionError, match="シグネチャ"):
        _validate_terminal_boundary(mutated)


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
def test_adding_a_terminal_reference_is_red(extra_reference: str) -> None:
    """同じモジュール内に末端の名前・属性参照を足す変異を拒否する。"""
    source = _SOURCE_PATH.read_text(encoding="utf-8")
    mutated = f"{source}\n_EXTRA_RUNNER = {extra_reference}\n"
    with pytest.raises(AssertionError, match="直接呼び出し"):
        _validate_terminal_boundary(mutated)


def test_calling_terminal_through_an_alias_is_red() -> None:
    """公開関数が末端を別名へ代入して呼ぶ変異を拒否する。"""
    source = _SOURCE_PATH.read_text(encoding="utf-8")
    mutated = source.replace(
        "    _run_product_operation(connection, ProductOperation.APPLY)",
        "    runner = _run_product_operation\n"
        "    runner(connection, ProductOperation.APPLY)",
        1,
    )
    with pytest.raises(AssertionError, match="直接呼び出し"):
        _validate_terminal_boundary(mutated)


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
    assert connection.identity_query_count == len(checkpoints) + 1


@pytest.mark.parametrize(
    ("identity_query_number", "expected_commit_count", "expected_rollback_count"),
    [
        pytest.param(1, 0, 0, id="precondition"),
        pytest.param(2, 0, 1, id="step-1"),
        pytest.param(3, 0, 1, id="step-3-helper"),
        pytest.param(4, 0, 1, id="step-4"),
        pytest.param(5, 0, 1, id="step-5-policy"),
        pytest.param(6, 0, 1, id="step-6-during"),
        pytest.param(7, 1, 0, id="after-commit"),
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
    connection.identity_overrides[3] = (
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
    assert connection.commit_count == 0
    assert connection.rollback_count == 0
