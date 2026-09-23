"""ドメイン計算パッケージの依存・型検査・配布境界を検証する。"""

from __future__ import annotations

import ast
import importlib
import os
import shutil
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
BACKEND_SOURCE = BACKEND_ROOT / "src"
BACKEND_PROJECT = BACKEND_ROOT / "pyproject.toml"
BACKEND_LOCK = BACKEND_ROOT / "uv.lock"
COVERAGE_PATH = BACKEND_ROOT / ".coverage"
DOMAIN_ASSETS = BACKEND_ROOT / "domain"
PACKAGE_NAMES = ("domaincheck", "domaingen", "domainmut")


def _project() -> dict[str, object]:
    """backend の pyproject を object として返す。"""
    return tomllib.loads(BACKEND_PROJECT.read_text(encoding="utf-8"))


def _uv_environment(cache: Path) -> dict[str, str]:
    """書き込み可能な uv cache を持つ子プロセス環境を返す。

    Args:
        cache: このテスト実行だけが使う uv cache。

    Returns:
        uv の進捗表示を抑えた環境変数。
    """
    cache.mkdir(parents=True, exist_ok=True)
    return {
        **os.environ,
        "UV_CACHE_DIR": str(cache),
        "UV_NO_PROGRESS": "1",
    }


def _run(
    arguments: list[str],
    *,
    cwd: Path,
    environment: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    """子プロセスを実行し、失敗時に標準出力も含めて報告する。

    Args:
        arguments: 実行ファイルを含む引数列。
        cwd: 実行ディレクトリ。
        environment: 子プロセスの環境変数。

    Returns:
        終了済みプロセス。
    """
    result = subprocess.run(
        arguments,
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"command={arguments!r}\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    return result


def _git(*arguments: str) -> subprocess.CompletedProcess[str]:
    """リポジトリに対する読み取り専用 Git コマンドを実行する。"""
    return subprocess.run(
        ["git", *arguments],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _asset_literals(package: str) -> tuple[str, ...]:
    """パッケージに記述されたルート相対の規範 JSON path を返す。

    Args:
        package: ``pitchlog`` 直下のパッケージ名。

    Returns:
        ``backend/domain`` から始まる文字列リテラル。
    """
    values: set[str] = set()
    for source in (BACKEND_SOURCE / "pitchlog" / package).rglob("*.py"):
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        values.update(
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value.startswith("backend/domain/")
            and node.value.endswith(".json")
        )
    return tuple(sorted(values))


def _local_build_python() -> Path:
    """ネットワーク不要の wheel build backend を持つ Python を返す。"""
    candidates = {
        Path(sys.executable),
        Path(sys.base_prefix) / "bin" / "python3",
        Path("/usr/bin/python3"),
    }
    for candidate in candidates:
        if not candidate.is_file():
            continue
        result = subprocess.run(
            [str(candidate), "-c", "import setuptools, wheel"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return candidate
    raise AssertionError("setuptools と wheel を持つローカル Python がない")


def test_ty_source_include_covers_all_three_python_packages() -> None:
    """既存の src 包含が新設三パッケージをすべて型検査対象にする。"""
    project = _project()
    tool = project["tool"]
    assert isinstance(tool, dict)
    ty = tool["ty"]
    assert isinstance(ty, dict)
    source = ty["src"]
    assert isinstance(source, dict)

    assert source["include"] == ["src", "tests"]
    for package in PACKAGE_NAMES:
        package_root = BACKEND_SOURCE / "pitchlog" / package
        assert package_root.is_dir()
        assert any(package_root.rglob("*.py"))
        assert package_root.is_relative_to(BACKEND_ROOT / "src")

    assert DOMAIN_ASSETS.is_dir()
    assert all(path.suffix == ".json" for path in DOMAIN_ASSETS.iterdir())


def test_locked_sync_and_ty_check_actually_succeed(tmp_path: Path) -> None:
    """lock を書き換えずに同期し、既存対象への ty 実行を完走する。"""
    project_before = BACKEND_PROJECT.read_bytes()
    lock_before = BACKEND_LOCK.read_bytes()
    environment = _uv_environment(tmp_path / "uv-cache")

    _run(["uv", "sync", "--locked"], cwd=BACKEND_ROOT, environment=environment)
    _run(["uv", "run", "ty", "check"], cwd=BACKEND_ROOT, environment=environment)

    assert BACKEND_PROJECT.read_bytes() == project_before
    assert BACKEND_LOCK.read_bytes() == lock_before


def test_generated_coverage_stays_untracked_and_ignored(tmp_path: Path) -> None:
    """実coverage生成後も backend/.coverage が index 外に留まる。"""
    indexed = _git("ls-files", "--error-unmatch", "--", "backend/.coverage")
    assert indexed.returncode != 0

    previous = COVERAGE_PATH.read_bytes() if COVERAGE_PATH.exists() else None
    environment = _uv_environment(tmp_path / "uv-cache")
    environment["COVERAGE_FILE"] = str(COVERAGE_PATH)
    try:
        _run(
            [
                "uv",
                "run",
                "pytest",
                "tests/test_package.py",
                "--cov=pitchlog",
                "--cov-report=",
            ],
            cwd=BACKEND_ROOT,
            environment=environment,
        )
        assert COVERAGE_PATH.is_file()

        ignored = _git(
            "ls-files",
            "--others",
            "--ignored",
            "--exclude-standard",
            "--",
            "backend/.coverage",
        )
        assert ignored.returncode == 0
        assert ignored.stdout.splitlines() == ["backend/.coverage"]
        assert _git(
            "status",
            "--porcelain",
            "--untracked-files=all",
            "--",
            "backend/.coverage",
        ).stdout == ""
    finally:
        if previous is None:
            COVERAGE_PATH.unlink(missing_ok=True)
        else:
            COVERAGE_PATH.write_bytes(previous)


def test_normative_assets_are_read_from_repository_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """三パッケージが package data でなくルート相対 path を使う。"""
    project = _project()
    tool = project["tool"]
    assert isinstance(tool, dict)
    setuptools = tool["setuptools"]
    assert isinstance(setuptools, dict)
    assert "package-data" not in setuptools
    assert not (BACKEND_ROOT / "MANIFEST.in").exists()

    for package in PACKAGE_NAMES:
        literals = _asset_literals(package)
        assert literals, f"{package} にルート相対の規範資産 path がない"
        assert all(not Path(value).is_absolute() for value in literals)

    sources = "\n".join(
        path.read_text(encoding="utf-8")
        for package in PACKAGE_NAMES
        for path in (BACKEND_SOURCE / "pitchlog" / package).rglob("*.py")
    )
    assert "importlib.resources" not in sources
    assert "pkgutil.get_data" not in sources

    monkeypatch.syspath_prepend(str(BACKEND_SOURCE))
    monkeypatch.chdir(tmp_path)
    authz_ddl = importlib.import_module("pitchlog.authz.ddl")
    clauses = importlib.import_module("pitchlog.domaincheck.boot.clauses")
    stopgate = importlib.import_module("pitchlog.domaincheck.stopgate")
    trigger_completion = importlib.import_module(
        "pitchlog.domaincheck.trigger_completion"
    )
    core = importlib.import_module("pitchlog.domaingen.core")
    cost_record = importlib.import_module("pitchlog.domainmut.cost_record")

    assert (REPOSITORY_ROOT / authz_ddl.DDL_ELEMENTS_PATH).is_file()
    assert clauses.load_and_validate_registry(REPOSITORY_ROOT)
    assert stopgate._default_registry_path() == (
        REPOSITORY_ROOT / "backend/domain/review-triggers.json"
    )
    assert trigger_completion._default_registry_path() == (
        REPOSITORY_ROOT / "backend/domain/review-triggers.json"
    )
    model_path = core._resolve_path(
        REPOSITORY_ROOT,
        Path("backend/domain/model.schema.json"),
    )
    assert core._load_schema(model_path, "model")
    assert cost_record._schemas(REPOSITORY_ROOT).documents()


def test_built_wheel_contains_packages_but_not_normative_json(
    tmp_path: Path,
) -> None:
    """実wheelの内容を列挙し、規範JSONを同梱しないことを固定する。"""
    build_root = tmp_path / "backend"
    build_root.mkdir()
    shutil.copy2(BACKEND_PROJECT, build_root / "pyproject.toml")
    shutil.copytree(BACKEND_SOURCE, build_root / "src")
    output = tmp_path / "wheel"
    environment = _uv_environment(tmp_path / "uv-cache")
    _run(
        [
            "uv",
            "build",
            "--wheel",
            "--no-build-isolation",
            "--python",
            str(_local_build_python()),
            "--out-dir",
            str(output),
        ],
        cwd=build_root,
        environment=environment,
    )
    wheels = list(output.glob("*.whl"))
    assert len(wheels) == 1

    with zipfile.ZipFile(wheels[0]) as archive:
        members = set(archive.namelist())
    for package in PACKAGE_NAMES:
        prefix = f"pitchlog/{package}/"
        assert any(member.startswith(prefix) and member.endswith(".py") for member in members)

    asset_names = {path.name for path in DOMAIN_ASSETS.glob("*.json")}
    packaged_json = {Path(member).name for member in members if member.endswith(".json")}
    assert packaged_json.isdisjoint(asset_names)
    assert all("backend/domain/" not in member for member in members)
