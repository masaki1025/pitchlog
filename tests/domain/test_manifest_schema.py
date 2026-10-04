"""design.md §6 のマニフェスト schema を検査する。"""

from __future__ import annotations

import copy
import json
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "backend/domain/manifest.schema.json"
CHECKER_PATH = ROOT / "backend/src/pitchlog/domaincheck/cli.py"

TOP_LEVEL_FIELDS = {"propertyCatalog", "calculations", "displayBindings"}
CALCULATION_FIELDS = {
    "calculation",
    "source",
    "generated",
    "entrypoints",
    "directTargets",
    "comparison",
    "normalization",
    "vectors",
    "properties",
    "mutation",
}
NONEMPTY_CALCULATION_FIELDS = {
    "entrypoints",
    "directTargets",
    "vectors",
    "properties",
    "mutation",
}
COMPARISON_TYPES = {"exact-set", "equals", "minimum"}
LINE_NUMBER_REFERENCE_PATTERN = re.compile(r":\d+")
HASH = f"sha256:{'0' * 64}"


class SchemaValidationError(AssertionError):
    """合成マニフェストが凍結 schema に適合しないことを表す。"""


@pytest.fixture(scope="module")
def schema() -> dict[str, Any]:
    """マニフェスト schema を読み込む。"""
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _resolve_ref(schema: dict[str, Any], ref: str) -> Any:
    """同一 schema 内の JSON Pointer を解決する。"""
    if not ref.startswith("#/"):
        raise SchemaValidationError(f"ローカル参照ではありません: {ref}")
    node: Any = schema
    for token in ref[2:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        node = node[token]
    return node


def _matches_type(instance: Any, expected: str) -> bool:
    """JSON Schema の基本型に適合するかを返す。"""
    match expected:
        case "object":
            return isinstance(instance, dict)
        case "array":
            return isinstance(instance, list)
        case "string":
            return isinstance(instance, str)
        case "integer":
            return isinstance(instance, int) and not isinstance(instance, bool)
        case "boolean":
            return isinstance(instance, bool)
        case "null":
            return instance is None
        case _:
            raise SchemaValidationError(f"テスト検証器が未対応の型です: {expected}")


def _validate(
    instance: Any,
    node: Any,
    schema: dict[str, Any],
    path: str = "$",
) -> None:
    """本 schema が使う JSON Schema と閉じた拡張語彙を検証する。"""
    if node is True:
        return
    if node is False:
        raise SchemaValidationError(f"{path}: false schema")
    if not isinstance(node, dict):
        raise SchemaValidationError(f"{path}: schema が object でない")

    if "$ref" in node:
        _validate(instance, _resolve_ref(schema, node["$ref"]), schema, path)
        return

    if "oneOf" in node:
        matched = 0
        for branch in node["oneOf"]:
            try:
                _validate(instance, branch, schema, path)
            except SchemaValidationError:
                continue
            matched += 1
        if matched != 1:
            raise SchemaValidationError(f"{path}: oneOf の適合数が {matched}")
        return

    if "const" in node and instance != node["const"]:
        raise SchemaValidationError(f"{path}: const に不適合")
    if "enum" in node and instance not in node["enum"]:
        raise SchemaValidationError(f"{path}: enum に不適合")

    expected_type = node.get("type")
    if expected_type is not None and not _matches_type(instance, expected_type):
        raise SchemaValidationError(f"{path}: 型 {expected_type} に不適合")

    if isinstance(instance, str):
        if len(instance) < node.get("minLength", 0):
            raise SchemaValidationError(f"{path}: minLength に不適合")
        if "pattern" in node and re.search(node["pattern"], instance) is None:
            raise SchemaValidationError(f"{path}: pattern に不適合")

    if isinstance(instance, dict):
        required = set(node.get("required", []))
        missing = required - set(instance)
        if missing:
            raise SchemaValidationError(f"{path}: 必須キー不足 {sorted(missing)!r}")
        properties = node.get("properties", {})
        if node.get("additionalProperties") is False:
            unknown = set(instance) - set(properties)
            if unknown:
                raise SchemaValidationError(f"{path}: 未知キー {sorted(unknown)!r}")
        for key, value in instance.items():
            if key in properties:
                _validate(value, properties[key], schema, f"{path}.{key}")

    if isinstance(instance, list):
        if len(instance) < node.get("minItems", 0):
            raise SchemaValidationError(f"{path}: minItems に不適合")
        if "maxItems" in node and len(instance) > node["maxItems"]:
            raise SchemaValidationError(f"{path}: maxItems に不適合")
        if node.get("uniqueItems"):
            canonical = [
                json.dumps(value, ensure_ascii=False, sort_keys=True) for value in instance
            ]
            if len(canonical) != len(set(canonical)):
                raise SchemaValidationError(f"{path}: uniqueItems に不適合")
        if "x-uniqueBy" in node:
            key = node["x-uniqueBy"]
            values = [value.get(key) for value in instance if isinstance(value, dict)]
            if len(values) != len(instance) or len(values) != len(set(values)):
                raise SchemaValidationError(f"{path}: {key} が重複")
        if "x-stageOrder" in node:
            stages = [value.get("stage") for value in instance]
            if stages != node["x-stageOrder"]:
                raise SchemaValidationError(f"{path}: 段の順序が不正")
        if "items" in node:
            for index, value in enumerate(instance):
                _validate(value, node["items"], schema, f"{path}[{index}]")


def _assert_manifest_semantics(manifest: dict[str, Any]) -> None:
    """親子参照と対象 ID ごとのベクタ帰属を検査する。"""
    calculations = manifest["calculations"]
    calculation_ids = [calculation["calculation"] for calculation in calculations]
    assert calculation_ids, "対象母集合が空"
    assert len(calculation_ids) == len(set(calculation_ids)), "calculation ID が重複"

    vector_owners: list[str] = []
    for calculation in calculations:
        calculation_id = calculation["calculation"]
        generated_kinds = {
            artifact["generatedId"]: artifact["artifactKind"]
            for artifact in calculation["generated"]
        }
        for target in calculation["directTargets"]:
            if target["kind"] == "single":
                assert target["generated"] in generated_kinds, "未知の generated 参照"
                continue
            component_ids = [component["generated"] for component in target["components"]]
            assert len(component_ids) == len(set(component_ids)), "components 参照が重複"
            assert not set(component_ids) - set(generated_kinds), "未知の generated 参照"
            for component in target["components"]:
                assert generated_kinds[component["generated"]] == component["stage"]

        assert len(calculation["vectors"]) == 1
        for vector in calculation["vectors"]:
            assert vector["calculation"] == calculation_id, "未知契約の対象 ID"
            vector_owners.append(vector["calculation"])

    ownership_counts = {
        calculation_id: vector_owners.count(calculation_id)
        for calculation_id in calculation_ids
    }
    assert all(count == 1 for count in ownership_counts.values()), "ベクタ帰属数が 1 でない"
    assert set(vector_owners) == set(calculation_ids), "未知契約または未帰属がある"


def _validate_manifest(manifest: dict[str, Any], schema: dict[str, Any]) -> None:
    """JSON Schema と識別子間の意味制約を適用する。"""
    _validate(manifest, schema, schema)
    _assert_manifest_semantics(manifest)


def _section_text(source_text: str, section_heading: str) -> str:
    """指定見出しに属する本文を取り出す。"""
    lines = source_text.splitlines()
    try:
        start = lines.index(section_heading)
    except ValueError as error:
        raise AssertionError(f"正本に節見出しがありません: {section_heading}") from error

    level = len(section_heading) - len(section_heading.lstrip("#"))
    end = len(lines)
    for index in range(start + 1, len(lines)):
        heading = re.match(r"^(#+)\s", lines[index])
        if heading is not None and len(heading.group(1)) <= level:
            end = index
            break
    return "\n".join(lines[start:end])


def _assert_authority_wording_exists(candidate: dict[str, Any]) -> None:
    """schema が持つ条項 ID と逐語が指定した正本に実在することを検査する。"""
    catalog = candidate["x-authorityCatalog"]
    catalog_ids = [entry["id"] for entry in catalog]
    assert catalog_ids and len(catalog_ids) == len(set(catalog_ids))
    for entry in catalog:
        assert set(entry) == {"id", "source", "section", "verbatim"}
        _validate(entry["id"], candidate["$defs"]["AuthorityId"], candidate)
        source_text = (ROOT / entry["source"]).read_text(encoding="utf-8")
        section = _section_text(source_text, entry["section"])
        assert entry["verbatim"] in section, f"逐語が実在しない: {entry['id']}"

    expectations = candidate["x-expectations"]
    for expectation_id, expectation in expectations.items():
        assert set(expectation) == {"expected", "comparison", "provenance"}
        assert expectation["comparison"] in COMPARISON_TYPES
        assert expectation["provenance"] in set(catalog_ids), (
            f"期待値 {expectation_id} の provenance が未登録"
        )

    serialized = json.dumps(candidate, ensure_ascii=False)
    assert LINE_NUMBER_REFERENCE_PATTERN.search(serialized) is None


def _generated(generated_id: str, artifact_kind: str) -> dict[str, str]:
    """合成生成物の宣言を返す。"""
    return {
        "generatedId": generated_id,
        "path": f"synthetic/generated/{generated_id}.txt",
        "artifactKind": artifact_kind,
    }


def _calculation(target_class: str) -> dict[str, Any]:
    """対象区分に対応する合成対象計算を返す。"""
    calculation_id = f"synthetic-{target_class}"
    stages_by_class = {
        "alpha": ["python"],
        "beta-1-5": ["sql", "typed-receiver", "formatter"],
        "beta-7": ["sql", "typed-receiver"],
        "beta-6-8": ["python"],
    }
    stages = stages_by_class[target_class]
    generated = [
        _generated(f"{calculation_id}-{stage}", stage) for stage in stages
    ]
    invocation = {
        "adapter": f"synthetic/adapters/{calculation_id}.py",
        "operation": "run",
    }
    if len(stages) == 1:
        direct_target: dict[str, Any] = {
            "directTargetId": f"{calculation_id}-direct",
            "targetClass": target_class,
            "kind": "single",
            "generated": generated[0]["generatedId"],
            "hash": HASH,
            "invocation": invocation,
        }
    else:
        direct_target = {
            "directTargetId": f"{calculation_id}-direct",
            "targetClass": target_class,
            "kind": "composite",
            "components": [
                {
                    "stage": stage,
                    "generated": artifact["generatedId"],
                    "hash": HASH,
                }
                for stage, artifact in zip(stages, generated, strict=True)
            ],
            "invocation": invocation,
        }

    return {
        "calculation": calculation_id,
        "source": {
            "path": f"synthetic/source/{calculation_id}.json",
            "provenance": "ADR-003 D-11 構成の完全性",
        },
        "generated": generated,
        "entrypoints": [
            {
                "entrypointId": f"{calculation_id}-entrypoint",
                "module": f"synthetic/product/{calculation_id}.py",
                "symbol": "execute",
                "adapter": f"synthetic/adapters/{calculation_id}.py",
            }
        ],
        "directTargets": [direct_target],
        "comparison": {"mode": "lossless"},
        "normalization": [],
        "vectors": [
            {
                "vectorId": f"{calculation_id}-vector",
                "calculation": calculation_id,
                "path": f"synthetic/vectors/{calculation_id}.json",
                "runner": "pytest",
                "expectedValueSchema": "#/$defs/ExpectedValue",
                "provenance": "ADR-003 D-6 契約分類",
            }
        ],
        "properties": [
            {
                "propertyId": f"{calculation_id}-invariant",
                "propertyKind": "invariant",
                "path": f"synthetic/properties/{calculation_id}.py",
                "provenance": "NFR-018 (b)② 差分の検出可能性",
            }
        ],
        "mutation": [
            {
                "mutationId": f"{calculation_id}-mutation",
                "target": generated[0]["path"],
                "operators": ["replace-constant"],
            }
        ],
    }


def _manifest(*target_classes: str) -> dict[str, Any]:
    """製品対象を含まない合成マニフェストを返す。"""
    return {
        "propertyCatalog": {
            "path": "synthetic/properties/catalog.json",
            "schema": "synthetic/properties/catalog.schema.json",
            "provenance": "ADR-003 D-11 3 層表 プロパティ層",
        },
        "calculations": [_calculation(target_class) for target_class in target_classes],
        "displayBindings": [
            {
                "displayItem": "synthetic-score",
                "callsite": "synthetic/product/score.py",
                "formatter": "format-score",
                "provenance": "ADR-003 D-11 構成の完全性",
            }
        ],
    }


def _write_and_validate(
    tmp_path: Path, manifest: dict[str, Any], schema: dict[str, Any]
) -> None:
    """一時ディレクトリの合成マニフェストを読み戻して検証する。"""
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
    _validate_manifest(loaded, schema)


def _addition_commit(relative_path: str) -> str | None:
    """指定パスを追加したコミットを履歴から返す。"""
    result = subprocess.run(
        ["git", "log", "--diff-filter=A", "--format=%H", "--", relative_path],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    commits = [line for line in result.stdout.splitlines() if line]
    return commits[-1] if commits else None


def test_two_layer_exact_sets_have_three_and_ten_fields(schema: dict[str, Any]) -> None:
    top_properties = set(schema["properties"])
    calculation = schema["$defs"]["Calculation"]
    calculation_properties = set(calculation["properties"])

    assert len(top_properties) == 3
    assert top_properties == TOP_LEVEL_FIELDS
    assert set(schema["required"]) == TOP_LEVEL_FIELDS
    assert len(calculation_properties) == 10
    assert calculation_properties == CALCULATION_FIELDS
    assert set(calculation["required"]) == CALCULATION_FIELDS


def test_kind_and_stage_counts_are_frozen(schema: dict[str, Any]) -> None:
    three_stage = schema["$defs"]["ThreeStageCompositeTarget"]["properties"]
    two_stage = schema["$defs"]["TwoStageCompositeTarget"]["properties"]
    single = schema["$defs"]["SingleTarget"]["properties"]

    assert three_stage["targetClass"]["const"] == "beta-1-5"
    assert three_stage["components"]["minItems"] == 3
    assert three_stage["components"]["maxItems"] == 3
    assert two_stage["targetClass"]["const"] == "beta-7"
    assert two_stage["components"]["minItems"] == 2
    assert two_stage["components"]["maxItems"] == 2
    assert single["kind"]["const"] == "single"
    assert set(single["targetClass"]["enum"]) == {"alpha", "beta-6-8"}
    assert "generated" in single and "components" not in single


def test_nonempty_fields_and_composite_minimum_are_frozen(
    schema: dict[str, Any],
) -> None:
    properties = schema["$defs"]["Calculation"]["properties"]
    assert len(NONEMPTY_CALCULATION_FIELDS) == 5
    for field in NONEMPTY_CALCULATION_FIELDS:
        assert properties[field]["minItems"] == 1
    assert schema["$defs"]["ThreeStageCompositeTarget"]["properties"]["components"][
        "minItems"
    ] >= 2
    assert schema["$defs"]["TwoStageCompositeTarget"]["properties"]["components"][
        "minItems"
    ] >= 2


def test_provenance_wording_exists_in_named_canonical_sections(
    schema: dict[str, Any],
) -> None:
    _assert_authority_wording_exists(schema)


def test_each_expectation_has_expected_comparison_and_provenance(
    schema: dict[str, Any],
) -> None:
    expected_value = schema["$defs"]["ExpectedValue"]
    assert set(expected_value["properties"]) == {
        "expected",
        "comparison",
        "provenance",
    }
    assert set(expected_value["required"]) == set(expected_value["properties"])
    assert expected_value["additionalProperties"] is False
    _validate(
        {
            "expected": {"value": 1},
            "comparison": "exact",
            "provenance": "ADR-003 D-6 契約分類",
        },
        expected_value,
        schema,
    )


def test_line_number_provenance_is_rejected(schema: dict[str, Any]) -> None:
    with pytest.raises(SchemaValidationError, match="pattern"):
        _validate(
            "ADR-003 D-6 契約分類:264",
            schema["$defs"]["AuthorityId"],
            schema,
        )


def test_each_schema_layer_has_rejection_leaves(schema: dict[str, Any]) -> None:
    assert schema["additionalProperties"] is False
    assert schema["$defs"]["Calculation"]["additionalProperties"] is False
    assert schema["$defs"]["ExpectedValue"]["additionalProperties"] is False
    assert schema["$defs"]["DirectTarget"]["oneOf"]


def test_schema_history_precedes_checker_in_git_history(schema: dict[str, Any]) -> None:
    history_rule = schema["x-historyPrecedes"]
    assert history_rule == {
        "beforePath": "backend/domain/manifest.schema.json",
        "afterPath": "backend/src/pitchlog/domaincheck/cli.py",
        "method": "history_precedes",
        "sameCommitAllowed": False,
    }
    schema_commit = _addition_commit(history_rule["beforePath"])
    checker_commit = _addition_commit(history_rule["afterPath"])

    if checker_commit is None:
        if CHECKER_PATH.exists():
            assert schema_commit is not None, "検査器より前の schema コミットが無い"
        return

    assert schema_commit is not None, "schema の追加コミットが無い"
    assert schema_commit != checker_commit, "schema と検査器が同一コミット"
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", schema_commit, checker_commit],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, "schema が検査器より履歴上先行していない"


def test_vector_ownership_is_exactly_one_and_has_no_unknown_contracts(
    schema: dict[str, Any],
) -> None:
    manifest = _manifest("alpha", "beta-1-5", "beta-7")
    _validate_manifest(manifest, schema)
    calculations = manifest["calculations"]
    assert calculations
    assert all(len(calculation["vectors"]) == 1 for calculation in calculations)
    target_ids = {calculation["calculation"] for calculation in calculations}
    vector_ids = {
        vector["calculation"]
        for calculation in calculations
        for vector in calculation["vectors"]
    }
    assert vector_ids == target_ids


def test_calculation_population_must_not_be_empty(schema: dict[str, Any]) -> None:
    mutated = _manifest("alpha")
    mutated["calculations"] = []
    with pytest.raises(SchemaValidationError, match="minItems"):
        _validate_manifest(mutated, schema)


def test_missing_vector_contract_is_rejected(schema: dict[str, Any]) -> None:
    mutated = _manifest("alpha")
    mutated["calculations"][0]["vectors"] = []
    with pytest.raises(SchemaValidationError, match="minItems"):
        _validate_manifest(mutated, schema)


def test_duplicate_vector_contract_is_rejected(schema: dict[str, Any]) -> None:
    mutated = _manifest("alpha")
    vector = copy.deepcopy(mutated["calculations"][0]["vectors"][0])
    mutated["calculations"][0]["vectors"].append(vector)
    with pytest.raises(SchemaValidationError):
        _validate_manifest(mutated, schema)


def test_unknown_vector_contract_is_rejected(schema: dict[str, Any]) -> None:
    mutated = _manifest("alpha")
    mutated["calculations"][0]["vectors"][0]["calculation"] = "unknown-contract"
    with pytest.raises(AssertionError, match="未知契約"):
        _validate_manifest(mutated, schema)


def test_duplicate_calculation_id_is_rejected(schema: dict[str, Any]) -> None:
    mutated = _manifest("alpha", "beta-6-8")
    duplicate_id = mutated["calculations"][0]["calculation"]
    mutated["calculations"][1]["calculation"] = duplicate_id
    with pytest.raises(SchemaValidationError, match="calculation が重複"):
        _validate_manifest(mutated, schema)


def test_duplicate_component_generated_reference_is_rejected(
    schema: dict[str, Any],
) -> None:
    mutated = _manifest("beta-1-5")
    components = mutated["calculations"][0]["directTargets"][0]["components"]
    components[1]["generated"] = components[0]["generated"]
    component_schema = schema["$defs"]["ThreeStageCompositeTarget"]["properties"][
        "components"
    ]
    with pytest.raises(SchemaValidationError, match="generated が重複"):
        _validate(components, component_schema, schema)


def test_duplicate_entrypoint_id_is_rejected(schema: dict[str, Any]) -> None:
    mutated = _manifest("alpha")
    entrypoint = copy.deepcopy(mutated["calculations"][0]["entrypoints"][0])
    mutated["calculations"][0]["entrypoints"].append(entrypoint)
    with pytest.raises(SchemaValidationError, match="entrypointId が重複"):
        _validate_manifest(mutated, schema)


def test_duplicate_property_id_is_rejected(schema: dict[str, Any]) -> None:
    mutated = _manifest("alpha")
    property_entry = copy.deepcopy(mutated["calculations"][0]["properties"][0])
    mutated["calculations"][0]["properties"].append(property_entry)
    with pytest.raises(SchemaValidationError, match="propertyId が重複"):
        _validate_manifest(mutated, schema)


@pytest.mark.parametrize(
    "field",
    ["entrypoints", "directTargets", "vectors", "properties", "mutation"],
)
def test_each_required_nonempty_field_rejects_an_empty_array(
    schema: dict[str, Any], field: str
) -> None:
    mutated = _manifest("alpha")
    mutated["calculations"][0][field] = []
    with pytest.raises(SchemaValidationError, match="minItems"):
        _validate_manifest(mutated, schema)


@pytest.mark.parametrize(
    ("target_class", "mutation"),
    [
        ("beta-1-5", "remove-component"),
        ("beta-7", "add-formatter"),
        ("alpha", "change-kind"),
    ],
)
def test_kind_and_wrong_stage_count_are_rejected(
    schema: dict[str, Any], target_class: str, mutation: str
) -> None:
    manifest = _manifest(target_class)
    calculation = manifest["calculations"][0]
    target = calculation["directTargets"][0]
    if mutation == "remove-component":
        target["components"].pop()
    elif mutation == "add-formatter":
        formatter = _generated("synthetic-beta-7-formatter", "formatter")
        calculation["generated"].append(formatter)
        target["components"].append(
            {"stage": "formatter", "generated": formatter["generatedId"], "hash": HASH}
        )
    else:
        target["kind"] = "composite"

    with pytest.raises(SchemaValidationError):
        _validate_manifest(manifest, schema)


def test_missing_calculation_field_is_rejected(schema: dict[str, Any]) -> None:
    mutated = _manifest("alpha")
    mutated["calculations"][0].pop("source")
    with pytest.raises(SchemaValidationError, match="source"):
        _validate_manifest(mutated, schema)


def test_unknown_calculation_field_is_rejected(schema: dict[str, Any]) -> None:
    mutated = _manifest("alpha")
    mutated["calculations"][0]["unknown"] = True
    with pytest.raises(SchemaValidationError, match="unknown"):
        _validate_manifest(mutated, schema)


def test_changed_provenance_wording_is_rejected(schema: dict[str, Any]) -> None:
    mutated = copy.deepcopy(schema)
    mutated["x-authorityCatalog"][0]["verbatim"] = "存在しない逐語"
    with pytest.raises(AssertionError, match="逐語"):
        _assert_authority_wording_exists(mutated)


def test_trigger_ten_material_records_intentional_layer_separation(
    schema: dict[str, Any],
) -> None:
    material = schema["x-triggerAssessmentMaterials"]["trigger10"]
    assert material["treatment"] == "intentional-top-level-separation"
    assert material["schemaLocation"] == "#/properties/propertyCatalog"
    assert material["basis"] == "ADR-003 D-11 3 層表 プロパティ層"


def test_trigger_eleven_material_records_manifest_and_contract_boundary(
    schema: dict[str, Any],
) -> None:
    material = schema["x-triggerAssessmentMaterials"]["trigger11"]
    assert material["basis"] == "ADR-003 D-6 契約分類"
    assert len(material["manifestRequires"]) == 3
    assert len(material["delegatesToContracts"]) == 3
    assert any("vectors[]" in item for item in material["manifestRequires"])
    assert any("TSK-236〜TSK-239" in item for item in material["delegatesToContracts"])


@pytest.mark.parametrize("target_class", ["alpha", "beta-1-5", "beta-7"])
def test_valid_synthetic_manifest_is_accepted(
    tmp_path: Path, schema: dict[str, Any], target_class: str
) -> None:
    _write_and_validate(tmp_path, _manifest(target_class), schema)
