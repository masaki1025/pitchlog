"""製品認可の DB 末端シンボルと正例 fixture の閉包を検査する。"""

from __future__ import annotations

import ast
import importlib.util
import shutil
import sys
from pathlib import Path
from types import ModuleType

import pytest

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_CHECKER_PATH = _REPOSITORY_ROOT / "scripts/check_tenant_boundary_bypass.py"
_POSITIVE_ROOT = _REPOSITORY_ROOT / "tests/fixtures/tenant_boundary/positive"
_GITHUB_ENVIRONMENT_NAMES = (
    "GITHUB_EVENT_PATH",
    "GITHUB_EVENT_NAME",
    "GITHUB_BASE_REF",
    "GITHUB_WORKSPACE",
    "GITHUB_REPOSITORY",
)
_PRODUCT_SYMBOLS = {
    "pitchlog.authz.product_provisioning._run_product_operation": {
        "signature": (
            "_run_product_operation(connection: psycopg.Connection[Any], "
            "operation: ProductOperation) -> None"
        ),
        "allowed_api_ids": {
            "PSYCOPG_CONNECTION_CURSOR",
            "PSYCOPG_CURSOR_EXECUTE",
            "PSYCOPG_CONNECTION_COMMIT",
            "PSYCOPG_CONNECTION_ROLLBACK",
        },
        "fixture": (
            "tests/fixtures/tenant_boundary/positive/pitchlog/authz/product_provisioning.py"
        ),
    },
    "pitchlog.authz.product_catalog._fetch_catalog_rows": {
        "signature": (
            "_fetch_catalog_rows(connection: psycopg.Connection[Any], "
            "query_id: CatalogQueryId, params: tuple[object, ...]) -> "
            "list[tuple[object, ...]]"
        ),
        "allowed_api_ids": {
            "PSYCOPG_CONNECTION_CURSOR",
            "PSYCOPG_CURSOR_EXECUTE",
        },
        "fixture": ("tests/fixtures/tenant_boundary/positive/pitchlog/authz/product_catalog.py"),
    },
}


def _load_checker() -> ModuleType:
    """検査器をリポジトリの import 設定に依存せず読む。"""
    spec = importlib.util.spec_from_file_location(
        "product_authz_tenant_boundary_checker",
        _CHECKER_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


checker = _load_checker()


@pytest.fixture(autouse=True)
def _clear_github_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """合成リポジトリを CI の PR 受理モードから隔離する。"""
    for name in _GITHUB_ENVIRONMENT_NAMES:
        monkeypatch.delenv(name, raising=False)


def _run_git(repository: Path, arguments: list[str]) -> str:
    """合成リポジトリで Git コマンドを実行する。"""
    return checker._run_git(repository, arguments)


def _commit(repository: Path, message: str) -> str:
    """合成リポジトリの全変更をコミットする。"""
    _run_git(repository, ["add", "."])
    _run_git(
        repository,
        [
            "-c",
            "user.name=Product Authz Test",
            "-c",
            "user.email=product-authz@example.invalid",
            "commit",
            "-m",
            message,
        ],
    )
    return _run_git(repository, ["rev-parse", "HEAD"]).strip()


def _initialize_repository(tmp_path: Path) -> tuple[Path, str]:
    """正例 fixture の exact-set を検査できる合成リポジトリを作る。"""
    repository = tmp_path / "repository"
    shutil.copytree(
        _REPOSITORY_ROOT / "contracts/tenant_boundary",
        repository / "contracts/tenant_boundary",
    )
    shutil.copytree(
        _REPOSITORY_ROOT / "tests/fixtures/tenant_boundary",
        repository / "tests/fixtures/tenant_boundary",
    )
    for relative_path in (
        Path("scripts/check_tenant_boundary_bypass.py"),
        Path("scripts/frozen_history.py"),
        Path(".github/workflows/ci.yml"),
    ):
        destination = repository / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_REPOSITORY_ROOT / relative_path, destination)

    _run_git(repository, ["init"])
    return repository, _commit(repository, "baseline")


def _function_signature(source: str, function_name: str) -> str:
    """Fixture の関数定義から検査器と同じシグネチャを作る。"""
    module = ast.parse(source)
    functions = [
        node
        for node in module.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name
    ]
    assert len(functions) == 1
    return checker._function_signature(functions[0])


def test_product_symbols_match_checker_signatures_and_fixtures() -> None:
    """製品の 2 記号が検査器の署名と許可 API の exact-set に一致する。"""
    contract = checker.load_contract(_REPOSITORY_ROOT)
    actual = {
        item.symbol: item for item in contract.allowed_symbols if item.symbol in _PRODUCT_SYMBOLS
    }

    assert set(actual) == set(_PRODUCT_SYMBOLS)
    for symbol, expected in _PRODUCT_SYMBOLS.items():
        allowed = actual[symbol]
        fixture_path = _REPOSITORY_ROOT / str(expected["fixture"])
        source = fixture_path.read_text(encoding="utf-8")
        assert allowed.signature == expected["signature"]
        assert allowed.signature == _function_signature(source, symbol.rsplit(".", 1)[1])
        assert allowed.allowed_api_ids == expected["allowed_api_ids"]
        assert allowed.fixture == expected["fixture"]
        assert (
            checker.scan_source(
                source,
                path=fixture_path.relative_to(_POSITIVE_ROOT).as_posix(),
                contract=contract,
            )
            == []
        )


def test_catalog_fixture_commit_without_allowed_api_is_red() -> None:
    """COMMIT を許可しないカタログ記号で commit を呼ぶ変異を拒否する。"""
    contract = checker.load_contract(_REPOSITORY_ROOT)
    fixture_path = _POSITIVE_ROOT / "pitchlog/authz/product_catalog.py"
    source = fixture_path.read_text(encoding="utf-8")
    mutated = source.replace(
        "    with connection.cursor() as cursor:\n",
        "    connection.commit()\n    with connection.cursor() as cursor:\n",
        1,
    )
    assert mutated != source

    violations = checker.scan_source(
        mutated,
        path="pitchlog/authz/product_catalog.py",
        contract=contract,
    )

    assert {(violation.code, violation.symbol) for violation in violations} == {
        ("TB005", "psycopg.Connection.commit")
    }


def test_missing_positive_fixture_is_red_through_repository_check(
    tmp_path: Path,
) -> None:
    """正例 fixture を 1 件欠く合成リポジトリを本番検査経路で拒否する。"""
    repository, base_ref = _initialize_repository(tmp_path)
    assert checker.check_repository(repository, base_ref=base_ref) == []
    missing = (
        repository / "tests/fixtures/tenant_boundary/positive/pitchlog/authz/product_catalog.py"
    )
    missing.unlink()
    _commit(repository, "remove positive fixture")

    with pytest.raises(checker.ContractError, match="正例 fixture.*missing"):
        checker.check_repository(repository, base_ref=base_ref)
