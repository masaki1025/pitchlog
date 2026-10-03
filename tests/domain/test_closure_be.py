"""Backend 閉域を独立収集・集合差・実行時拒否の各境界で検査する。"""

from __future__ import annotations

import ast
import copy
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC = ROOT / "backend/src"
CLOSURE_SOURCE = BACKEND_SRC / "pitchlog/domaincheck/closure_be.py"

sys.path.insert(0, str(BACKEND_SRC))
CLOSURE = importlib.import_module("pitchlog.domaincheck.closure_be")
COLLECTOR = importlib.import_module(
    "pitchlog.domaincheck.collect_entrypoints_be"
)


def _write(root: Path, relative: str, content: str) -> None:
    """合成リポジトリへ UTF-8 ファイルを書く。"""
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@pytest.fixture
def synthetic_repository(tmp_path: Path) -> Path:
    """静的入口と import graph を持つ合成 backend を返す。"""
    root = tmp_path / "repository"
    root.mkdir()
    _write(
        root,
        "backend/pyproject.toml",
        "[project]\n"
        'name = "synthetic-closure"\n'
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
        "from pitchlog.routers import alpha\n\n"
        "ROUTERS = (alpha.router,)\n\n"
        "def create_app():\n"
        "    return tuple(ROUTERS)\n",
    )
    _write(root, "backend/src/pitchlog/routers/__init__.py", '"""ルータ群。"""\n')
    _write(root, "backend/src/pitchlog/routers/alpha.py", "router = 'alpha'\n")
    return root


def _collect(root: Path) -> dict[str, Any]:
    """ステップ 11 の既存収集器で合成 backend を実測する。"""
    result = COLLECTOR.collect_backend_entries(
        root,
        root / "backend/src",
        root / "backend/pyproject.toml",
    )
    assert isinstance(result, dict)
    return result


def _module_path(module: str) -> str:
    """Dotted module を schema のリポジトリ相対パスへ変換する。"""
    return f"backend/src/{module.replace('.', '/')}.py"


def _manifest_for(collection: dict[str, Any]) -> dict[str, object]:
    """実測入口と同じ集合を宣言する合成マニフェストを返す。"""
    observed = [*collection["entries"], *collection["routers"]]
    entrypoints = []
    for index, row in enumerate(observed):
        entrypoints.append(
            {
                "entrypointId": f"synthetic-entry-{index}",
                "module": _module_path(row["module"]),
                "symbol": row["attribute"],
                "adapter": f"synthetic/adapters/entry-{index}.py",
            }
        )
    return {
        "calculations": [
            {
                "calculation": "synthetic-closure",
                "entrypoints": entrypoints,
            }
        ]
    }


def _write_manifest(root: Path, manifest: object) -> None:
    """CLI が読む合成マニフェストを書く。"""
    _write(
        root,
        "manifest.json",
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    )


def _run_closure(root: Path) -> subprocess.CompletedProcess[str]:
    """Backend 閉域 CLI を独立プロセスで実行する。"""
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pitchlog.domaincheck.closure_be",
            "--root",
            str(root),
            "--manifest",
            "manifest.json",
        ],
        cwd=ROOT,
        env={"PYTHONPATH": str(BACKEND_SRC), "PATH": os.environ["PATH"]},
        capture_output=True,
        text=True,
        check=False,
    )


def _result(process: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    """CLI 標準出力を JSON object として返す。"""
    result = json.loads(process.stdout)
    assert isinstance(result, dict)
    return result


def test_matching_declarations_pass_with_nonempty_measured_scan(
    synthetic_repository: Path,
) -> None:
    collection = _collect(synthetic_repository)
    _write_manifest(synthetic_repository, _manifest_for(collection))

    process = _run_closure(synthetic_repository)
    result = _result(process)

    assert process.returncode == 0, process.stderr
    assert result["status"] == "conforming"
    assert result["attempts"] == collection["attempts"]
    assert result["attempts"] > 0
    assert result["observedCount"] == result["declaredCount"]
    assert result["observedCount"] > 0
    assert result["importGraphEdgeCount"] == len(collection["importGraph"])
    assert result["importGraphEdgeCount"] > 0


def test_one_undeclared_actual_entry_is_rejected(
    synthetic_repository: Path,
) -> None:
    collection = _collect(synthetic_repository)
    manifest = _manifest_for(collection)
    calculations = manifest["calculations"]
    assert isinstance(calculations, list)
    calculation = calculations[0]
    assert isinstance(calculation, dict)
    entrypoints = calculation["entrypoints"]
    assert isinstance(entrypoints, list)
    entrypoints.pop()
    _write_manifest(synthetic_repository, manifest)

    process = _run_closure(synthetic_repository)
    result = _result(process)

    assert process.returncode == 1
    assert result["status"] == "nonconforming"
    assert len(result["undeclaredEntrypoints"]) == 1
    assert result["missingActualEntrypoints"] == []


def test_one_declared_but_absent_entry_is_rejected(
    synthetic_repository: Path,
) -> None:
    collection = _collect(synthetic_repository)
    manifest = _manifest_for(collection)
    calculations = manifest["calculations"]
    assert isinstance(calculations, list)
    calculation = calculations[0]
    assert isinstance(calculation, dict)
    entrypoints = calculation["entrypoints"]
    assert isinstance(entrypoints, list)
    entrypoints.append(
        {
            "entrypointId": "absent-entry",
            "module": "backend/src/pitchlog/absent.py",
            "symbol": "run",
            "adapter": "synthetic/adapters/absent.py",
        }
    )
    _write_manifest(synthetic_repository, manifest)

    process = _run_closure(synthetic_repository)
    result = _result(process)

    assert process.returncode == 1
    assert result["status"] == "nonconforming"
    assert result["undeclaredEntrypoints"] == []
    assert result["missingActualEntrypoints"] == ["pitchlog.absent:run"]


def test_unresolved_dynamic_import_is_fail_closed(
    synthetic_repository: Path,
) -> None:
    baseline = _collect(synthetic_repository)
    _write_manifest(synthetic_repository, _manifest_for(baseline))
    _write(
        synthetic_repository,
        "backend/src/pitchlog/main.py",
        "from importlib import import_module\n\n"
        'module_name = "pitchlog.app"\n'
        "application = import_module(module_name)\n"
        "app = application.create_app()\n",
    )

    process = _run_closure(synthetic_repository)
    result = _result(process)

    assert process.returncode == 2
    assert result["status"] == "indeterminate"
    assert result["attempts"] > 0
    assert "静的に解決できない入口" in result["reasons"][0]


@pytest.mark.parametrize(
    ("mechanism", "expected_fragment"),
    [
        ("importlib", "importlib.import_module"),
        ("getattr", "|getattr|"),
        ("entry-point", "project-entry-point"),
    ],
)
def test_resolved_dynamic_loading_mechanisms_are_rejected(
    synthetic_repository: Path,
    mechanism: str,
    expected_fragment: str,
) -> None:
    if mechanism == "importlib":
        _write(
            synthetic_repository,
            "backend/src/pitchlog/main.py",
            "from importlib import import_module\n\n"
            'application = import_module("pitchlog.app")\n'
            "app = application.create_app()\n",
        )
    elif mechanism == "getattr":
        _write(
            synthetic_repository,
            "backend/src/pitchlog/main.py",
            "from pitchlog import app as application\n\n"
            'factory = getattr(application, "create_app")\n'
            "app = factory()\n",
        )
    else:
        _write(
            synthetic_repository,
            "backend/pyproject.toml",
            "[project]\n"
            'name = "synthetic-closure"\n'
            "[project.entry-points.synthetic]\n"
            'plugin = "pitchlog.plugin:run"\n'
            "[tool.fastapi]\n"
            'entrypoint = "pitchlog.main:app"\n',
        )
        _write(
            synthetic_repository,
            "backend/src/pitchlog/plugin.py",
            "def run():\n    return True\n",
        )

    collection = _collect(synthetic_repository)
    _write_manifest(synthetic_repository, _manifest_for(collection))
    process = _run_closure(synthetic_repository)
    result = _result(process)

    assert process.returncode == 1
    assert result["status"] == "nonconforming"
    assert any(
        expected_fragment in violation
        for violation in result["forbiddenDynamicLoads"]
    )


def test_runtime_gate_rejects_before_undeclared_callable_runs(
    synthetic_repository: Path,
) -> None:
    collection = _collect(synthetic_repository)
    manifest = _manifest_for(collection)
    gate = CLOSURE.runtime_gate(manifest, collection["sourceRoot"])
    allowed = next(iter(gate.allowed))
    calls: list[str] = []

    assert gate.invoke(
        allowed.module,
        allowed.symbol,
        lambda: calls.append("allowed") or "executed",
    ) == "executed"
    with pytest.raises(CLOSURE.UndeclaredEntrypointError, match="宣言外の入口"):
        gate.invoke(
            "pitchlog.undeclared",
            "run",
            lambda: calls.append("undeclared"),
        )

    assert calls == ["allowed"]


def test_zero_scan_cannot_be_reported_as_conforming(
    synthetic_repository: Path,
) -> None:
    collection = copy.deepcopy(_collect(synthetic_repository))
    collection["attempts"] = 0
    collection["attemptsByKind"] = {
        key: 0 for key in collection["attemptsByKind"]
    }

    with pytest.raises(CLOSURE.BackendClosureIndeterminate, match="正の整数"):
        CLOSURE.inspect_backend_closure(
            collection,
            _manifest_for(collection),
        )


def test_existing_collector_is_the_only_import_graph_collector() -> None:
    tree = ast.parse(CLOSURE_SOURCE.read_text(encoding="utf-8"))
    collector_imports = [
        node
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
        and node.module == "pitchlog.domaincheck.collect_entrypoints_be"
    ]

    assert len(collector_imports) == 1
    assert any(
        alias.name == "collect_backend_entries"
        for alias in collector_imports[0].names
    )
    assert not any(isinstance(node, (ast.Import, ast.ImportFrom)) and any(
        alias.name == "ast" for alias in node.names
    ) for node in tree.body)
