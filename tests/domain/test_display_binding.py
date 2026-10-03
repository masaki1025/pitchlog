"""表外既定の表示対応を schema 閉包と静的実測から検査する。"""

from __future__ import annotations

import ast
import copy
import importlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC = ROOT / "backend/src"
POLICY_PATH = ROOT / "backend/domain/display-binding.json"
MODEL_SCHEMA = ROOT / "backend/domain/model.schema.json"
VOCABULARY_SCHEMA = ROOT / "backend/domain/vocabulary.schema.json"
BOOT_SEAL = ROOT / "backend/domain/boot-seal.json"
REVIEW_TRIGGERS = ROOT / "backend/domain/review-triggers.json"
MATCHER_SOURCE = BACKEND_SRC / "pitchlog/domaincheck/display_binding.py"

sys.path.insert(0, str(BACKEND_SRC))
DISPLAY = importlib.import_module("pitchlog.domaincheck.display_binding")
COLLECTOR = importlib.import_module(
    "pitchlog.domaincheck.collect_display_paths"
)


def _read_json(path: Path) -> dict[str, Any]:
    """JSON object を読み込む。"""
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _write(root: Path, relative: str, content: str) -> None:
    """合成リポジトリへ UTF-8 ファイルを書く。"""
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_json(root: Path, relative: str, value: object) -> None:
    """合成リポジトリへ整形済み JSON を書く。"""
    _write(
        root,
        relative,
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
    )


@pytest.fixture
def synthetic_repository(tmp_path: Path) -> Path:
    """Schema 閉包と生成 formatter 呼出しを持つ合成リポジトリを返す。"""
    root = tmp_path / "repository"
    root.mkdir()
    for source, relative in (
        (MODEL_SCHEMA, "backend/domain/model.schema.json"),
        (VOCABULARY_SCHEMA, "backend/domain/vocabulary.schema.json"),
        (POLICY_PATH, "backend/domain/display-binding.json"),
        (BOOT_SEAL, "backend/domain/boot-seal.json"),
    ):
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    _write(
        root,
        "frontend/src/lib/generated/domainFormat.ts",
        "export function formatSynthetic(value: number): string {\n"
        "  return `value=${value}`\n"
        "}\n",
    )
    _write(
        root,
        "frontend/src/useDisplay.ts",
        "import { formatSynthetic } from './lib/generated/domainFormat'\n\n"
        "export const label = formatSynthetic(7)\n",
    )
    _write(root, "frontend/vite.config.ts", "export default { build: {} }\n")
    _write(
        root,
        "frontend/index.html",
        '<script type="module" src="/src/main.ts"></script>\n',
    )
    _write(root, "frontend/src/main.ts", "import './useDisplay'\n")
    return root


def _collect(root: Path) -> dict[str, Any]:
    """ステップ 12 の既存収集器で表示経路を実測する。"""
    result = COLLECTOR.collect_display_paths(
        root,
        root / "frontend/src",
        root / "backend/domain/model.schema.json",
        root / "backend/domain/vocabulary.schema.json",
    )
    assert isinstance(result, dict)
    return result


def _manifest_for(collection: dict[str, Any]) -> dict[str, object]:
    """Schema 閉包と実在呼出しに一致する表示対応宣言を返す。"""
    target_fields = collection["schemaClosure"]["targetFields"]
    calls = [
        call
        for call in collection["displayCalls"]
        if call["kind"] == "formatter-call"
    ]
    assert len(target_fields) == len(calls)
    return {
        "displayBindings": [
            {
                "displayItem": target,
                "callsite": call["path"],
                "formatter": call["symbol"],
                "provenance": "ADR-003 D-11 構成の完全性",
            }
            for target, call in zip(target_fields, calls, strict=True)
        ]
    }


def _write_manifest(root: Path, manifest: object) -> None:
    """CLI 用の合成マニフェストを書く。"""
    _write_json(root, "manifest.json", manifest)


def _run_module(
    module: str,
    root: Path,
    *arguments: str,
) -> subprocess.CompletedProcess[str]:
    """Domaincheck CLI を独立プロセスで実行する。"""
    return subprocess.run(
        [sys.executable, "-m", module, "--root", str(root), *arguments],
        cwd=ROOT,
        env={"PYTHONPATH": str(BACKEND_SRC), "PATH": os.environ["PATH"]},
        capture_output=True,
        text=True,
        check=False,
    )


def _run_display(root: Path) -> subprocess.CompletedProcess[str]:
    """表示対応 CLI を合成資産に対して実行する。"""
    return _run_module(
        "pitchlog.domaincheck.display_binding",
        root,
        "--manifest",
        "manifest.json",
    )


def _result(process: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    """CLI 標準出力を JSON object として返す。"""
    result = json.loads(process.stdout)
    assert isinstance(result, dict)
    return result


def test_policy_asset_is_closed_indented_and_newline_terminated() -> None:
    content = POLICY_PATH.read_text(encoding="utf-8")
    policy = _read_json(POLICY_PATH)

    assert set(policy) == {
        "schemaVersion",
        "authority",
        "sources",
        "targetDerivation",
        "bindingContract",
        "sealedMissingDeclaration",
    }
    assert content.endswith("\n")
    assert '\n  "schemaVersion"' in content


def test_matching_target_callsite_and_generated_formatter_pass(
    synthetic_repository: Path,
) -> None:
    collection = _collect(synthetic_repository)
    _write_manifest(synthetic_repository, _manifest_for(collection))

    process = _run_display(synthetic_repository)
    result = _result(process)

    assert process.returncode == 0, process.stderr
    assert result["status"] == "conforming"
    assert result["attempts"] == collection["attempts"]
    assert result["attempts"] > 0
    assert result["targetFields"] == collection["schemaClosure"]["targetFields"]
    assert result["bindingCount"] == len(result["targetFields"])


def test_missing_registration_is_an_exact_set_difference(
    synthetic_repository: Path,
) -> None:
    collection = _collect(synthetic_repository)
    manifest = _manifest_for(collection)
    manifest["displayBindings"] = []
    _write_manifest(synthetic_repository, manifest)

    process = _run_display(synthetic_repository)
    result = _result(process)

    assert process.returncode == 1
    assert result["status"] == "nonconforming"
    assert result["missingBindings"] == collection["schemaClosure"]["targetFields"]
    assert len(result["unregisteredCalls"]) == 1


def test_formatter_bypass_is_rejected_as_a_difference(
    synthetic_repository: Path,
) -> None:
    baseline = _collect(synthetic_repository)
    _write_manifest(synthetic_repository, _manifest_for(baseline))
    _write(
        synthetic_repository,
        "frontend/src/useDisplay.ts",
        "export const label = String(7)\n",
    )

    process = _run_display(synthetic_repository)
    result = _result(process)

    assert process.returncode == 1
    assert result["status"] == "nonconforming"
    assert len(result["nonFormatterCalls"]) == 1
    assert len(result["missingCalls"]) == 1


def test_formatter_outside_generated_area_is_rejected(
    synthetic_repository: Path,
) -> None:
    _write(
        synthetic_repository,
        "frontend/src/lib/manualFormat.ts",
        "export function formatSynthetic(value: number): string {\n"
        "  return `value=${value}`\n"
        "}\n",
    )
    _write(
        synthetic_repository,
        "frontend/src/useDisplay.ts",
        "import { formatSynthetic } from './lib/manualFormat'\n\n"
        "export const label = formatSynthetic(7)\n",
    )
    collection = _collect(synthetic_repository)
    target = collection["schemaClosure"]["targetFields"][0]
    _write_manifest(
        synthetic_repository,
        {
            "displayBindings": [
                {
                    "displayItem": target,
                    "callsite": "frontend/src/useDisplay.ts",
                    "formatter": "formatSynthetic",
                    "provenance": "ADR-003 D-11 構成の完全性",
                }
            ]
        },
    )

    process = _run_display(synthetic_repository)
    result = _result(process)

    assert process.returncode == 1
    assert len(result["invalidFormatters"]) == 1


def test_unregistered_formatter_call_is_rejected(
    synthetic_repository: Path,
) -> None:
    collection = _collect(synthetic_repository)
    _write_manifest(synthetic_repository, _manifest_for(collection))
    _write(
        synthetic_repository,
        "frontend/src/secondDisplay.ts",
        "import { formatSynthetic } from './lib/generated/domainFormat'\n\n"
        "export const second = formatSynthetic(8)\n",
    )

    process = _run_display(synthetic_repository)
    result = _result(process)

    assert process.returncode == 1
    assert len(result["unregisteredCalls"]) == 1


def test_schema_selector_addition_changes_target_closure_without_code_list(
    synthetic_repository: Path,
) -> None:
    before = _collect(synthetic_repository)
    model = _read_json(synthetic_repository / "backend/domain/model.schema.json")
    changed = copy.deepcopy(model)
    selector = copy.deepcopy(changed["x-pitchlog"]["targetFieldSelectors"][0])
    selector["id"] = "synthetic-added-visible-numeric-output"
    changed["x-pitchlog"]["targetFieldSelectors"].append(selector)
    _write_json(
        synthetic_repository,
        "backend/domain/model.schema.json",
        changed,
    )

    after = _collect(synthetic_repository)
    before_targets = set(before["schemaClosure"]["targetFields"])
    after_targets = set(after["schemaClosure"]["targetFields"])

    assert after_targets - before_targets == {selector["id"]}
    assert len(after_targets) == len(before_targets) + 1


def test_matcher_contains_no_literal_copy_of_derived_target_ids() -> None:
    collection = COLLECTOR.collect_display_paths(
        ROOT,
        ROOT / "frontend/src",
        MODEL_SCHEMA,
        VOCABULARY_SCHEMA,
    )
    tree = ast.parse(MATCHER_SOURCE.read_text(encoding="utf-8"))
    literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }

    assert collection["schemaClosure"]["complete"] is True
    assert collection["schemaClosure"]["targetFields"]
    assert not set(collection["schemaClosure"]["targetFields"]) & literals


def test_unresolved_display_path_is_fail_closed(
    synthetic_repository: Path,
) -> None:
    collection = _collect(synthetic_repository)
    _write_manifest(synthetic_repository, _manifest_for(collection))
    _write(
        synthetic_repository,
        "frontend/src/unresolved.ts",
        "const modulePath = './useDisplay'\nvoid import(modulePath)\n",
    )

    process = _run_display(synthetic_repository)
    result = _result(process)

    assert process.returncode == 2
    assert result["status"] == "indeterminate"
    assert result["attempts"] > 0


def test_missing_display_declaration_is_already_in_fixed_seal(
    synthetic_repository: Path,
) -> None:
    collection = _collect(synthetic_repository)
    manifest = _manifest_for(collection)
    policy = _read_json(POLICY_PATH)
    seal = _read_json(BOOT_SEAL)

    DISPLAY.inspect_display_bindings(collection, manifest, policy, seal)
    mutated = copy.deepcopy(seal)
    sealed_id = policy["sealedMissingDeclaration"]["elementId"]
    mutated["elements"] = [
        element for element in mutated["elements"] if element["id"] != sealed_id
    ]

    with pytest.raises(
        DISPLAY.DisplayBindingIndeterminate,
        match="封印要素",
    ):
        DISPLAY.inspect_display_bindings(collection, manifest, policy, mutated)


def test_trigger_six_record_is_bound_to_three_fail_closed_measurements(
    synthetic_repository: Path,
) -> None:
    collection = _collect(synthetic_repository)
    _write_manifest(synthetic_repository, _manifest_for(collection))
    _write(
        synthetic_repository,
        "frontend/src/main.ts",
        "const workerPath = './worker.ts'\n"
        "new Worker(workerPath)\n"
        "const modulePath = './useDisplay'\n"
        "void import(modulePath)\n",
    )
    _write(
        synthetic_repository,
        "backend/pyproject.toml",
        "[project]\n"
        'name = "synthetic-trigger-six"\n'
        "[tool.fastapi]\n"
        'entrypoint = "pitchlog.main:app"\n',
    )
    _write(
        synthetic_repository,
        "backend/src/pitchlog/__init__.py",
        '"""合成 package。"""\n',
    )
    _write(
        synthetic_repository,
        "backend/src/pitchlog/main.py",
        "from importlib import import_module\n\n"
        'module_name = "pitchlog.application"\n'
        "application = import_module(module_name)\n"
        "app = application.create_app()\n",
    )
    _write(
        synthetic_repository,
        "backend/src/pitchlog/application.py",
        "def create_app():\n    return object()\n",
    )
    _write_json(synthetic_repository, "backend-manifest.json", {})

    frontend = _run_module(
        "pitchlog.domaincheck.collect_entrypoints_fe",
        synthetic_repository,
    )
    backend = _run_module(
        "pitchlog.domaincheck.closure_be",
        synthetic_repository,
        "--manifest",
        "backend-manifest.json",
    )
    display = _run_display(synthetic_repository)
    measured = DISPLAY.FailClosedMeasurement(
        frontend.returncode,
        backend.returncode,
        display.returncode,
    )
    trigger = next(
        item
        for item in _read_json(REVIEW_TRIGGERS)["triggers"]
        if item["id"] == 6
    )

    assert measured.complete
    assert trigger["evaluation"] == {"fired": not measured.complete}
    assert trigger["evidenceLocation"] == "tests/domain/test_display_binding.py"


def test_trigger_thirteen_record_is_bound_to_actual_schema_closure() -> None:
    collection = _collect(ROOT)
    closure = collection["schemaClosure"]
    tree = ast.parse(MATCHER_SOURCE.read_text(encoding="utf-8"))
    literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    hardcoded = bool(set(closure["targetFields"]) & literals)
    complete = bool(closure["complete"] and closure["targetFields"] and not hardcoded)
    trigger = next(
        item
        for item in _read_json(REVIEW_TRIGGERS)["triggers"]
        if item["id"] == 13
    )

    assert complete
    assert trigger["evaluation"] == {"fired": not complete}
    assert trigger["evidenceLocation"] == "tests/domain/test_display_binding.py"
