"""生成コアの前段に置く5系統の意味検査を検証する。"""

from __future__ import annotations

import copy
import importlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
BACKEND_SRC = ROOT / "backend/src"

sys.path.insert(0, str(BACKEND_SRC))
CORE = importlib.import_module("pitchlog.domaingen.core")
PREGEN = importlib.import_module("pitchlog.domaingen.pregen_checks")
BACKENDS = importlib.import_module("pitchlog.domaingen.backends")

HASH = f"sha256:{'0' * 64}"
CHECK_IDS = tuple(sorted(PREGEN.CHECK_IDS, key=lambda item: item.value))


@pytest.fixture(scope="module")
def schemas() -> Any:
    """既存の宣言モデル・マニフェスト・語彙 schema を返す。"""
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
    """有限範囲を持つ整数フィールドを返す。"""
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
    """5系統をすべて満たす合成宣言モデルを返す。"""
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


def _generated(generated_id: str, artifact_kind: str) -> dict[str, str]:
    """合成生成物の宣言を返す。"""
    return {
        "generatedId": generated_id,
        "path": f"synthetic/generated/{generated_id}.txt",
        "artifactKind": artifact_kind,
    }


def _manifest() -> dict[str, Any]:
    """合成宣言モデルに対応する α マニフェストを返す。"""
    calculation_id = "syntheticCalculation"
    generated = _generated("synthetic-python", "python")
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
                "generated": [generated],
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
                        "targetClass": "alpha",
                        "kind": "single",
                        "generated": generated["generatedId"],
                        "hash": HASH,
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
                        "target": generated["path"],
                        "operators": ["replace-constant"],
                    }
                ],
            }
        ],
        "displayBindings": [
            {
                "displayItem": "synthetic-visible-metric",
                "callsite": "synthetic/product.py",
                "formatter": "wholeNumber",
                "provenance": "ADR-003 D-11 構成の完全性",
            }
        ],
    }


def _invalid_model(check_id: Any) -> dict[str, Any]:
    """指定した1系統だけに違反する宣言モデルを返す。"""
    model = _model()
    calculation = model["calculations"][0]
    if check_id is PREGEN.CheckId.TRANSITIONS:
        duplicate = copy.deepcopy(calculation["rules"][0])
        duplicate["ruleId"] = "applyAdvanceAgain"
        calculation["rules"].append(duplicate)
    elif check_id is PREGEN.CheckId.TYPES_AND_RANGES:
        state_field = calculation["states"][0]["fields"][0]
        state_field["range"] = {
            "minimum": _integer(10),
            "maximum": _integer(1),
        }
    elif check_id is PREGEN.CheckId.DIVISION_ROUNDING:
        numeric_value_type = {
            "kind": "numeric-value",
            "valueSchema": "vocabulary.schema.json#/$defs/NumericValue",
        }
        calculation["states"][0]["fields"][0]["type"] = numeric_value_type
        calculation["events"][0]["fields"][0]["type"] = copy.deepcopy(
            numeric_value_type
        )
        value = calculation["rules"][0]["nextState"][0]["value"]
        value["operator"] = "divide"
    elif check_id is PREGEN.CheckId.DISPLAY_PARAMETERS:
        del model["displayRules"][0]["primitive"]["sign"]
    elif check_id is PREGEN.CheckId.DISPLAY_ATOM_BOUNDARY:
        calculation["displayRuleRefs"] = ["badTemplate"]
        model["displayRules"] = [
            {
                "kind": "template",
                "id": "badTemplate",
                "pattern": "{score}",
                "placeholders": {
                    "score": {"kind": "integer", "value": 7},
                },
            }
        ]
    else:
        raise AssertionError(f"未対応の検査 ID: {check_id}")
    return model


def test_check_population_is_exactly_five(schemas: Any) -> None:
    report = PREGEN.run_pregen_checks(_model(), schemas)

    assert len(PREGEN.CHECK_IDS) == 5
    assert len(report.attempted) == 5
    assert report.attempted == PREGEN.CHECK_IDS
    assert report.passed


@pytest.mark.parametrize("check_id", CHECK_IDS, ids=lambda item: item.value)
def test_each_invalid_declaration_fails_its_own_check(
    check_id: Any,
    schemas: Any,
) -> None:
    report = PREGEN.run_pregen_checks(_invalid_model(check_id), schemas)
    failed_checks = {violation.check_id for violation in report.violations}

    assert failed_checks == {check_id}
    assert not report.passed


@pytest.mark.parametrize("check_id", CHECK_IDS, ids=lambda item: item.value)
def test_removing_each_check_allows_its_invalid_declaration_to_generate(
    check_id: Any,
    schemas: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = _invalid_model(check_id)

    with pytest.raises(PREGEN.PregenCheckError) as caught:
        PREGEN.generate_checked(
            model,
            _manifest(),
            schemas,
            ROOT,
        )
    assert {item.check_id for item in caught.value.report.violations} == {check_id}

    remaining = {
        candidate: check
        for candidate, check in PREGEN._CHECKS.items()
        if candidate is not check_id
    }
    reached_generation: list[dict[str, Any]] = []

    def generation_spy(
        candidate_model: dict[str, Any],
        manifest: dict[str, Any],
        source_schemas: Any,
        root: Path,
    ) -> dict[str, object]:
        """生成コアへ到達した入力を記録する。"""
        del manifest, source_schemas, root
        reached_generation.append(candidate_model)
        return {"calculations": []}

    monkeypatch.setattr(PREGEN, "_CHECKS", remaining)
    monkeypatch.setattr(
        PREGEN.core,
        "generate_intermediate_representation",
        generation_spy,
    )
    intermediate = PREGEN.generate_checked(
        model,
        _manifest(),
        schemas,
        ROOT,
    )

    assert len(remaining) == 4
    assert reached_generation == [model]
    assert intermediate == {"calculations": []}


def test_display_parameter_set_is_derived_from_vocabulary_schema(schemas: Any) -> None:
    vocabulary = copy.deepcopy(schemas.vocabulary)
    fixed_decimal = vocabulary["$defs"]["FixedDecimal"]
    fixed_decimal["required"].append("futureParameter")
    changed_schemas = CORE.SourceSchemas(
        model=schemas.model,
        manifest=schemas.manifest,
        vocabulary=vocabulary,
    )

    report = PREGEN.run_pregen_checks(_model(), changed_schemas)

    assert {item.check_id for item in report.violations} == {
        PREGEN.CheckId.DISPLAY_PARAMETERS
    }
    assert "futureParameter" in report.violations[0].message


def test_valid_declaration_passes_all_checks_and_reaches_generation(
    schemas: Any,
) -> None:
    intermediate = PREGEN.generate_checked(
        _model(),
        _manifest(),
        schemas,
        ROOT,
    )
    artifacts = BACKENDS.generate_language_artifacts(intermediate)

    assert intermediate["calculations"]
    assert {artifact.language.value for artifact in artifacts} == {
        "python",
        "typescript",
    }
