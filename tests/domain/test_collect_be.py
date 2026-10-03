"""Backend 実在入口の独立収集器をプロセス境界で検査する。"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC = ROOT / "backend/src"
COLLECTOR_SOURCE = BACKEND_SRC / "pitchlog/domaincheck/collect_entrypoints_be.py"
EXPECTED_SYNTHETIC_ATTEMPTS = 10


def _write(root: Path, relative: str, content: str) -> None:
    """合成 backend のファイルを作る。"""
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@pytest.fixture
def synthetic_repository(tmp_path: Path) -> Path:
    """静的・動的 import とルータを持つ合成リポジトリを返す。"""
    root = tmp_path / "repository"
    root.mkdir()
    _write(
        root,
        "backend/pyproject.toml",
        "[project]\n"
        'name = "synthetic"\n'
        "[project.scripts]\n"
        'synthetic = "pitchlog.cli:main"\n'
        "[tool.fastapi]\n"
        'entrypoint = "pitchlog.main:app"\n',
    )
    _write(root, "backend/src/pitchlog/__init__.py", '"""合成 package。"""\n')
    _write(
        root,
        "backend/src/pitchlog/main.py",
        "from pitchlog.app import create_app\n\napp = create_app()\n",
    )
    _write(
        root,
        "backend/src/pitchlog/app.py",
        "from pitchlog.routers import alpha, beta\n\n"
        "ROUTERS = (alpha.router, beta.router)\n\n"
        "def create_app():\n"
        "    return tuple(ROUTERS)\n",
    )
    _write(root, "backend/src/pitchlog/routers/alpha.py", "router = 'alpha'\n")
    _write(root, "backend/src/pitchlog/routers/beta.py", "router = 'beta'\n")
    _write(
        root,
        "backend/src/pitchlog/cli.py",
        "from pitchlog import dynamic, metadata_probe\n\n"
        "def main():\n"
        "    return dynamic.PLUGIN, metadata_probe.VERSION\n",
    )
    _write(
        root,
        "backend/src/pitchlog/dynamic.py",
        "from importlib import import_module\n\n"
        'PLUGIN = import_module("pitchlog.plugin")\n'
        'HANDLER = getattr(PLUGIN, "run")\n',
    )
    _write(root, "backend/src/pitchlog/plugin.py", "def run():\n    return True\n")
    _write(
        root,
        "backend/src/pitchlog/metadata_probe.py",
        "from importlib import metadata\n\n"
        'VERSION = metadata.version("synthetic")\n',
    )
    return root


def _run_collector(root: Path) -> subprocess.CompletedProcess[str]:
    """Backend 収集器を独立プロセスで実行する。"""
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pitchlog.domaincheck.collect_entrypoints_be",
            "--root",
            str(root),
        ],
        cwd=ROOT,
        env={"PYTHONPATH": str(BACKEND_SRC), "PATH": os.environ["PATH"]},
        capture_output=True,
        text=True,
        check=False,
    )


def _result(process: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    """収集器の標準出力を JSON object として返す。"""
    value = json.loads(process.stdout)
    assert isinstance(value, dict)
    return value


def _reachable_names(result: dict[str, Any]) -> set[str]:
    """到達可能モジュール名の集合を返す。"""
    return {row["module"] for row in result["reachableModules"]}


def test_synthetic_scan_attempt_population_is_fixed(
    synthetic_repository: Path,
) -> None:
    process = _run_collector(synthetic_repository)
    result = _result(process)

    assert process.returncode == 0, process.stderr
    assert result["attemptsByKind"] == {
        "projectMetadata": 1,
        "pythonFiles": 9,
    }
    assert result["attempts"] == EXPECTED_SYNTHETIC_ATTEMPTS
    assert result["unresolved"] == []


def test_known_synthetic_entries_and_routers_are_collected(
    synthetic_repository: Path,
) -> None:
    process = _run_collector(synthetic_repository)
    result = _result(process)
    entries = {(row["kind"], row["module"]) for row in result["entries"]}
    routers = {
        (row["reference"], row["module"], row["attribute"])
        for row in result["routers"]
    }

    assert process.returncode == 0, process.stderr
    assert entries == {
        ("application", "pitchlog.main"),
        ("project-script", "pitchlog.cli"),
    }
    assert routers == {
        ("alpha.router", "pitchlog.routers.alpha", "router"),
        ("beta.router", "pitchlog.routers.beta", "router"),
    }
    assert {"pitchlog.main", "pitchlog.app", "pitchlog.cli"} <= _reachable_names(
        result
    )


def test_import_graph_is_derived_from_changed_source(
    synthetic_repository: Path,
) -> None:
    _write(
        synthetic_repository,
        "backend/src/pitchlog/extra.py",
        "VALUE = 'derived'\n",
    )
    _write(
        synthetic_repository,
        "backend/src/pitchlog/main.py",
        "from pitchlog.app import create_app\n"
        "from pitchlog import extra\n\n"
        "app = create_app()\n"
        "value = extra.VALUE\n",
    )

    process = _run_collector(synthetic_repository)
    result = _result(process)

    assert process.returncode == 0, process.stderr
    assert "pitchlog.extra" in _reachable_names(result)
    assert {
        "from": "pitchlog.main",
        "to": "pitchlog.extra",
        "kind": "import",
    } in result["importGraph"]


def test_dynamic_import_target_is_reported_as_indeterminate(
    synthetic_repository: Path,
) -> None:
    _write(
        synthetic_repository,
        "backend/src/pitchlog/dynamic.py",
        "from importlib import import_module\n\n"
        'module_name = "pitchlog.plugin"\n'
        "PLUGIN = import_module(module_name)\n"
        'HANDLER = getattr(PLUGIN, "run")\n',
    )

    process = _run_collector(synthetic_repository)
    result = _result(process)

    assert process.returncode == 2
    assert "判定不能" in process.stderr
    assert result["unresolved"] == [
        {
            "module": "pitchlog.dynamic",
            "path": "backend/src/pitchlog/dynamic.py",
            "construct": "importlib.import_module",
            "expression": "import_module(module_name)",
            "reachable": True,
            "reason": "第 1 引数が静的文字列でない",
        }
    ]


def test_dynamic_getattr_target_is_reported_as_indeterminate(
    synthetic_repository: Path,
) -> None:
    _write(
        synthetic_repository,
        "backend/src/pitchlog/dynamic.py",
        "from importlib import import_module\n\n"
        'PLUGIN = import_module("pitchlog.plugin")\n'
        'attribute_name = "run"\n'
        "HANDLER = getattr(PLUGIN, attribute_name)\n",
    )

    process = _run_collector(synthetic_repository)
    result = _result(process)

    assert process.returncode == 2
    assert result["unresolved"] == [
        {
            "module": "pitchlog.dynamic",
            "path": "backend/src/pitchlog/dynamic.py",
            "construct": "getattr",
            "expression": "getattr(PLUGIN, attribute_name)",
            "reachable": True,
            "reason": "属性名が静的文字列でない",
        }
    ]


def test_constant_dynamic_targets_are_resolved(synthetic_repository: Path) -> None:
    process = _run_collector(synthetic_repository)
    result = _result(process)
    resolved = {
        (row["construct"], row["target"])
        for row in result["resolvedDynamic"]
    }

    assert process.returncode == 0, process.stderr
    assert ("importlib.import_module", "pitchlog.plugin") in resolved
    assert ("getattr", "run") in resolved
    assert any(
        construct == "importlib.metadata.version"
        and "synthetic" in target
        for construct, target in resolved
    )
    assert "pitchlog.plugin" in _reachable_names(result)


def test_collector_has_no_declared_entrypoint_comparison_path() -> None:
    tree = ast.parse(COLLECTOR_SOURCE.read_text(encoding="utf-8"))
    string_literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }

    assert all("entrypoints" not in value for value in string_literals)
    assert all("manifest.json" not in value for value in string_literals)
    assert all("backend/domain" not in value for value in string_literals)


def _declared_router_references(path: Path) -> set[str]:
    """実ファイルの `ROUTERS` から参照式を独立導出する。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for statement in tree.body:
        value: ast.expr | None = None
        if isinstance(statement, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "ROUTERS"
            for target in statement.targets
        ):
            value = statement.value
        elif (
            isinstance(statement, ast.AnnAssign)
            and isinstance(statement.target, ast.Name)
            and statement.target.id == "ROUTERS"
        ):
            value = statement.value
        if isinstance(value, (ast.Tuple, ast.List)):
            return {ast.unparse(element) for element in value.elts}
    return set()


def test_real_main_reaches_every_statically_declared_router() -> None:
    process = _run_collector(ROOT)
    result = _result(process)
    expected_references = _declared_router_references(
        BACKEND_SRC / "pitchlog/api/app.py"
    )
    router_rows = [
        row
        for row in result["routers"]
        if row["ownerModule"] == "pitchlog.api.app"
    ]
    reachable = _reachable_names(result)

    assert expected_references
    assert {row["reference"] for row in router_rows} == expected_references
    assert {"pitchlog.main", "pitchlog.api.app"} <= reachable
    assert all(row["module"] in reachable for row in router_rows)
    expected_exit = 2 if result["unresolved"] else 0
    assert process.returncode == expected_exit
