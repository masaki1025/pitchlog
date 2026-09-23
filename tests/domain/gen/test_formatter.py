"""表示 formatter・参照実装・β⑦受け口の生成を検査する。"""

from __future__ import annotations

import ast
import copy
import dataclasses
import hashlib
import importlib
import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest

ROOT = Path(__file__).resolve().parents[3]
BACKEND_SRC = ROOT / "backend/src"
FORMATTER_SOURCE = BACKEND_SRC / "pitchlog/domaingen/formatter.py"
REVIEW_TRIGGERS = ROOT / "backend/domain/review-triggers.json"
EXPECTED_TARGET_CLASSES = {"alpha", "beta-1-5", "beta-7", "beta-6-8"}

sys.path.insert(0, str(BACKEND_SRC))
CORE = importlib.import_module("pitchlog.domaingen.core")
FORMATTER = importlib.import_module("pitchlog.domaingen.formatter")


@pytest.fixture(scope="module")
def schemas() -> Any:
    """中間表現の検証に使う既存 schema を返す。"""
    return CORE.SourceSchemas(
        model=_read_json(ROOT / "backend/domain/model.schema.json"),
        manifest=_read_json(ROOT / "backend/domain/manifest.schema.json"),
        vocabulary=_read_json(ROOT / "backend/domain/vocabulary.schema.json"),
    )


def _read_json(path: Path) -> dict[str, Any]:
    """JSON object を読み込む。"""
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _integer(value: int) -> dict[str, object]:
    """構造化整数を返す。"""
    return {"kind": "integer", "value": value}


def _field(field_id: str) -> dict[str, object]:
    """合成宣言の整数フィールドを返す。"""
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


def _declaration(calculation_id: str, display_rule_id: str) -> dict[str, object]:
    """表示規則を参照する状態遷移宣言を返す。"""
    output = _field("visibleMetric")
    output["visibility"] = "user-visible"
    return {
        "calculationId": calculation_id,
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
        "displayRuleRefs": [display_rule_id],
    }


def _hash(character: str) -> str:
    """識別しやすい段別 hash を返す。"""
    return f"sha256:{character * 64}"


def _stage(name: str, generated_id: str, character: str) -> dict[str, str]:
    """ステップ 26 と同じキー集合の IR 段を返す。"""
    return {
        "stage": name,
        "generatedId": generated_id,
        "sourceHash": _hash(character),
    }


def _calculation(
    target_class: str,
    kind: str,
    stages: list[dict[str, str]],
    display_rule_id: str,
) -> dict[str, object]:
    """指定区分と表示規則を持つ中間表現の計算要素を返す。"""
    calculation_id = f"synthetic-{target_class}"
    return {
        "calculationId": calculation_id,
        "sourceId": "ADR-003 D-11 構成の完全性",
        "declaration": _declaration(calculation_id, display_rule_id),
        "targets": [
            {
                "directTargetId": f"{calculation_id}-direct",
                "targetClass": target_class,
                "kind": kind,
                "stages": stages,
                "invocation": {
                    "adapter": f"synthetic/adapters/{calculation_id}.py",
                    "operation": "execute",
                },
            }
        ],
    }


def _intermediate() -> dict[str, Any]:
    """表示規則と全 target matrix を持つ中間表現を返す。"""
    return {
        "schemaVersion": 1,
        "generatorVersion": CORE.GENERATOR_VERSION,
        "displayRules": [
            {
                "kind": "numeric-primitive",
                "id": "oneDecimal",
                "primitive": {
                    "kind": "fixed-decimal",
                    "scale": 1,
                    "rounding": "half-up",
                    "leadingZero": True,
                    "sign": "negative-only-hyphen-minus",
                },
            },
            {
                "kind": "enum-map",
                "id": "sideName",
                "enumId": "side",
                "stability": "stable",
                "managedBy": "system",
                "members": [
                    {"value": "home", "display": "ホーム"},
                    {"value": "away", "display": "ビジター"},
                ],
            },
        ],
        "calculations": [
            _calculation(
                "alpha",
                "single",
                [_stage("python", "alpha-core", "a")],
                "oneDecimal",
            ),
            _calculation(
                "beta-1-5",
                "composite",
                [
                    _stage("sql", "beta-aggregate-sql", "b"),
                    _stage("typed-receiver", "beta-aggregate-receiver", "c"),
                    _stage("formatter", "beta-aggregate-formatter", "d"),
                ],
                "oneDecimal",
            ),
            _calculation(
                "beta-7",
                "composite",
                [
                    _stage("sql", "beta-classification-sql", "e"),
                    _stage("typed-receiver", "beta-classification-receiver", "f"),
                ],
                "sideName",
            ),
            _calculation(
                "beta-6-8",
                "single",
                [_stage("python", "beta-python", "1")],
                "oneDecimal",
            ),
        ],
    }


def _artifacts(schemas: Any) -> tuple[Any, ...]:
    """検証済み中間表現から表示生成物を返す。"""
    intermediate = _intermediate()
    CORE.validate_intermediate_representation(intermediate, schemas)
    return FORMATTER.generate_display_artifacts(intermediate)


def _artifact(
    artifacts: tuple[Any, ...],
    target_class: str,
    language: str,
    purpose: str,
) -> Any:
    """条件に一致する表示生成物を一意に返す。"""
    matches = [
        artifact
        for artifact in artifacts
        if artifact.target_class == target_class
        and artifact.language.value == language
        and artifact.purpose.value == purpose
    ]
    assert len(matches) == 1
    return matches[0]


def _execute_python(
    artifact: Any,
    function_name: str,
    module_name: str,
) -> Callable[..., object]:
    """生成 Python を指定ラッパー名でロードして関数を返す。"""
    namespace: dict[str, object] = {"__name__": module_name}
    exec(compile(artifact.content, "<generated-display>", "exec"), namespace)
    function = namespace[function_name]
    assert callable(function)
    return cast(Callable[..., object], function)


def _tree_snapshot(root: Path) -> tuple[tuple[str, str], ...]:
    """ディレクトリ配下の相対パスと内容 hash を返す。"""
    if not root.exists():
        return ()
    values: list[tuple[str, str]] = []
    for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        values.append((path.relative_to(root).as_posix(), digest))
    return tuple(values)


def test_reference_implementations_have_regenerable_provenance(schemas: Any) -> None:
    intermediate = _intermediate()
    references = [
        artifact
        for artifact in _artifacts(schemas)
        if artifact.purpose is FORMATTER.DisplayPurpose.REFERENCE
    ]

    assert len(references) == len(EXPECTED_TARGET_CLASSES) == 4
    assert all(
        FORMATTER.verify_generated_provenance(artifact, intermediate)
        for artifact in references
    )
    assert all(
        artifact.provenance.generator_id
        == "pitchlog.domaingen.formatter.generate_display_artifacts"
        for artifact in references
    )


def test_handwritten_reference_without_generator_match_is_rejected(
    schemas: Any,
) -> None:
    intermediate = _intermediate()
    reference = _artifact(
        _artifacts(schemas),
        "alpha",
        "python",
        "property-reference",
    )
    handwritten = dataclasses.replace(
        reference,
        content=reference.content + "# 手書き変更\n",
    )
    false_marker = dataclasses.replace(
        reference,
        provenance=dataclasses.replace(
            reference.provenance,
            generator_id="handwritten.reference",
        ),
    )

    assert not FORMATTER.verify_generated_provenance(handwritten, intermediate)
    assert not FORMATTER.verify_generated_provenance(false_marker, intermediate)


def test_changed_declaration_invalidates_old_generated_provenance(schemas: Any) -> None:
    intermediate = _intermediate()
    reference = _artifact(
        _artifacts(schemas),
        "alpha",
        "python",
        "property-reference",
    )
    changed = copy.deepcopy(intermediate)
    changed["displayRules"][0]["primitive"]["scale"] = 2

    assert not FORMATTER.verify_generated_provenance(reference, changed)


def test_alpha_python_typescript_and_reference_return_same_display(
    schemas: Any,
) -> None:
    artifacts = _artifacts(schemas)
    python_formatter = _artifact(artifacts, "alpha", "python", "formatter")
    typescript_formatter = _artifact(artifacts, "alpha", "typescript", "formatter")
    reference = _artifact(
        artifacts,
        "alpha",
        "python",
        "property-reference",
    )
    value = {"kind": "rational", "numerator": 5, "denominator": 4}
    python_function = _execute_python(
        python_formatter,
        "_pitchlog_format",
        "__pitchlog_generated_wrapper__",
    )
    reference_function = _execute_python(
        reference,
        "_pitchlog_reference",
        "__pitchlog_property_reference__",
    )
    typescript_script = "\n".join(
        [
            "globalThis.__PITCHLOG_GENERATED_WRAPPER__ = true;",
            typescript_formatter.content,
            f"console.log(pitchlogFormat('oneDecimal', {json.dumps(value)}));",
        ]
    )
    typescript_result = subprocess.run(
        ["node", "--input-type=module", "--eval", typescript_script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert typescript_result.returncode == 0, typescript_result.stderr
    assert python_function("oneDecimal", value) == "1.3"
    assert reference_function("oneDecimal", value) == "1.3"
    assert typescript_result.stdout.strip() == "1.3"


def test_reference_implementation_generates_through_display_string(
    schemas: Any,
) -> None:
    reference = _artifact(
        _artifacts(schemas),
        "beta-1-5",
        "python",
        "property-reference",
    )
    function = _execute_python(
        reference,
        "_pitchlog_reference",
        "__pitchlog_property_reference__",
    )
    displayed = function(
        "oneDecimal",
        {"kind": "exact-decimal", "value": "2.25"},
    )

    assert displayed == "2.3"
    assert isinstance(displayed, str)


def test_beta_seven_enum_map_receiver_and_reference_agree(schemas: Any) -> None:
    artifacts = _artifacts(schemas)
    receiver = _artifact(
        artifacts,
        "beta-7",
        "python",
        "enum-map-receiver",
    )
    reference = _artifact(
        artifacts,
        "beta-7",
        "python",
        "property-reference",
    )
    receiver_function = _execute_python(
        receiver,
        "_pitchlog_generated",
        "__pitchlog_generated_wrapper__",
    )
    reference_function = _execute_python(
        reference,
        "_pitchlog_reference",
        "__pitchlog_property_reference__",
    )

    receiver_display = receiver_function(
        {"value": "home"},
        {"home": "ホーム", "away": "ビジター"},
    )
    reference_display = reference_function("sideName", "home")
    assert receiver_display == reference_display == "ホーム"


def test_reference_is_not_connected_to_product_paths() -> None:
    tree = ast.parse(FORMATTER_SOURCE.read_text(encoding="utf-8"))
    called_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    product_sources = [ROOT / "backend/src/pitchlog/main.py"]
    for directory in ("api", "authz", "db"):
        product_sources.extend(
            (ROOT / f"backend/src/pitchlog/{directory}").rglob("*.py")
        )

    assert "open" not in called_names
    assert "write_text" not in called_names
    for path in product_sources:
        source = path.read_text(encoding="utf-8")
        assert "pitchlog.domaingen.formatter" not in source


def test_generated_outputs_write_neither_product_paths_nor_contracts(
    schemas: Any,
) -> None:
    watched = (ROOT / "backend/src/pitchlog", ROOT / "frontend", ROOT / "contracts")
    before = tuple(_tree_snapshot(path) for path in watched)

    artifacts = _artifacts(schemas)

    after = tuple(_tree_snapshot(path) for path in watched)
    assert artifacts
    assert after == before


def test_all_target_matrix_classes_are_actually_generated(schemas: Any) -> None:
    intermediate = _intermediate()
    CORE.validate_intermediate_representation(intermediate, schemas)

    evaluation = FORMATTER.evaluate_target_matrix(intermediate)

    assert len(evaluation.expected) == 4
    assert evaluation.expected == EXPECTED_TARGET_CLASSES
    assert evaluation.generated == evaluation.expected
    assert evaluation.failures == ()
    assert evaluation.complete


def test_missing_matrix_class_is_detected(schemas: Any) -> None:
    intermediate = _intermediate()
    intermediate["calculations"] = [
        calculation
        for calculation in intermediate["calculations"]
        if calculation["targets"][0]["targetClass"] != "beta-6-8"
    ]
    CORE.validate_intermediate_representation(intermediate, schemas)

    evaluation = FORMATTER.evaluate_target_matrix(intermediate)

    assert not evaluation.complete
    assert "beta-6-8" not in evaluation.generated
    assert any("beta-6-8" in failure for failure in evaluation.failures)


def test_trigger_three_record_matches_measured_matrix(schemas: Any) -> None:
    evaluation = FORMATTER.evaluate_target_matrix(_intermediate())
    asset = _read_json(REVIEW_TRIGGERS)
    trigger = next(item for item in asset["triggers"] if item["id"] == 3)

    assert trigger["evaluation"] == {"fired": not evaluation.complete}
    assert trigger["evidenceLocation"] == "tests/domain/gen/test_formatter.py"
