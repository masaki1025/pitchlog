"""Frontend 実在入口の独立収集器をプロセス境界で検査する。"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from collections import deque
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC = ROOT / "backend/src"
COLLECTOR_SOURCE = (
    BACKEND_SRC / "pitchlog/domaincheck/collect_entrypoints_fe.py"
)
EXPECTED_SYNTHETIC_ATTEMPTS = 10


def _write(root: Path, relative: str, content: str) -> None:
    """合成 frontend のファイルを作る。"""
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@pytest.fixture
def synthetic_repository(tmp_path: Path) -> Path:
    """HTML・public・Worker・import graph を持つ合成リポジトリを返す。"""
    root = tmp_path / "repository"
    root.mkdir()
    _write(
        root,
        "frontend/vite.config.ts",
        "export default { build: { rollupOptions: {} } }\n",
    )
    _write(
        root,
        "frontend/index.html",
        '<script type="module" src="/src/main.ts"></script>\n',
    )
    _write(
        root,
        "frontend/admin.html",
        '<script type="module" src="/src/admin.ts"></script>\n',
    )
    _write(root, "frontend/public/manifest.webmanifest", "{}\n")
    _write(
        root,
        "frontend/src/main.ts",
        "import App from './App.vue'\n"
        "new Worker(new URL('./worker.ts', import.meta.url), { type: 'module' })\n"
        "void App\n",
    )
    _write(
        root,
        "frontend/src/App.vue",
        "<script setup lang=\"ts\">\nimport './feature'\n</script>\n",
    )
    _write(root, "frontend/src/feature.ts", "export const feature = true\n")
    _write(root, "frontend/src/admin.ts", "export const admin = true\n")
    _write(
        root,
        "frontend/src/worker.ts",
        "import './workerDependency'\npostMessage('ready')\n",
    )
    _write(
        root,
        "frontend/src/workerDependency.ts",
        "export const dependency = true\n",
    )
    return root


def _run_collector(root: Path) -> subprocess.CompletedProcess[str]:
    """Frontend 収集器を独立プロセスで実行する。"""
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pitchlog.domaincheck.collect_entrypoints_fe",
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


def _entries_by_path(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """収集した入口をパスで索引する。"""
    return {entry["path"]: entry for entry in result["entries"]}


def _shortest_path(
    result: dict[str, Any], source: str, target: str
) -> list[str] | None:
    """Import graph 上の最短到達経路を返す。"""
    outgoing: dict[str, set[str]] = {}
    for edge in result["importGraph"]:
        outgoing.setdefault(edge["from"], set()).add(edge["to"])
    queue: deque[list[str]] = deque([[source]])
    visited = {source}
    while queue:
        path = queue.popleft()
        if path[-1] == target:
            return path
        for next_path in sorted(outgoing.get(path[-1], set())):
            if next_path in visited:
                continue
            visited.add(next_path)
            queue.append([*path, next_path])
    return None


def test_synthetic_scan_attempt_population_is_fixed(
    synthetic_repository: Path,
) -> None:
    result_process = _run_collector(synthetic_repository)
    result = _result(result_process)

    assert result_process.returncode == 0, result_process.stderr
    assert result["attemptsByKind"] == {
        "graphFiles": 6,
        "htmlFiles": 2,
        "publicFiles": 1,
        "viteConfig": 1,
    }
    assert result["attempts"] == EXPECTED_SYNTHETIC_ATTEMPTS
    assert result["unresolved"] == []
    assert set(_entries_by_path(result)) == {
        "frontend/admin.html",
        "frontend/index.html",
        "frontend/public/manifest.webmanifest",
        "frontend/src/worker.ts",
    }


def test_explicit_vite_inputs_are_derived_from_config(
    synthetic_repository: Path,
) -> None:
    _write(
        synthetic_repository,
        "frontend/vite.config.ts",
        "export default {\n"
        "  build: {\n"
        "    rollupOptions: {\n"
        "      input: {\n"
        "        main: resolve(__dirname, 'index.html'),\n"
        "        admin: 'admin.html',\n"
        "      },\n"
        "    },\n"
        "  },\n"
        "}\n",
    )

    result_process = _run_collector(synthetic_repository)
    entries = _entries_by_path(_result(result_process))

    assert result_process.returncode == 0, result_process.stderr
    assert "vite-input" in entries["frontend/index.html"]["origins"]
    assert "vite-input" in entries["frontend/admin.html"]["origins"]
    assert "vite-default" not in entries["frontend/index.html"]["origins"]


def test_dynamic_worker_is_reported_as_indeterminate(
    synthetic_repository: Path,
) -> None:
    _write(
        synthetic_repository,
        "frontend/src/main.ts",
        "import App from './App.vue'\n"
        "const workerPath = './worker.ts'\n"
        "new Worker(workerPath)\n"
        "void App\n",
    )

    result_process = _run_collector(synthetic_repository)
    result = _result(result_process)

    assert result_process.returncode == 2
    assert "判定不能" in result_process.stderr
    assert result["unresolved"] == [
        {
            "path": "frontend/src/main.ts",
            "construct": "worker",
            "expression": "workerPath",
            "reason": "第 1 引数が静的 URL でない",
        }
    ]


def test_collector_has_no_declared_entrypoint_comparison_path() -> None:
    tree = ast.parse(COLLECTOR_SOURCE.read_text(encoding="utf-8"))
    string_literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }

    assert all("entrypoints" not in value for value in string_literals)
    assert all("backend/domain" not in value for value in string_literals)


def test_real_course_input_view_is_reachable_from_production_html() -> None:
    result_process = _run_collector(ROOT)
    result = _result(result_process)
    path = _shortest_path(
        result,
        "frontend/index.html",
        "frontend/src/lib/courseInputView.ts",
    )

    assert result_process.returncode == 0, result_process.stderr
    assert path is not None
    assert path[0] == "frontend/index.html"
    assert path[-1] == "frontend/src/lib/courseInputView.ts"
