"""ADR-003 D-1 正本の射程行に閉じた宣言モデル schema を検査する。"""

from __future__ import annotations

import copy
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODEL_SCHEMA_PATH = ROOT / "backend/domain/model.schema.json"
VOCABULARY_SCHEMA_PATH = ROOT / "backend/domain/vocabulary.schema.json"
BACKEND_SRC = ROOT / "backend/src"
EXPECTED_SCOPE_ELEMENTS = {
    "state",
    "event",
    "guard",
    "next-state",
    "integer",
    "boolean",
    "enum",
    "add",
    "subtract",
    "multiply",
    "divide",
    "comparison",
    "min",
    "max",
    "explicit-rounding",
    "finite-reducer",
    "input-type",
    "input-range",
    "input-unit",
    "input-scale",
    "output-type",
    "output-range",
    "output-unit",
    "output-scale",
    "nullable",
    "enum-display-map",
    "declarative-display-rule",
}
EXPECTED_VOCABULARY_REFS = {
    "vocabulary.schema.json",
    "vocabulary.schema.json#/$defs/NumericValue",
    "vocabulary.schema.json#/$defs/DisplayAtom",
    "vocabulary.schema.json#/$defs/ResolvedName",
}
FORBIDDEN_DUPLICATE_DEFINITIONS = {
    "DisplayAtom",
    "DisplayAtomSource",
    "DisplayTemplate",
    "EnumDisplayMap",
    "NumericDisplayPrimitive",
    "NumericPrimitive",
    "NumericValue",
    "ResolvedName",
}


class SchemaValidationError(AssertionError):
    """合成宣言モデルが schema に適合しないことを表す。"""


@pytest.fixture(scope="module")
def model_schema() -> dict[str, Any]:
    """宣言モデル schema を読み込む。"""
    return json.loads(MODEL_SCHEMA_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def vocabulary_schema() -> dict[str, Any]:
    """表示語彙 schema を読み込む。"""
    return json.loads(VOCABULARY_SCHEMA_PATH.read_text(encoding="utf-8"))


def _resolve_pointer(document: dict[str, Any], pointer: str) -> Any:
    """JSON Pointer を指定文書内で解決する。"""
    if pointer in {"", "#"}:
        return document
    if not pointer.startswith("#/"):
        raise SchemaValidationError(f"不正な JSON Pointer: {pointer}")
    node: Any = document
    for raw_token in pointer[2:].split("/"):
        token = raw_token.replace("~1", "/").replace("~0", "~")
        try:
            node = node[token]
        except (KeyError, TypeError) as error:
            raise SchemaValidationError(f"解決できない JSON Pointer: {pointer}") from error
    return node


def _resolve_ref(
    reference: str,
    document: dict[str, Any],
    vocabulary: dict[str, Any],
) -> tuple[Any, dict[str, Any]]:
    """ローカル参照または表示語彙への外部参照を解決する。"""
    if reference.startswith("#"):
        return _resolve_pointer(document, reference), document
    if reference == "vocabulary.schema.json":
        return vocabulary, vocabulary
    prefix = "vocabulary.schema.json#"
    if reference.startswith(prefix):
        pointer = f"#{reference.removeprefix(prefix)}"
        return _resolve_pointer(vocabulary, pointer), vocabulary
    raise SchemaValidationError(f"許可されない外部参照: {reference}")


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
            raise SchemaValidationError(f"テスト検証器が未対応の型: {expected}")


def _validate(
    instance: Any,
    node: Any,
    document: dict[str, Any],
    vocabulary: dict[str, Any],
    path: str = "$",
) -> None:
    """本資産が使う JSON Schema 語彙を検証する。"""
    if node is True:
        return
    if node is False or not isinstance(node, dict):
        raise SchemaValidationError(f"{path}: 不正な schema node")
    if "$ref" in node:
        resolved, resolved_document = _resolve_ref(
            node["$ref"], document, vocabulary
        )
        _validate(instance, resolved, resolved_document, vocabulary, path)
        return
    if "oneOf" in node:
        matched = 0
        for branch in node["oneOf"]:
            try:
                _validate(instance, branch, document, vocabulary, path)
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
    if isinstance(instance, int) and not isinstance(instance, bool):
        if instance < node.get("minimum", instance):
            raise SchemaValidationError(f"{path}: minimum に不適合")
        if instance > node.get("maximum", instance):
            raise SchemaValidationError(f"{path}: maximum に不適合")
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
        additional = node.get("additionalProperties", True)
        unknown = set(instance) - set(properties)
        if additional is False and unknown:
            raise SchemaValidationError(f"{path}: 未知キー {sorted(unknown)!r}")
        for key, value in instance.items():
            if key in properties:
                _validate(value, properties[key], document, vocabulary, f"{path}.{key}")
            elif isinstance(additional, dict):
                _validate(value, additional, document, vocabulary, f"{path}.{key}")
    if isinstance(instance, list):
        if len(instance) < node.get("minItems", 0):
            raise SchemaValidationError(f"{path}: minItems に不適合")
        if "maxItems" in node and len(instance) > node["maxItems"]:
            raise SchemaValidationError(f"{path}: maxItems に不適合")
        canonical = [
            json.dumps(item, ensure_ascii=False, sort_keys=True) for item in instance
        ]
        if node.get("uniqueItems") and len(canonical) != len(set(canonical)):
            raise SchemaValidationError(f"{path}: uniqueItems に不適合")
        unique_key = node.get("x-uniqueBy")
        if isinstance(unique_key, str):
            values = [item.get(unique_key) for item in instance if isinstance(item, dict)]
            if len(values) != len(instance) or len(values) != len(set(values)):
                raise SchemaValidationError(f"{path}: {unique_key} が重複")
        if "items" in node:
            for index, value in enumerate(instance):
                _validate(
                    value,
                    node["items"],
                    document,
                    vocabulary,
                    f"{path}[{index}]",
                )


def _integer(value: int) -> dict[str, object]:
    """構造化整数を返す。"""
    return {"kind": "integer", "value": value}


def _field(
    field_id: str,
    kind: str = "integer",
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> dict[str, object]:
    """合成の入出力または状態フィールドを返す。"""
    value_range = None
    if minimum is not None and maximum is not None:
        value_range = {"minimum": _integer(minimum), "maximum": _integer(maximum)}
    return {
        "fieldId": field_id,
        "type": {"kind": kind},
        "nullable": False,
        "range": value_range,
        "unit": "point" if kind == "integer" else None,
        "scale": 0 if kind == "integer" else None,
    }


@pytest.fixture
def valid_model() -> dict[str, Any]:
    """状態遷移と有限集計を含む合成宣言モデルを返す。"""
    visible_output = _field("visibleMetric", minimum=0, maximum=999)
    visible_output["visibility"] = "user-visible"
    internal_output = _field("auditFlag", "boolean")
    internal_output["visibility"] = "internal"
    return {
        "schemaVersion": 1,
        "calculations": [
            {
                "calculationId": "syntheticCalculation",
                "inputs": [_field("delta", minimum=0, maximum=99)],
                "states": [
                    {
                        "stateId": "scoreState",
                        "fields": [_field("total", minimum=0, maximum=999)],
                    }
                ],
                "events": [
                    {
                        "eventId": "advance",
                        "fields": [_field("amount", minimum=0, maximum=99)],
                    }
                ],
                "rules": [
                    {
                        "kind": "guard",
                        "ruleId": "positiveDelta",
                        "expression": {
                            "kind": "comparison",
                            "operator": "greater-than",
                            "left": {"kind": "input-ref", "fieldRef": "delta"},
                            "right": {"kind": "numeric-literal", "value": _integer(0)},
                        },
                    },
                    {
                        "kind": "transition",
                        "ruleId": "applyAdvance",
                        "eventRef": "advance",
                        "guardRefs": ["positiveDelta"],
                        "nextState": [
                            {
                                "fieldRef": "total",
                                "value": {
                                    "kind": "arithmetic",
                                    "operator": "add",
                                    "operands": [
                                        {"kind": "state-ref", "fieldRef": "total"},
                                        {"kind": "event-ref", "fieldRef": "amount"},
                                    ],
                                },
                            }
                        ],
                    },
                    {
                        "kind": "reducer",
                        "ruleId": "boundedTotal",
                        "sourceRef": "events",
                        "maximumItems": 100,
                        "initial": _integer(0),
                        "expression": {
                            "kind": "arithmetic",
                            "operator": "add",
                            "operands": [
                                {"kind": "accumulator-ref", "fieldRef": "total"},
                                {"kind": "item-ref", "fieldRef": "amount"},
                            ],
                        },
                    },
                ],
                "outputs": [visible_output, internal_output],
                "displayRuleRefs": ["wholeNumber"],
            }
        ],
        "displayRules": [
            {
                "kind": "numeric-primitive",
                "id": "wholeNumber",
                "primitive": {
                    "kind": "fixed-decimal",
                    "scale": 0,
                    "rounding": "half-up",
                    "leadingZero": True,
                    "sign": "negative-only-hyphen-minus",
                },
            }
        ],
    }


def _validate_model(
    model: dict[str, Any],
    schema: dict[str, Any],
    vocabulary: dict[str, Any],
) -> None:
    """合成宣言モデルを外部語彙参照込みで検証する。"""
    _validate(model, schema, schema, vocabulary)


def _assert_scope_elements(candidate: dict[str, Any]) -> None:
    """D-1 射程の母集合と schema 対応が過不足ないことを検査する。"""
    scope = candidate["x-pitchlog"]["scopeElements"]
    identifiers = [item["id"] for item in scope]
    assert len(identifiers) == 27
    assert len(identifiers) == len(set(identifiers))
    assert set(identifiers) == EXPECTED_SCOPE_ELEMENTS
    for item in scope:
        reference = item["schema"]
        if reference.startswith("vocabulary.schema.json"):
            continue
        _resolve_pointer(candidate, reference)


def _section_text(source_text: str, heading: str) -> str:
    """指定見出しに属する本文を取り出す。"""
    lines = source_text.splitlines()
    try:
        start = lines.index(heading)
    except ValueError as error:
        raise AssertionError(f"正本に節見出しがない: {heading}") from error
    level = len(heading) - len(heading.lstrip("#"))
    end = len(lines)
    for index in range(start + 1, len(lines)):
        match = re.match(r"^(#+)\s", lines[index])
        if match is not None and len(match.group(1)) <= level:
            end = index
            break
    return "\n".join(lines[start:end])


def _external_refs(value: object) -> set[str]:
    """Schema 木に実在する表示語彙への外部参照を集める。"""
    refs: set[str] = set()
    if isinstance(value, dict):
        reference = value.get("$ref")
        if isinstance(reference, str) and reference.startswith("vocabulary.schema.json"):
            refs.add(reference)
        for child in value.values():
            refs.update(_external_refs(child))
    elif isinstance(value, list):
        for child in value:
            refs.update(_external_refs(child))
    return refs


def _assert_vocabulary_reuse(candidate: dict[str, Any]) -> None:
    """表示語彙が外部参照だけであり二重定義されていないことを検査する。"""
    declared = set(candidate["x-pitchlog"]["vocabularyReferences"])
    actual = _external_refs(candidate)
    assert declared - actual == set(), f"未使用の表示語彙参照: {declared - actual}"
    assert actual - declared == set(), f"未宣言の表示語彙参照: {actual - declared}"
    assert declared == EXPECTED_VOCABULARY_REFS
    duplicates = set(candidate["$defs"]) & FORBIDDEN_DUPLICATE_DEFINITIONS
    assert duplicates == set(), f"表示語彙を二重定義している: {duplicates}"


def _visible_numeric_targets(
    model: dict[str, Any], schema: dict[str, Any]
) -> set[str]:
    """Schema 自身が宣言した selector で可視数値出力を選ぶ。"""
    selector = schema["x-pitchlog"]["targetFieldSelectors"][0]
    targets: set[str] = set()
    for calculation in model["calculations"]:
        for output in calculation["outputs"]:
            if (
                output[selector["visibilityProperty"]] == selector["visibleValue"]
                and output["type"]["kind"] in selector["numericTypeKinds"]
            ):
                targets.add(output[selector["fieldIdProperty"]])
    return targets


def test_d_one_scope_has_exactly_twenty_seven_schema_elements(
    model_schema: dict[str, Any],
) -> None:
    _assert_scope_elements(model_schema)


def test_removing_each_scope_element_is_rejected(model_schema: dict[str, Any]) -> None:
    attempts = 0
    for index in range(len(EXPECTED_SCOPE_ELEMENTS)):
        changed = copy.deepcopy(model_schema)
        del changed["x-pitchlog"]["scopeElements"][index]
        with pytest.raises(AssertionError):
            _assert_scope_elements(changed)
        attempts += 1
    assert attempts == 27


def test_d_one_authority_wording_exists_in_named_section(
    model_schema: dict[str, Any],
) -> None:
    catalog = model_schema["x-authorityCatalog"]
    entry = next(item for item in catalog if item["id"] == "ADR-003 D-1 正本の射程行")
    section = _section_text(
        (ROOT / entry["source"]).read_text(encoding="utf-8"), entry["section"]
    )
    assert entry["verbatim"] in section


def test_conditional_declaration_is_rejected(
    valid_model: dict[str, Any],
    model_schema: dict[str, Any],
    vocabulary_schema: dict[str, Any],
) -> None:
    changed = copy.deepcopy(valid_model)
    changed["calculations"][0]["rules"].append(
        {"kind": "condition", "ruleId": "branch", "if": True}
    )
    with pytest.raises(SchemaValidationError):
        _validate_model(changed, model_schema, vocabulary_schema)


def test_substring_operation_is_rejected(
    valid_model: dict[str, Any],
    model_schema: dict[str, Any],
    vocabulary_schema: dict[str, Any],
) -> None:
    changed = copy.deepcopy(valid_model)
    changed["calculations"][0]["rules"][0]["expression"] = {
        "kind": "substring",
        "value": {"kind": "input-ref", "fieldRef": "delta"},
    }
    with pytest.raises(SchemaValidationError):
        _validate_model(changed, model_schema, vocabulary_schema)


def test_undeclared_numeric_formatting_is_rejected(
    valid_model: dict[str, Any],
    model_schema: dict[str, Any],
    vocabulary_schema: dict[str, Any],
) -> None:
    changed = copy.deepcopy(valid_model)
    changed["calculations"][0]["rules"][1]["nextState"][0]["value"] = {
        "kind": "format-number",
        "scale": 2,
        "value": {"kind": "state-ref", "fieldRef": "total"},
    }
    with pytest.raises(SchemaValidationError):
        _validate_model(changed, model_schema, vocabulary_schema)


def test_output_visibility_and_type_define_the_numeric_target_closure(
    valid_model: dict[str, Any], model_schema: dict[str, Any]
) -> None:
    before = _visible_numeric_targets(valid_model, model_schema)
    changed = copy.deepcopy(valid_model)
    future_output = _field("futureMetric", minimum=0, maximum=9)
    future_output["visibility"] = "user-visible"
    changed["calculations"][0]["outputs"].append(future_output)
    after = _visible_numeric_targets(changed, model_schema)

    assert before == {"visibleMetric"}
    assert after - before == {"futureMetric"}
    assert len(after) == len(before) + 1


def test_vocabulary_is_referenced_without_duplicate_definitions(
    model_schema: dict[str, Any],
) -> None:
    _assert_vocabulary_reuse(model_schema)


def test_duplicate_vocabulary_definition_is_rejected(
    model_schema: dict[str, Any], vocabulary_schema: dict[str, Any]
) -> None:
    changed = copy.deepcopy(model_schema)
    changed["$defs"]["NumericValue"] = copy.deepcopy(
        vocabulary_schema["$defs"]["NumericValue"]
    )
    with pytest.raises(AssertionError):
        _assert_vocabulary_reuse(changed)


def test_valid_state_transition_model_is_accepted(
    valid_model: dict[str, Any],
    model_schema: dict[str, Any],
    vocabulary_schema: dict[str, Any],
) -> None:
    _validate_model(valid_model, model_schema, vocabulary_schema)


def test_step_twelve_collector_derives_complete_nonempty_closure() -> None:
    process = subprocess.run(
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
    result = json.loads(process.stdout)

    assert process.returncode == 0, process.stderr
    assert result["schemaClosure"]["complete"] is True
    assert result["schemaClosure"]["targetFields"] == [
        "calculation-output-user-visible-numeric"
    ]
    materials = {
        item["construct"]: item
        for item in result["trigger1AssessmentMaterials"]["items"]
    }
    assert len(materials) == 5
    assert all(item["representable"] is True for item in materials.values())
