"""表示経路の静的解析器をプロセス境界で検査する。"""

from __future__ import annotations

import ast
import copy
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC = ROOT / "backend/src"
COLLECTOR_SOURCE = BACKEND_SRC / "pitchlog/domaincheck/collect_display_paths.py"
EXPECTED_SYNTHETIC_ATTEMPTS = 4


def _write(root: Path, relative: str, content: str) -> None:
    """合成リポジトリのファイルを作る。"""
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_json(root: Path, relative: str, value: object) -> None:
    """合成 JSON 資産を作る。"""
    _write(
        root,
        relative,
        f"{json.dumps(value, ensure_ascii=False, indent=2)}\n",
    )


def _kind_schema(kind: str) -> dict[str, object]:
    """Kind だけを持つ合成 object schema を返す。"""
    return {
        "type": "object",
        "properties": {"kind": {"const": kind}},
    }


def _manifest_schema(fields: list[str]) -> dict[str, Any]:
    """有限の表示項目を持つ合成マニフェスト schema を返す。"""
    return {
        "type": "object",
        "properties": {
            "displayBindings": {
                "type": "array",
                "items": {"$ref": "#/$defs/DisplayBinding"},
            }
        },
        "$defs": {
            "DisplayBinding": {
                "type": "object",
                "properties": {"displayItem": {"enum": fields}},
            }
        },
    }


def _vocabulary_schema() -> dict[str, object]:
    """閉じた数値・表示型を持つ合成語彙 schema を返す。"""
    return {
        "$defs": {
            "NumericValue": {
                "oneOf": [{"$ref": "#/$defs/IntegerValue"}]
            },
            "IntegerValue": _kind_schema("integer"),
            "NumericPrimitive": {
                "oneOf": [{"$ref": "#/$defs/FixedDecimal"}]
            },
            "FixedDecimal": _kind_schema("fixed-decimal"),
            "DisplayAtomSource": {
                "oneOf": [
                    {"$ref": "#/$defs/NumericPrimitiveOutput"},
                    {"$ref": "#/$defs/ResolvedName"},
                ]
            },
            "NumericPrimitiveOutput": _kind_schema(
                "numeric-primitive-output"
            ),
            "ResolvedName": {
                "type": "object",
                "additionalProperties": False,
                "required": ["kind", "vocabularyId", "entityId"],
                "properties": {
                    "kind": {"const": "resolved-name"},
                    "vocabularyId": {"type": "string"},
                    "entityId": {"type": "string"},
                },
            },
        }
    }


@pytest.fixture
def synthetic_repository(tmp_path: Path) -> Path:
    """閉じた schema と既知の formatter 呼出しを持つ合成ツリーを返す。"""
    root = tmp_path / "repository"
    root.mkdir()
    _write_json(
        root,
        "schemas/manifest.json",
        _manifest_schema(["calculation.visible.alpha"]),
    )
    _write_json(root, "schemas/vocabulary.json", _vocabulary_schema())
    _write(
        root,
        "frontend/src/lib/format.ts",
        "export function formatValue(value: number): string {\n"
        "  return `value=${value}`\n"
        "}\n",
    )
    _write(
        root,
        "frontend/src/Score.vue",
        '<script setup lang="ts">\n'
        "import { formatValue } from './lib/format'\n"
        "const label = formatValue(7)\n"
        "</script>\n"
        "<template><output>{{ label }}</output></template>\n",
    )
    return root


def _run_collector(root: Path) -> subprocess.CompletedProcess[str]:
    """表示経路収集器を独立プロセスで実行する。"""
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pitchlog.domaincheck.collect_display_paths",
            "--root",
            str(root),
            "--manifest-schema",
            "schemas/manifest.json",
            "--vocabulary-schema",
            "schemas/vocabulary.json",
        ],
        cwd=ROOT,
        env={"PYTHONPATH": str(BACKEND_SRC), "PATH": os.environ["PATH"]},
        capture_output=True,
        text=True,
        check=False,
    )


def _run_real_collector() -> subprocess.CompletedProcess[str]:
    """実リポジトリの表示経路収集器を独立プロセスで実行する。"""
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pitchlog.domaincheck.collect_display_paths",
            "--root",
            str(ROOT),
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


def test_synthetic_scan_population_and_positive_path_are_fixed(
    synthetic_repository: Path,
) -> None:
    process = _run_collector(synthetic_repository)
    result = _result(process)

    assert process.returncode == 0, process.stderr
    assert result["attemptsByKind"] == {
        "frontendFiles": 2,
        "schemaDocuments": 2,
    }
    assert result["attempts"] == EXPECTED_SYNTHETIC_ATTEMPTS
    assert result["schemaClosure"]["targetFields"] == [
        "calculation.visible.alpha"
    ]
    assert result["unresolved"] == []
    assert {
        "path": "frontend/src/Score.vue",
        "kind": "formatter-call",
        "expression": "formatValue(",
        "occurrence": 1,
        "symbol": "formatValue",
        "formatter": "frontend/src/lib/format.ts",
    } in result["displayCalls"]


def test_adding_one_schema_field_adds_one_target(
    synthetic_repository: Path,
) -> None:
    before_process = _run_collector(synthetic_repository)
    before = _result(before_process)["schemaClosure"]["targetFields"]
    schema_path = synthetic_repository / "schemas/manifest.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    changed = copy.deepcopy(schema)
    changed["$defs"]["DisplayBinding"]["properties"]["displayItem"][
        "enum"
    ].append("calculation.visible.beta")
    _write_json(synthetic_repository, "schemas/manifest.json", changed)

    after_process = _run_collector(synthetic_repository)
    after = _result(after_process)["schemaClosure"]["targetFields"]

    assert before_process.returncode == 0, before_process.stderr
    assert after_process.returncode == 0, after_process.stderr
    assert set(after) - set(before) == {"calculation.visible.beta"}
    assert len(after) == len(before) + 1


def test_open_display_item_schema_is_indeterminate(
    synthetic_repository: Path,
) -> None:
    schema = _manifest_schema(["unused"])
    schema["$defs"]["DisplayBinding"]["properties"]["displayItem"] = {
        "type": "string",
        "pattern": "^[A-Za-z.]+$",
    }
    _write_json(synthetic_repository, "schemas/manifest.json", schema)

    process = _run_collector(synthetic_repository)
    result = _result(process)

    assert process.returncode == 2
    assert result["schemaClosure"]["targetFields"] == []
    assert result["schemaClosure"]["complete"] is False
    assert result["unresolved"] == [
        {
            "path": "schemas/manifest.json",
            "construct": "schema-closure",
            "expression": "#/properties/displayBindings/items/displayItem",
            "reason": "表示項目が有限の const / enum 閉包でない",
        }
    ]


def test_dynamic_display_dispatch_is_indeterminate(
    synthetic_repository: Path,
) -> None:
    _write(
        synthetic_repository,
        "frontend/src/Dynamic.ts",
        "const formatters = { fixed: (value: number) => `${value}` }\n"
        'const selected = "fixed"\n'
        "export const output = formatters[selected](7)\n",
    )

    process = _run_collector(synthetic_repository)
    result = _result(process)

    assert process.returncode == 2
    assert "判定不能" in process.stderr
    assert result["unresolved"] == [
        {
            "path": "frontend/src/Dynamic.ts",
            "construct": "dynamic-call",
            "expression": "formatters[selected](",
            "reason": "Bracket 記法の呼出し先を静的に確定できない",
        }
    ]


def test_trigger_one_materials_are_machine_readable(
    synthetic_repository: Path,
) -> None:
    process = _run_collector(synthetic_repository)
    materials = _result(process)["trigger1AssessmentMaterials"]
    items = {item["construct"]: item for item in materials["items"]}

    assert process.returncode == 0, process.stderr
    assert materials["judge"] == "山田正輝"
    assert materials["status"] == "pending-po-evaluation"
    assert set(items) == {
        "scoreboard-all-fields",
        "vocabulary-snapshot-map",
        "history-stack",
        "rule-arrays",
        "numeric-display-type-vocabulary",
    }
    assert items["scoreboard-all-fields"]["representable"] is True
    assert items["vocabulary-snapshot-map"]["representable"] is True
    assert items["numeric-display-type-vocabulary"]["representable"] is True


def test_collector_has_no_display_declaration_comparison_path() -> None:
    tree = ast.parse(COLLECTOR_SOURCE.read_text(encoding="utf-8"))
    string_literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }

    assert all("backend/domain/manifest.json" not in value for value in string_literals)
    assert all("display-binding.json" not in value for value in string_literals)
    assert all("contracts/" not in value for value in string_literals)


def test_real_formatter_definition_and_callsite_are_collected() -> None:
    process = _run_real_collector()
    result = _result(process)
    definition_paths = {
        row["path"] for row in result["formatterDefinitions"]
    }
    formatter_calls = [
        row
        for row in result["displayCalls"]
        if row["kind"] == "formatter-call"
    ]

    assert "frontend/src/lib/format.ts" in definition_paths
    assert any(
        row["path"] == "frontend/src/components/zone/StrikeZone.vue"
        and row["formatter"] == "frontend/src/lib/format.ts"
        for row in formatter_calls
    )
    expected_exit = 2 if result["unresolved"] else 0
    assert process.returncode == expected_exit
