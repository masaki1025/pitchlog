"""合成 DSL から全 target matrix と後続 runner の入力を実生成する。"""

from __future__ import annotations

import copy
import importlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
BACKEND_SRC = ROOT / "backend/src"
FIXTURE_ROOT = ROOT / "backend/tests/domain/fixtures/synthetic_dsl"
MODEL_FIXTURE = FIXTURE_ROOT / "model.json"
MANIFEST_FIXTURE = FIXTURE_ROOT / "manifest.json"
ASSESSMENT_FIXTURE = FIXTURE_ROOT / "assessment.json"
TARGET_CLASSES = {"alpha", "beta-1-5", "beta-7", "beta-6-8"}
EXPECTED_ARTIFACT_COUNTS = {
    "alpha": 5,
    "beta-1-5": 4,
    "beta-7": 4,
    "beta-6-8": 2,
}

sys.path.insert(0, str(BACKEND_SRC))
CORE = importlib.import_module("pitchlog.domaingen.core")
PREGEN = importlib.import_module("pitchlog.domaingen.pregen_checks")
BACKENDS = importlib.import_module("pitchlog.domaingen.backends")
FORMATTER = importlib.import_module("pitchlog.domaingen.formatter")


@pytest.fixture(scope="module")
def schemas() -> Any:
    """既存の宣言モデル・マニフェスト・語彙 schema を返す。"""
    return CORE.SourceSchemas(
        model=_read_json(ROOT / "backend/domain/model.schema.json"),
        manifest=_read_json(ROOT / "backend/domain/manifest.schema.json"),
        vocabulary=_read_json(ROOT / "backend/domain/vocabulary.schema.json"),
    )


def _read_json(path: Path) -> dict[str, Any]:
    """UTF-8 の JSON object を読み込む。"""
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _pipeline(
    schemas: Any,
    model: dict[str, Any] | None = None,
    manifest: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], tuple[Any, ...], tuple[Any, ...]]:
    """ステップ 26〜29 を通して全生成物を返す。"""
    intermediate = PREGEN.generate_checked(
        _read_json(MODEL_FIXTURE) if model is None else model,
        _read_json(MANIFEST_FIXTURE) if manifest is None else manifest,
        schemas,
        ROOT,
    )
    CORE.validate_intermediate_representation(intermediate, schemas)
    language_artifacts = BACKENDS.generate_language_artifacts(intermediate)
    display_artifacts = FORMATTER.generate_display_artifacts(intermediate)
    return intermediate, language_artifacts, display_artifacts


def _target_by_class(
    manifest: dict[str, Any],
    target_class: str,
) -> dict[str, Any]:
    """指定区分の direct target を一意に返す。"""
    matches = [
        target
        for calculation in manifest["calculations"]
        for target in calculation["directTargets"]
        if target["targetClass"] == target_class
    ]
    assert len(matches) == 1
    return matches[0]


def _artifact_counts(
    language_artifacts: tuple[Any, ...],
    display_artifacts: tuple[Any, ...],
) -> dict[str, int]:
    """言語生成物と表示生成物を区分別に数える。"""
    return dict(
        sorted(
            Counter(
                artifact.target_class
                for artifact in (*language_artifacts, *display_artifacts)
            ).items()
        )
    )


def _line_counts(root: Path, pattern: str) -> dict[str, int]:
    """物理行数を相対パスごとに数える。"""
    return {
        path.relative_to(ROOT).as_posix(): len(
            path.read_text(encoding="utf-8").splitlines()
        )
        for path in sorted(root.glob(pattern))
        if path.is_file()
    }


def _string_leaves(value: object) -> list[str]:
    """JSON 木の文字列葉を再帰的に列挙する。"""
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for child in value for item in _string_leaves(child)]
    if isinstance(value, dict):
        return [item for child in value.values() for item in _string_leaves(child)]
    return []


def _calculation(model: dict[str, Any], calculation_id: str) -> dict[str, Any]:
    """指定 ID の計算宣言を一意に返す。"""
    matches = [
        calculation
        for calculation in model["calculations"]
        if calculation["calculationId"] == calculation_id
    ]
    assert len(matches) == 1
    return matches[0]


def _all_fields(calculation: dict[str, Any]) -> list[dict[str, Any]]:
    """計算宣言に含まれる全フィールドを返す。"""
    fields = [*calculation["inputs"], *calculation["outputs"]]
    for owner in (*calculation["states"], *calculation["events"]):
        fields.extend(owner["fields"])
    return fields


def _trigger_one_materials() -> dict[str, bool]:
    """判断材料 5 項目が合成 DSL に実在するかを測る。"""
    model = _read_json(MODEL_FIXTURE)
    assessment = _read_json(ASSESSMENT_FIXTURE)["trigger1Materials"]
    calculation_id = assessment["historyStack"]["calculationId"]
    calculation = _calculation(model, calculation_id)
    fields = {field["fieldId"]: field for field in _all_fields(calculation)}
    outputs = {field["fieldId"]: field for field in calculation["outputs"]}
    display_rules = {rule["id"]: rule for rule in model["displayRules"]}

    history = assessment["historyStack"]
    vocabulary = assessment["vocabularySnapshotMap"]
    scoreboard = assessment["scoreboardAllFields"]
    numeric = assessment["numericValueDisplayAtom"]
    template = display_rules[numeric["displayRuleId"]]
    placeholder_types = {
        value["type"] for value in template["placeholders"].values()
    }
    return {
        "historyStack": (
            fields[history["fieldId"]]["type"]["kind"] == history["typeKind"]
        ),
        "ruleArray": (
            {rule["kind"] for rule in calculation["rules"]}
            == set(assessment["ruleArray"]["ruleKinds"])
        ),
        "vocabularySnapshotMap": (
            fields[vocabulary["fieldId"]]["type"]["kind"]
            == vocabulary["typeKind"]
        ),
        "scoreboardAllFields": (
            set(scoreboard["fieldIds"]) <= set(outputs)
            and len(scoreboard["fieldIds"]) == 9
        ),
        "numericValueDisplayAtom": (
            outputs[numeric["outputFieldId"]]["type"]["kind"]
            == numeric["numericTypeKind"]
            and placeholder_types == {numeric["displayAtomType"]}
        ),
    }


def test_all_target_matrix_classes_generate_from_synthetic_dsl(
    schemas: Any,
) -> None:
    """全 4 区分を既存生成器へ通して生成する。"""
    intermediate, language_artifacts, display_artifacts = _pipeline(schemas)
    evaluation = FORMATTER.evaluate_target_matrix(intermediate)
    observed = {
        artifact.target_class
        for artifact in (*language_artifacts, *display_artifacts)
    }

    assert len(evaluation.expected) == 4
    assert evaluation.expected == TARGET_CLASSES
    assert evaluation.generated == TARGET_CLASSES
    assert evaluation.complete
    assert evaluation.failures == ()
    assert observed == TARGET_CLASSES


def test_kind_and_stage_counts_match_manifest_schema_in_real_generation(
    schemas: Any,
) -> None:
    """Schema 由来の kind・段数契約が生成後にも一致することを示す。"""
    intermediate, _, _ = _pipeline(schemas)
    manifest_schema = _read_json(ROOT / "backend/domain/manifest.schema.json")
    expected = manifest_schema["x-expectations"]["targetStageCounts"]["expected"]
    targets = {
        target["targetClass"]: target
        for calculation in intermediate["calculations"]
        for target in calculation["targets"]
    }

    assert len(expected) == 4
    assert set(expected) == TARGET_CLASSES
    assert set(targets) == TARGET_CLASSES
    for target_class, stage_count in expected.items():
        target = targets[target_class]
        assert len(target["stages"]) == stage_count
        assert target["kind"] == (
            "composite" if stage_count >= 2 else "single"
        )


@pytest.mark.parametrize("mutation", ["kind", "stage-count"])
def test_manifest_schema_rejects_kind_or_stage_count_mismatch(
    mutation: str,
    schemas: Any,
) -> None:
    """Kind または段数を崩した fixture が実生成へ入れないことを示す。"""
    manifest = _read_json(MANIFEST_FIXTURE)
    target = _target_by_class(manifest, "beta-1-5")
    if mutation == "kind":
        target["kind"] = "single"
    else:
        target["components"].pop()

    with pytest.raises(CORE.GenerationError):
        PREGEN.generate_checked(
            _read_json(MODEL_FIXTURE),
            manifest,
            schemas,
            ROOT,
        )


def test_synthetic_fixture_contains_no_product_vectors() -> None:
    """合成 fixture に製品ベクタや製品ドメイン値がないことを静的検査する。"""
    documents = [
        _read_json(MODEL_FIXTURE),
        _read_json(MANIFEST_FIXTURE),
        _read_json(ASSESSMENT_FIXTURE),
    ]
    leaves = [leaf.lower() for document in documents for leaf in _string_leaves(document)]
    forbidden = {
        "contracts/",
        "frontend/",
        "inning",
        "pitcher",
        "batter",
        "イニング",
        "投手",
        "打者",
        "得点",
        "失点",
    }
    manifest = documents[1]

    assert all(token not in leaf for leaf in leaves for token in forbidden)
    assert all(
        calculation["calculation"].startswith("synthetic")
        for calculation in manifest["calculations"]
    )
    assert all(
        vector["path"].startswith(
            "backend/tests/domain/fixtures/synthetic_dsl/"
        )
        for calculation in manifest["calculations"]
        for vector in calculation["vectors"]
    )


def test_generated_artifacts_form_inputs_for_all_three_runner_layers(
    schemas: Any,
) -> None:
    """生成物をベクタ・プロパティ・変異の各層へ渡せる形に束ねる。"""
    intermediate, language_artifacts, display_artifacts = _pipeline(schemas)
    manifest_calculation = _read_json(MANIFEST_FIXTURE)["calculations"][0]
    generated = (*language_artifacts, *display_artifacts)
    runner_inputs = []
    for calculation in intermediate["calculations"]:
        for target in calculation["targets"]:
            direct_target_id = target["directTargetId"]
            runner_inputs.append(
                {
                    "directTargetId": direct_target_id,
                    "vectorLayer": manifest_calculation["vectors"],
                    "propertyLayer": manifest_calculation["properties"],
                    "mutationLayer": manifest_calculation["mutation"],
                    "stageHashes": [
                        stage["sourceHash"] for stage in target["stages"]
                    ],
                    "generatedArtifacts": [
                        artifact
                        for artifact in generated
                        if artifact.direct_target_id == direct_target_id
                    ],
                }
            )

    assert len(runner_inputs) == len(TARGET_CLASSES) == 4
    assert all(item["vectorLayer"] for item in runner_inputs)
    assert all(item["propertyLayer"] for item in runner_inputs)
    assert all(item["mutationLayer"] for item in runner_inputs)
    assert all(item["stageHashes"] for item in runner_inputs)
    assert all(item["generatedArtifacts"] for item in runner_inputs)


def test_adding_one_declaration_requires_only_declared_maintenance_files(
    schemas: Any,
) -> None:
    """宣言を 1 件追加し、実生成までに触る fixture を実測する。"""
    model = _read_json(MODEL_FIXTURE)
    manifest = _read_json(MANIFEST_FIXTURE)
    original_model = copy.deepcopy(model)
    original_manifest = copy.deepcopy(manifest)
    added_declaration = copy.deepcopy(model["calculations"][0])
    added_registration = copy.deepcopy(manifest["calculations"][0])
    added_declaration["calculationId"] = "syntheticAddition"
    added_registration["calculation"] = "syntheticAddition"
    added_registration["vectors"][0]["calculation"] = "syntheticAddition"
    model["calculations"].append(added_declaration)
    manifest["calculations"].append(added_registration)

    intermediate, language_artifacts, display_artifacts = _pipeline(
        schemas,
        model,
        manifest,
    )
    actual_touched = {
        path.relative_to(ROOT).as_posix()
        for path, before, after in (
            (MODEL_FIXTURE, original_model, model),
            (MANIFEST_FIXTURE, original_manifest, manifest),
        )
        if before != after
    }
    maintenance = _read_json(ASSESSMENT_FIXTURE)["maintenanceProcedure"]

    assert actual_touched == set(maintenance["touchedFiles"])
    assert len(maintenance["steps"]) == 3
    assert {item["calculationId"] for item in intermediate["calculations"]} == {
        "syntheticMatrix",
        "syntheticAddition",
    }
    assert language_artifacts
    assert display_artifacts


def test_trigger_one_materials_are_expressed_by_the_synthetic_dsl() -> None:
    """トリガー 1 の 5 項目を推定でなく fixture から実測する。"""
    materials = _trigger_one_materials()

    assert len(materials) == 5
    assert all(materials.values())


def test_po_assessment_measurements_are_reproducible(
    schemas: Any,
) -> None:
    """PO 判断材料の行数・生成数・保守手順・表現可否を再計測する。"""
    _, language_artifacts, display_artifacts = _pipeline(schemas)
    implementation_lines = _line_counts(
        BACKEND_SRC / "pitchlog/domaingen",
        "**/*.py",
    )
    test_lines = _line_counts(ROOT / "tests/domain/gen", "*.py")
    generated = _artifact_counts(language_artifacts, display_artifacts)
    maintenance = _read_json(ASSESSMENT_FIXTURE)["maintenanceProcedure"]
    materials = {
        "implementationLines": {
            "files": implementation_lines,
            "total": sum(implementation_lines.values()),
        },
        "testLines": {
            "files": test_lines,
            "total": sum(test_lines.values()),
        },
        "generatedArtifacts": {
            "byTargetClass": generated,
            "total": sum(generated.values()),
        },
        "maintenanceProcedure": maintenance,
        "trigger1Materials": _trigger_one_materials(),
    }

    print(
        "STEP30_MEASUREMENTS="
        + json.dumps(materials, ensure_ascii=False, sort_keys=True)
    )
    assert generated == EXPECTED_ARTIFACT_COUNTS
    assert materials["implementationLines"]["total"] == sum(
        implementation_lines.values()
    )
    assert materials["testLines"]["total"] == sum(test_lines.values())
    assert materials["generatedArtifacts"]["total"] == 15
    assert all(materials["trigger1Materials"].values())
