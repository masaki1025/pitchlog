"""宣言モデルから言語非依存の中間表現を生成するコアを検査する。"""

from __future__ import annotations

import ast
import copy
import hashlib
import importlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
BACKEND_SRC = ROOT / "backend/src"
CORE_SOURCE = BACKEND_SRC / "pitchlog/domaingen/core.py"
MODEL_SCHEMA_PATH = ROOT / "backend/domain/model.schema.json"
MANIFEST_SCHEMA_PATH = ROOT / "backend/domain/manifest.schema.json"
VOCABULARY_SCHEMA_PATH = ROOT / "backend/domain/vocabulary.schema.json"

sys.path.insert(0, str(BACKEND_SRC))
CORE = importlib.import_module("pitchlog.domaingen.core")

HASH = f"sha256:{'0' * 64}"
OWNED_OBJECT_SCHEMAS = ("root", "Calculation", "Target", "Stage")


@pytest.fixture(scope="module")
def schemas() -> Any:
    """既存の宣言モデル・マニフェスト・語彙 schema を読み込む。"""
    return CORE.SourceSchemas(
        model=_read_json(MODEL_SCHEMA_PATH),
        manifest=_read_json(MANIFEST_SCHEMA_PATH),
        vocabulary=_read_json(VOCABULARY_SCHEMA_PATH),
    )


def _read_json(path: Path) -> dict[str, Any]:
    """JSON object を読み込む。"""
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _write_json(path: Path, value: object) -> None:
    """合成 JSON fixture を整形して書き込む。"""
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _integer(value: int) -> dict[str, object]:
    """構造化整数を返す。"""
    return {"kind": "integer", "value": value}


def _field(field_id: str) -> dict[str, object]:
    """合成宣言モデルの整数フィールドを返す。"""
    return {
        "fieldId": field_id,
        "type": {"kind": "integer"},
        "nullable": False,
        "range": {
            "minimum": _integer(0),
            "maximum": _integer(999),
        },
        "unit": "point",
        "scale": 0,
    }


def _model() -> dict[str, Any]:
    """状態遷移を持つ製品非依存の宣言モデルを返す。"""
    output = _field("visibleMetric")
    output["visibility"] = "user-visible"
    return {
        "schemaVersion": 1,
        "calculations": [
            {
                "calculationId": "syntheticCalculation",
                "inputs": [_field("delta")],
                "states": [
                    {
                        "stateId": "scoreState",
                        "fields": [_field("total")],
                    }
                ],
                "events": [
                    {
                        "eventId": "advance",
                        "fields": [_field("amount")],
                    }
                ],
                "rules": [
                    {
                        "kind": "transition",
                        "ruleId": "applyAdvance",
                        "eventRef": "advance",
                        "guardRefs": [],
                        "nextState": [
                            {
                                "fieldRef": "total",
                                "value": {
                                    "kind": "arithmetic",
                                    "operator": "add",
                                    "operands": [
                                        {
                                            "kind": "state-ref",
                                            "fieldRef": "total",
                                        },
                                        {
                                            "kind": "event-ref",
                                            "fieldRef": "amount",
                                        },
                                    ],
                                },
                            }
                        ],
                    }
                ],
                "outputs": [output],
                "displayRuleRefs": [],
            }
        ],
        "displayRules": [],
    }


def _generated(generated_id: str, artifact_kind: str) -> dict[str, str]:
    """合成生成物の宣言を返す。"""
    return {
        "generatedId": generated_id,
        "path": f"synthetic/generated/{generated_id}.txt",
        "artifactKind": artifact_kind,
    }


def _manifest() -> dict[str, Any]:
    """3 段 composite target を持つ合成マニフェストを返す。"""
    stages = ("sql", "typed-receiver", "formatter")
    generated = [_generated(f"synthetic-{stage}", stage) for stage in stages]
    calculation_id = "syntheticCalculation"
    return {
        "propertyCatalog": {
            "path": "synthetic/properties/catalog.json",
            "schema": "synthetic/properties/catalog.schema.json",
            "provenance": "ADR-003 D-11 3 層表 プロパティ層",
        },
        "calculations": [
            {
                "calculation": calculation_id,
                "source": {
                    "path": "synthetic/source/model.json",
                    "provenance": "ADR-003 D-11 構成の完全性",
                },
                "generated": generated,
                "entrypoints": [
                    {
                        "entrypointId": "synthetic-entrypoint",
                        "module": "synthetic/product.py",
                        "symbol": "execute",
                        "adapter": "synthetic/adapter.py",
                    }
                ],
                "directTargets": [
                    {
                        "directTargetId": "synthetic-direct",
                        "targetClass": "beta-1-5",
                        "kind": "composite",
                        "components": [
                            {
                                "stage": stage,
                                "generated": artifact["generatedId"],
                                "hash": HASH,
                            }
                            for stage, artifact in zip(stages, generated, strict=True)
                        ],
                        "invocation": {
                            "adapter": "synthetic/adapter.py",
                            "operation": "execute",
                        },
                    }
                ],
                "comparison": {"mode": "lossless"},
                "normalization": [],
                "vectors": [
                    {
                        "vectorId": "synthetic-vector",
                        "calculation": calculation_id,
                        "path": "synthetic/vectors/cases.json",
                        "runner": "pytest",
                        "expectedValueSchema": "#/$defs/ExpectedValue",
                        "provenance": "ADR-003 D-6 契約分類",
                    }
                ],
                "properties": [
                    {
                        "propertyId": "synthetic-property",
                        "propertyKind": "invariant",
                        "path": "synthetic/properties/invariant.py",
                        "provenance": "NFR-018 (b)② 差分の検出可能性",
                    }
                ],
                "mutation": [
                    {
                        "mutationId": "synthetic-mutation",
                        "target": "synthetic/generated/synthetic-sql.txt",
                        "operators": ["replace-constant"],
                    }
                ],
            }
        ],
        "displayBindings": [
            {
                "displayItem": "synthetic-visible-metric",
                "callsite": "synthetic/product.py",
                "formatter": "synthetic-formatter",
                "provenance": "ADR-003 D-11 構成の完全性",
            }
        ],
    }


def _generate(schemas: Any) -> dict[str, Any]:
    """合成入力から中間表現を生成する。"""
    return CORE.generate_intermediate_representation(
        _model(),
        _manifest(),
        schemas,
        ROOT,
    )


def _run_core(
    *arguments: str,
) -> subprocess.CompletedProcess[str]:
    """生成専用 CLI を独立プロセスで実行する。"""
    return subprocess.run(
        [sys.executable, "-m", "pitchlog.domaingen.core", *arguments],
        cwd=ROOT,
        env={"PYTHONPATH": str(BACKEND_SRC)},
        capture_output=True,
        text=True,
        check=False,
    )


def _run_checker(*arguments: str) -> subprocess.CompletedProcess[str]:
    """比較対象の適合検査 CLI を独立プロセスで実行する。"""
    return subprocess.run(
        [sys.executable, "-m", "pitchlog.domaincheck.cli", *arguments],
        cwd=ROOT,
        env={"PYTHONPATH": str(BACKEND_SRC)},
        capture_output=True,
        text=True,
        check=False,
    )


def _tree_snapshot(root: Path) -> tuple[tuple[str, str], ...]:
    """ディレクトリ配下の相対パスと内容 hash を返す。"""
    if not root.exists():
        return ()
    snapshot: list[tuple[str, str]] = []
    for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        snapshot.append((path.relative_to(root).as_posix(), digest))
    return tuple(snapshot)


def _owned_schema(name: str) -> dict[str, Any]:
    """中間表現 schema の所有する object 節を返す。"""
    schema = CORE.INTERMEDIATE_REPRESENTATION_SCHEMA
    if name == "root":
        return schema
    return schema["$defs"][name]


def _nested_object(intermediate: dict[str, Any], name: str) -> dict[str, Any]:
    """中間表現から指定した所有 object を返す。"""
    if name == "root":
        return intermediate
    calculation = intermediate["calculations"][0]
    if name == "Calculation":
        return calculation
    target = calculation["targets"][0]
    if name == "Target":
        return target
    return target["stages"][0]


def test_intermediate_schema_has_exact_sets_at_every_owned_layer() -> None:
    assert len(OWNED_OBJECT_SCHEMAS) == 4
    for name in OWNED_OBJECT_SCHEMAS:
        node = _owned_schema(name)
        assert node["type"] == "object"
        assert node["additionalProperties"] is False
        assert set(node["required"]) == set(node["properties"])


@pytest.mark.parametrize("schema_name", OWNED_OBJECT_SCHEMAS)
def test_unknown_key_is_rejected_at_each_owned_layer(
    schema_name: str,
    schemas: Any,
) -> None:
    intermediate = _generate(schemas)
    _nested_object(intermediate, schema_name)["unknown"] = True
    with pytest.raises(CORE.GenerationError, match="未知キー"):
        CORE.validate_intermediate_representation(intermediate, schemas)


@pytest.mark.parametrize("schema_name", OWNED_OBJECT_SCHEMAS)
def test_missing_key_is_rejected_at_each_owned_layer(
    schema_name: str,
    schemas: Any,
) -> None:
    intermediate = _generate(schemas)
    node = _nested_object(intermediate, schema_name)
    field = _owned_schema(schema_name)["required"][0]
    del node[field]
    with pytest.raises(CORE.GenerationError, match="必須キー不足"):
        CORE.validate_intermediate_representation(intermediate, schemas)


def test_empty_input_exits_zero_under_generation_contract() -> None:
    result = _run_core("--root", str(ROOT))

    assert result.returncode == CORE.EXIT_GENERATED == 0
    output = json.loads(result.stdout)
    assert output["calculations"] == []
    assert output["displayRules"] == []


def test_generator_exit_contract_is_separate_from_checker_contract() -> None:
    generator = _run_core("--model", "missing-model.json")
    checker = _run_checker()

    assert generator.returncode == CORE.EXIT_GENERATION_FAILED == 1
    assert checker.returncode == 2
    assert "生成失敗" in generator.stderr
    assert "判定不能" in checker.stderr


def test_generation_leaves_contracts_tree_unchanged(
    tmp_path: Path,
) -> None:
    model_path = tmp_path / "model.json"
    manifest_path = tmp_path / "manifest.json"
    _write_json(model_path, _model())
    _write_json(manifest_path, _manifest())
    before = _tree_snapshot(ROOT / "contracts")

    result = _run_core(
        "--root",
        str(ROOT),
        "--model",
        str(model_path),
        "--manifest",
        str(manifest_path),
    )

    after = _tree_snapshot(ROOT / "contracts")
    assert result.returncode == 0, result.stderr
    assert after == before


def test_source_id_has_clause_form_and_verbatim_exists(schemas: Any) -> None:
    intermediate = _generate(schemas)
    source_id = intermediate["calculations"][0]["sourceId"]
    authority_schema = schemas.manifest["$defs"]["AuthorityId"]

    assert re.fullmatch(authority_schema["pattern"], source_id)
    entry = next(
        item
        for item in schemas.manifest["x-authorityCatalog"]
        if item["id"] == source_id
    )
    source = (ROOT / entry["source"]).read_text(encoding="utf-8")
    section = CORE._section_text(source, entry["section"])
    assert entry["verbatim"] in section


def test_unknown_source_clause_is_rejected(schemas: Any) -> None:
    manifest = _manifest()
    manifest["calculations"][0]["source"]["provenance"] = (
        "ADR-003 D-999 存在しない条項"
    )

    with pytest.raises(CORE.GenerationError, match="カタログ対応"):
        CORE.generate_intermediate_representation(
            _model(),
            manifest,
            schemas,
            ROOT,
        )


def test_changed_authority_wording_is_rejected(schemas: Any) -> None:
    changed_manifest_schema = copy.deepcopy(schemas.manifest)
    entry = next(
        item
        for item in changed_manifest_schema["x-authorityCatalog"]
        if item["id"] == "ADR-003 D-11 構成の完全性"
    )
    entry["verbatim"] += "存在しない逐語"
    changed_schemas = CORE.SourceSchemas(
        model=schemas.model,
        manifest=changed_manifest_schema,
        vocabulary=schemas.vocabulary,
    )

    with pytest.raises(CORE.GenerationError, match="逐語が正本にない"):
        CORE.generate_intermediate_representation(
            _model(),
            _manifest(),
            changed_schemas,
            ROOT,
        )


@pytest.mark.parametrize("schema_name", ["model", "manifest"])
def test_input_field_contract_is_read_from_existing_schemas(
    schema_name: str,
    schemas: Any,
) -> None:
    changed_model = copy.deepcopy(schemas.model)
    changed_manifest = copy.deepcopy(schemas.manifest)
    target = changed_model if schema_name == "model" else changed_manifest
    calculation = target["$defs"]["Calculation"]
    calculation["properties"]["futureField"] = {"type": "boolean"}
    calculation["required"].append("futureField")
    changed_schemas = CORE.SourceSchemas(
        model=changed_model,
        manifest=changed_manifest,
        vocabulary=schemas.vocabulary,
    )

    with pytest.raises(CORE.GenerationError, match="futureField"):
        CORE.generate_intermediate_representation(
            _model(),
            _manifest(),
            changed_schemas,
            ROOT,
        )


def test_valid_model_generates_language_independent_intermediate(
    schemas: Any,
) -> None:
    intermediate = _generate(schemas)
    repeated = _generate(schemas)
    calculation = intermediate["calculations"][0]
    target = calculation["targets"][0]
    stages = target["stages"]

    assert intermediate == repeated
    assert intermediate["generatorVersion"] == CORE.GENERATOR_VERSION
    assert calculation["declaration"] == _model()["calculations"][0]
    assert [stage["stage"] for stage in stages] == [
        "sql",
        "typed-receiver",
        "formatter",
    ]
    assert len({stage["sourceHash"] for stage in stages}) == 3
    assert all(re.fullmatch(r"sha256:[0-9a-f]{64}", stage["sourceHash"]) for stage in stages)
    assert all("code" not in stage for stage in stages)


def test_declaration_change_updates_each_stage_hash(schemas: Any) -> None:
    original = _generate(schemas)
    changed_model = _model()
    changed_model["calculations"][0]["inputs"][0]["range"]["maximum"] = _integer(1000)
    changed = CORE.generate_intermediate_representation(
        changed_model,
        _manifest(),
        schemas,
        ROOT,
    )
    original_hashes = {
        stage["sourceHash"]
        for stage in original["calculations"][0]["targets"][0]["stages"]
    }
    changed_hashes = {
        stage["sourceHash"]
        for stage in changed["calculations"][0]["targets"][0]["stages"]
    }

    assert len(original_hashes) == len(changed_hashes) == 3
    assert original_hashes.isdisjoint(changed_hashes)


def test_core_contains_no_language_backend_implementation() -> None:
    tree = ast.parse(CORE_SOURCE.read_text(encoding="utf-8"))
    function_names = {
        node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    }

    assert function_names.isdisjoint(
        {"generate_python", "generate_typescript", "generate_sql"}
    )
