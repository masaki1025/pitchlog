"""認証アプリ層の公開操作と DB 到達点を閉じた集合として照合する。"""

import ast
import re
import shutil
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from pitchlog.authz.database_transport import (
    DatabaseTransportConfigurationError,
    require_database_transport,
)
from pitchlog.authz.signing_key_config import (
    SigningKeyConfigurationError,
    require_signing_key_configuration,
)
from pitchlog.authz.token_presentation import TokenPresentation
from pitchlog.authz.verified_tenant import verify_tenant_id

_SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src" / "pitchlog"
_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_MODULES = frozenset(
    {
        "authz.token_presentation",
        "authz.signing_key_config",
        "authz.database_transport",
        "authz.verified_tenant",
    }
)
_PUBLIC_OPERATIONS = frozenset(
    {
        "authz.token_presentation.TokenPresentation",
        "authz.token_presentation.TokenPresentation.encode",
        "authz.token_presentation.TokenPresentation.decode",
        "authz.signing_key_config.require_signing_key_configuration",
        "authz.database_transport.require_database_transport",
        "authz.verified_tenant.verify_tenant_id",
    }
)
_DB_ENDPOINTS: dict[str, str | None] = {
    "authn.verify_token": "authz.verified_tenant.verify_tenant_id",
    "authn.logout": None,
    "authn.change_password": None,
}
_DB_REACH = frozenset(
    (caller, endpoint)
    for endpoint, caller in _DB_ENDPOINTS.items()
    if caller is not None
)
_PUBLIC_CALLERS = frozenset(
    {
        (
            "api.app.create_app",
            "authz.signing_key_config.require_signing_key_configuration",
        ),
        ("api.app.create_app", "authz.token_presentation.TokenPresentation"),
        (
            "db.engine.create_database_engine",
            "authz.database_transport.require_database_transport",
        ),
        (
            "authz.verified_tenant.verify_tenant_id",
            "authz.token_presentation.TokenPresentation.decode",
        ),
    }
)
_AUTHN_REFERENCE = re.compile(r"\bauthn\.([a-z_]+)\b")


def _tree(path: Path) -> ast.Module:
    """製品ソースを構文木へ変換する。"""
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _module(path: Path, root: Path) -> str:
    """ソースルート相対のモジュール名を返す。"""
    parts = path.relative_to(root).with_suffix("").parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _public_operations(root: Path) -> frozenset[str]:
    """本単位の四モジュールにある公開関数・クラス操作を列挙する。"""
    found: set[str] = set()
    for module in _MODULES:
        tree = _tree(root.joinpath(*module.split(".")).with_suffix(".py"))
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not node.name.startswith("_"):
                    found.add(f"{module}.{node.name}")
            elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
                if any(
                    isinstance(base, ast.Name)
                    and base.id.endswith(("Error", "Exception"))
                    for base in node.bases
                ):
                    continue
                found.add(f"{module}.{node.name}")
                for method in node.body:
                    if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if not method.name.startswith("_"):
                            found.add(f"{module}.{node.name}.{method.name}")
    return frozenset(found)


def _symbol(node: ast.AST) -> str | None:
    """Name または Attribute の静的な名前を返す。"""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _symbol(node.value)
        return f"{parent}.{node.attr}" if parent else None
    return None


def _function_calls(tree: ast.Module, module: str) -> list[tuple[str, ast.Call]]:
    """呼び出し式と最も内側の関数名を列挙する。"""
    calls: list[tuple[str, ast.Call]] = []

    class Visitor(ast.NodeVisitor):
        """関数の入れ子を保持して呼び出しを訪問する。"""

        def __init__(self) -> None:
            self.stack: list[str] = []

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            """関数名を保持して本文を走査する。"""
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            """非同期関数名を保持して本文を走査する。"""
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        def visit_Call(self, node: ast.Call) -> None:
            """関数内の呼び出しを採集する。"""
            if self.stack:
                calls.append((f"{module}.{self.stack[-1]}", node))
            self.generic_visit(node)

    Visitor().visit(tree)
    return calls


def _public_callers(root: Path) -> frozenset[tuple[str, str]]:
    """製品コードから本単位の公開操作への呼び出しを列挙する。"""
    found: set[tuple[str, str]] = set()
    for path in root.rglob("*.py"):
        module = _module(path, root)
        tree = _tree(path)
        imports: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                source = node.module.removeprefix("pitchlog.")
                if source in _MODULES:
                    for alias in node.names:
                        imports[alias.asname or alias.name] = f"{source}.{alias.name}"
                elif source == "authz":
                    for alias in node.names:
                        candidate = f"authz.{alias.name}"
                        if candidate in _MODULES:
                            imports[alias.asname or alias.name] = candidate
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    source = alias.name.removeprefix("pitchlog.")
                    if source in _MODULES and alias.asname:
                        imports[alias.asname] = source
        receivers: dict[str, dict[str, str]] = {}
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            caller = f"{module}.{node.name}"
            typed: dict[str, str] = {}
            for argument in (
                *node.args.posonlyargs,
                *node.args.args,
                *node.args.kwonlyargs,
            ):
                annotation = (
                    _symbol(argument.annotation) if argument.annotation else None
                )
                if annotation is not None and annotation in imports:
                    typed[argument.arg] = imports[annotation]
            for assignment in ast.walk(node):
                if not isinstance(assignment, ast.Assign):
                    continue
                if not isinstance(assignment.value, ast.Call):
                    continue
                created = _symbol(assignment.value.func)
                if created not in imports:
                    continue
                for target in assignment.targets:
                    if isinstance(target, ast.Name):
                        typed[target.id] = imports[created]
            receivers[caller] = typed
        for caller, call in _function_calls(tree, module):
            name = _symbol(call.func)
            if name is None:
                continue
            head, _, tail = name.partition(".")
            target = imports.get(head) or receivers.get(caller, {}).get(head)
            if target is not None:
                target += f".{tail}" if tail else ""
                if target in _PUBLIC_OPERATIONS:
                    found.add((caller, target))
    return frozenset(found)


def _db_reach(root: Path) -> frozenset[tuple[str, str]]:
    """製品コードの SQL 呼び出しから authn 関数への到達を列挙する。"""
    found: set[tuple[str, str]] = set()
    for path in root.rglob("*.py"):
        module = _module(path, root)
        tree = _tree(path)
        sql_constants: dict[str, set[str]] = {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            values = {
                literal.value
                for literal in ast.walk(node.value)
                if isinstance(literal, ast.Constant) and isinstance(literal.value, str)
            }
            for target in node.targets:
                if isinstance(target, ast.Name):
                    sql_constants.setdefault(target.id, set()).update(values)
        for caller, call in _function_calls(tree, module):
            if not isinstance(call.func, ast.Attribute) or call.func.attr not in {
                "execute",
                "exec_driver_sql",
                "callproc",
            }:
                continue
            for arg in call.args:
                values = {
                    literal.value
                    for literal in ast.walk(arg)
                    if isinstance(literal, ast.Constant)
                    and isinstance(literal.value, str)
                }
                if isinstance(arg, ast.Name):
                    values.update(sql_constants.get(arg.id, set()))
                for value in values:
                    for match in _AUTHN_REFERENCE.finditer(value):
                        found.add((caller, f"authn.{match.group(1)}"))
    return frozenset(found)


def _assert_exact(expected: frozenset[Any], actual: frozenset[Any]) -> None:
    """空の期待集合と差分の両方を拒否する。"""
    assert expected, "期待集合が空です"
    assert actual, "実装からの導出集合が空です"
    assert actual == expected, (
        f"集合の差分: 追加={actual - expected}, 消失={expected - actual}"
    )


def test_public_operations_and_callers_are_exact_sets() -> None:
    """公開操作と既存の製品呼び出し元を過不足なく固定する。"""
    _assert_exact(_PUBLIC_OPERATIONS, _public_operations(_SOURCE_ROOT))
    _assert_exact(_PUBLIC_CALLERS, _public_callers(_SOURCE_ROOT))


def test_db_reach_is_exact_set_and_absences_are_explicit() -> None:
    """検証兼延長だけを到達点とし、未接続の二関数を明示する。"""
    assert set(_DB_ENDPOINTS) == {
        "authn.verify_token",
        "authn.logout",
        "authn.change_password",
    }
    assert _DB_ENDPOINTS["authn.logout"] is None
    assert _DB_ENDPOINTS["authn.change_password"] is None
    _assert_exact(_DB_REACH, _db_reach(_SOURCE_ROOT))


def test_beta_functions_and_current_absences_are_explicit() -> None:
    """β の三関数とアプリ層の未接続点を資産から確かめる。"""
    functions = _REPOSITORY_ROOT / "contracts/authz/product/function-bodies/functions"
    verified = (functions / "FUNCTION:authn:verify_token(uuid).sql").read_text(
        encoding="utf-8"
    )
    logged_out = (functions / "FUNCTION:authn:logout(uuid).sql").read_text(
        encoding="utf-8"
    )
    changed = (
        functions / "FUNCTION:authn:change_password(uuid, text, text).sql"
    ).read_text(encoding="utf-8")

    assert "CREATE OR REPLACE FUNCTION authn.verify_token(p_token_id uuid)" in verified
    assert "SET last_used_at = checked_at," in verified
    assert "expires_at = checked_at + token_ttl" in verified
    assert "CREATE OR REPLACE FUNCTION authn.logout(p_token_id uuid)" in logged_out
    assert (
        "SET expires_at = greatest(logged_out_at, previous_last_used_at)" in logged_out
    )
    assert "GRANT EXECUTE ON FUNCTION authn.logout(uuid) TO pitchlog_app" in logged_out
    assert "CREATE OR REPLACE FUNCTION authn.change_password(p_token_id uuid" in changed
    assert _DB_ENDPOINTS["authn.logout"] is None
    assert _DB_ENDPOINTS["authn.verify_token"] == (
        "authz.verified_tenant.verify_tenant_id"
    )
    assert _DB_ENDPOINTS["authn.change_password"] is None


def test_db_verification_and_extension_rejects_null() -> None:
    """署名が正しくても DB が無効と判定したらテナント ID を返さない。"""
    signer = TokenPresentation(b"test" * 8)
    engine = MagicMock()
    connection = engine.begin.return_value.__enter__.return_value
    connection.execute.return_value.scalar_one.return_value = None

    assert verify_tenant_id(signer.encode(UUID(int=1)), signer, engine) is None
    statement, parameters = connection.execute.call_args.args
    assert str(statement) == "SELECT authn.verify_token(:token_id)"
    assert parameters == {"token_id": UUID(int=1)}


def test_empty_sets_are_rejected() -> None:
    """期待集合または実装側が空なら照合が失敗する。"""
    for expected, actual in (
        (frozenset(), _public_operations(_SOURCE_ROOT)),
        (_PUBLIC_OPERATIONS, frozenset()),
        (frozenset(), _db_reach(_SOURCE_ROOT)),
        (_DB_REACH, frozenset()),
    ):
        with pytest.raises(AssertionError):
            _assert_exact(expected, actual)


def test_added_implementation_caller_breaks_exact_set(tmp_path: Path) -> None:
    """新しい製品呼び出し元が実装へ届いた後に照合が落ちる。"""
    root = tmp_path / "pitchlog"
    shutil.copytree(_SOURCE_ROOT, root)
    added = root / "authz" / "new_caller.py"
    added.write_text(
        "from pitchlog.authz.verified_tenant import verify_tenant_id\n"
        "def added_caller(value, presentation, engine):\n"
        "    return verify_tenant_id(value, presentation, engine)\n",
        encoding="utf-8",
    )
    derived = _public_callers(root)
    added_edge = (
        "authz.new_caller.added_caller",
        "authz.verified_tenant.verify_tenant_id",
    )
    assert added_edge in derived
    with pytest.raises(AssertionError, match="集合の差分"):
        _assert_exact(_PUBLIC_CALLERS, derived)


def test_added_public_operation_breaks_exact_set(tmp_path: Path) -> None:
    """公開入口を実装へ増やすと公開操作の集合照合が落ちる。"""
    root = tmp_path / "pitchlog"
    shutil.copytree(_SOURCE_ROOT, root)
    source = root / "authz" / "verified_tenant.py"
    source.write_text(
        source.read_text(encoding="utf-8")
        + "\ndef added_operation(value):\n    return value\n",
        encoding="utf-8",
    )
    derived = _public_operations(root)
    assert "authz.verified_tenant.added_operation" in derived
    with pytest.raises(AssertionError, match="集合の差分"):
        _assert_exact(_PUBLIC_OPERATIONS, derived)


def test_added_implementation_db_reach_breaks_exact_set(tmp_path: Path) -> None:
    """新しい authn 呼び出しが実装へ届いた後に照合が落ちる。"""
    root = tmp_path / "pitchlog"
    shutil.copytree(_SOURCE_ROOT, root)
    added = root / "authz" / "new_db_caller.py"
    added.write_text(
        "def added_caller(connection, token_id):\n"
        "    return connection.execute('SELECT authn.logout(:token_id)', "
        "{'token_id': token_id})\n",
        encoding="utf-8",
    )
    derived = _db_reach(root)
    added_edge = ("authz.new_db_caller.added_caller", "authn.logout")
    assert added_edge in derived
    with pytest.raises(AssertionError, match="集合の差分"):
        _assert_exact(_DB_REACH, derived)


def test_added_local_sql_db_reach_breaks_exact_set(tmp_path: Path) -> None:
    """関数内の SQL 変数を介した認証関数呼び出しも検出する。"""
    root = tmp_path / "pitchlog"
    shutil.copytree(_SOURCE_ROOT, root)
    added = root / "authz" / "new_password_caller.py"
    added.write_text(
        "def added_caller(connection, token_id, old, new):\n"
        "    statement = 'SELECT authn.change_password(:token_id, :old, :new)'\n"
        "    return connection.exec_driver_sql(statement, "
        "{'token_id': token_id, 'old': old, 'new': new})\n",
        encoding="utf-8",
    )
    derived = _db_reach(root)
    added_edge = ("authz.new_password_caller.added_caller", "authn.change_password")
    assert added_edge in derived
    with pytest.raises(AssertionError, match="集合の差分"):
        _assert_exact(_DB_REACH, derived)


@pytest.mark.parametrize("operation", sorted(_PUBLIC_OPERATIONS))
def test_each_public_operation_has_a_negative_case(operation: str) -> None:
    """公開操作ごとに不正入力が拒否または非到達となる。"""
    if operation == "authz.token_presentation.TokenPresentation":
        with pytest.raises(TypeError):
            TokenPresentation(cast(bytes, "invalid"))
    elif operation == "authz.token_presentation.TokenPresentation.encode":
        with pytest.raises(TypeError):
            TokenPresentation(b"test" * 8).encode(cast(UUID, "invalid"))
    elif operation == "authz.token_presentation.TokenPresentation.decode":
        with pytest.raises(ValueError):
            TokenPresentation(b"test" * 8).decode("invalid")
    elif operation == "authz.signing_key_config.require_signing_key_configuration":
        with pytest.raises(SigningKeyConfigurationError):
            require_signing_key_configuration("TEST_KEY", None)
    elif operation == "authz.database_transport.require_database_transport":
        with pytest.raises(DatabaseTransportConfigurationError):
            require_database_transport(
                "postgresql+psycopg://localhost/pitchlog", {"sslmode": "prefer"}
            )
    elif operation == "authz.verified_tenant.verify_tenant_id":
        engine = MagicMock()
        assert (
            verify_tenant_id(str(UUID(int=1)), TokenPresentation(b"test" * 8), engine)
            is None
        )
        engine.begin.assert_not_called()
    else:
        pytest.fail(f"負例のない公開操作: {operation}")
