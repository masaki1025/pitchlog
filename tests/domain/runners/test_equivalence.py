"""Target matrix 四区分の等価性を要求 case 全件で検査する。"""

from __future__ import annotations

import ast
import copy
import dataclasses
import importlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
BACKEND_SRC = ROOT / "backend/src"
REQUIRED_CASES_PATH = ROOT / "backend/domain/required-cases.json"
TARGET_CLASSES = ("alpha", "beta-1-5", "beta-7", "beta-6-8")

sys.path.insert(0, str(BACKEND_SRC))
EQUIVALENCE = importlib.import_module(
    "pitchlog.domaincheck.runners.equivalence"
)
FORMATTER = importlib.import_module("pitchlog.domaingen.formatter")
PATH_MATCH = importlib.import_module("pitchlog.domaincheck.path_match")


def _read_json(path: Path) -> dict[str, Any]:
    """JSON object を UTF-8 で読む。"""
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


@pytest.fixture(scope="module")
def required_cases() -> dict[str, Any]:
    """ステップ 35 の独立導出済み要求 case 集合を返す。"""
    return _read_json(REQUIRED_CASES_PATH)


def _hash(character: str) -> str:
    """識別しやすい段別 hash を返す。"""
    return f"sha256:{character * 64}"


def _stage(name: str, generated_id: str, character: str) -> dict[str, str]:
    """一つの中間表現段を返す。"""
    return {
        "stage": name,
        "generatedId": generated_id,
        "sourceHash": _hash(character),
    }


def _calculation(
    calculation_id: str,
    target_class: str,
    display_rule_id: str,
    stages: list[dict[str, str]],
) -> dict[str, object]:
    """生成参照実装を得るための最小計算要素を返す。"""
    kind = "composite" if len(stages) > 1 else "single"
    return {
        "calculationId": calculation_id,
        "sourceId": "ADR-003 D-11 3 層表 プロパティ層",
        "declaration": {"displayRuleRefs": [display_rule_id]},
        "targets": [
            {
                "directTargetId": f"{calculation_id}Direct",
                "targetClass": target_class,
                "kind": kind,
                "stages": stages,
                "invocation": {
                    "adapter": f"synthetic/{calculation_id}.py",
                    "operation": "execute",
                },
            }
        ],
    }


@pytest.fixture(scope="module")
def intermediate() -> dict[str, Any]:
    """四区分の生成参照実装を持つ合成中間表現を返す。"""
    return {
        "schemaVersion": 1,
        "generatorVersion": "1.0.0",
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
                "syntheticAlpha",
                "alpha",
                "oneDecimal",
                [_stage("python", "alphaCore", "a")],
            ),
            _calculation(
                "syntheticBetaAggregate",
                "beta-1-5",
                "oneDecimal",
                [
                    _stage("sql", "aggregateSql", "b"),
                    _stage("typed-receiver", "aggregateReceiver", "c"),
                    _stage("formatter", "aggregateFormatter", "d"),
                ],
            ),
            _calculation(
                "syntheticBetaClassification",
                "beta-7",
                "sideName",
                [
                    _stage("sql", "classificationSql", "e"),
                    _stage("typed-receiver", "classificationReceiver", "f"),
                ],
            ),
            _calculation(
                "syntheticBetaPython",
                "beta-6-8",
                "oneDecimal",
                [_stage("python", "betaPython", "1")],
            ),
        ],
    }


def _calculation_id(target_class: str) -> str:
    """区分ごとの合成計算 ID を返す。"""
    return {
        "alpha": "syntheticAlpha",
        "beta-1-5": "syntheticBetaAggregate",
        "beta-7": "syntheticBetaClassification",
        "beta-6-8": "syntheticBetaPython",
    }[target_class]


def _reference(intermediate: dict[str, Any], target_class: str) -> Any:
    """指定区分の生成済み参照実装を一意に返す。"""
    references = [
        artifact
        for artifact in FORMATTER.generate_display_artifacts(intermediate)
        if artifact.target_class == target_class
        and artifact.purpose is FORMATTER.DisplayPurpose.REFERENCE
    ]
    assert len(references) == 1
    return references[0]


def _comparison(target_class: str) -> Any:
    """区分が要求する構造化・表示フィールドの比較面を返す。"""
    fields: list[Any] = []
    if target_class in {"alpha", "beta-1-5", "beta-6-8"}:
        fields.append(
            PATH_MATCH.FieldContract(
                "structuredValue",
                "structured",
                "json",
                False,
                None,
            )
        )
    if target_class in {"alpha", "beta-1-5", "beta-7"}:
        fields.append(
            PATH_MATCH.FieldContract(
                "displayValue",
                "display",
                "display-string",
                False,
                None,
            )
        )
    surface = (
        "structured-and-display"
        if any(field.role == "display" for field in fields)
        else "structured-only"
    )
    return PATH_MATCH.ComparisonContract(
        surface=surface,
        fields=tuple(fields),
        normalizations=frozenset({"total-order"}),
    )


def _target(intermediate: dict[str, Any], target_class: str) -> Any:
    """四区分の比較表に一致する runner 入力を返す。"""
    calculation = _calculation_id(target_class)
    left, right = EQUIVALENCE.comparison_pair(target_class)
    return EQUIVALENCE.EquivalenceTarget(
        target_class=target_class,
        calculation=calculation,
        vector="requiredDisplayCases",
        runner="pytest",
        entrypoint_id=f"{calculation}Entrypoint",
        direct_target_id=f"{calculation}Direct",
        left_implementation=left,
        right_implementation=right,
        comparison=_comparison(target_class),
        reference_artifact=_reference(intermediate, target_class),
    )


def _output(target_class: str, case_id: str) -> list[dict[str, object]]:
    """区分ごとの比較面を満たす決定的な合成出力を返す。"""
    row: dict[str, object] = {}
    if target_class in {"alpha", "beta-1-5", "beta-6-8"}:
        row["structuredValue"] = {"caseId": case_id, "value": 1}
    if target_class in {"alpha", "beta-1-5"}:
        row["displayValue"] = f"1.0:{case_id}"
    elif target_class == "beta-7":
        row["displayValue"] = f"区分名:{case_id}"
    return [row]


def _cases(
    required_cases: dict[str, Any],
    target_class: str,
) -> tuple[Any, ...]:
    """要求 case 全件について左右が一致する生出力を返す。"""
    return tuple(
        EQUIVALENCE.EquivalenceCase(
            case_id=item["id"],
            left_output=_output(target_class, item["id"]),
            right_output=_output(target_class, item["id"]),
        )
        for item in required_cases["requiredCases"]
    )


def _run(
    required_cases: dict[str, Any],
    intermediate: dict[str, Any],
    target_class: str,
    cases: tuple[Any, ...] | None = None,
    target: Any | None = None,
) -> Any:
    """既定の正しい値を補って一比較面を実行する。"""
    return EQUIVALENCE.run_equivalence(
        target=_target(intermediate, target_class) if target is None else target,
        cases=_cases(required_cases, target_class) if cases is None else cases,
        required_case_asset=required_cases,
        intermediate=intermediate,
    )


@pytest.mark.parametrize("target_class", TARGET_CLASSES)
def test_each_target_matrix_surface_rejects_equivalence_violation(
    target_class: str,
    required_cases: dict[str, Any],
    intermediate: dict[str, Any],
) -> None:
    """四つの比較面でそれぞれ一フィールドの不一致を拒否する。"""
    cases = list(_cases(required_cases, target_class))
    changed = copy.deepcopy(cases[0].right_output)
    field = "displayValue" if target_class in {"alpha", "beta-7"} else "structuredValue"
    changed[0][field] = "不一致"
    cases[0] = dataclasses.replace(cases[0], right_output=changed)

    with pytest.raises(EQUIVALENCE.EquivalenceRunError, match="等価性違反"):
        _run(required_cases, intermediate, target_class, tuple(cases))


@pytest.mark.parametrize("field", ["structuredValue", "displayValue"])
def test_beta_aggregate_keeps_structured_and_extends_to_display(
    field: str,
    required_cases: dict[str, Any],
    intermediate: dict[str, Any],
) -> None:
    """β①〜⑤では構造化段と最終表示段の不一致を個別に拒否する。"""
    cases = list(_cases(required_cases, "beta-1-5"))
    changed = copy.deepcopy(cases[0].left_output)
    changed[0][field] = "不一致"
    cases[0] = dataclasses.replace(cases[0], left_output=changed)

    with pytest.raises(EQUIVALENCE.EquivalenceRunError, match="等価性違反"):
        _run(required_cases, intermediate, "beta-1-5", tuple(cases))


def test_reference_must_have_regenerable_provenance(
    required_cases: dict[str, Any],
    intermediate: dict[str, Any],
) -> None:
    """生成器を通らない手書き参照実装を拒否する。"""
    target = _target(intermediate, "beta-7")
    handwritten = dataclasses.replace(
        target.reference_artifact,
        content=target.reference_artifact.content + "# 手書き変更\n",
    )
    changed_target = dataclasses.replace(target, reference_artifact=handwritten)

    with pytest.raises(EQUIVALENCE.EquivalenceRunError, match="生成由来"):
        _run(
            required_cases,
            intermediate,
            "beta-7",
            target=changed_target,
        )


def test_reference_is_separated_from_product_paths(
    required_cases: dict[str, Any],
    intermediate: dict[str, Any],
) -> None:
    """参照実装の配布形態と製品 import graph の分離を検査する。"""
    target = _target(intermediate, "beta-1-5")
    assert target.reference_artifact.delivery == "test-only-property-layer"

    product_sources = [ROOT / "backend/src/pitchlog/main.py"]
    for directory in ("api", "authz", "db"):
        product_sources.extend(
            (ROOT / f"backend/src/pitchlog/{directory}").rglob("*.py")
        )
    forbidden_modules = {
        "pitchlog.domaincheck.runners.equivalence",
        "pitchlog.domaingen.formatter",
    }
    for path in product_sources:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        }
        imported.update(
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        assert imported.isdisjoint(forbidden_modules)

    product_delivery = dataclasses.replace(
        target.reference_artifact,
        delivery="wrapper-only-fragment",
    )
    with pytest.raises(EQUIVALENCE.EquivalenceRunError, match="テスト専用経路"):
        _run(
            required_cases,
            intermediate,
            "beta-1-5",
            target=dataclasses.replace(
                target,
                reference_artifact=product_delivery,
            ),
        )


def test_missing_required_case_fails_coverage_before_comparison(
    required_cases: dict[str, Any],
    intermediate: dict[str, Any],
) -> None:
    """決定的な要求 case 集合を一件でも欠く比較を拒否する。"""
    cases = _cases(required_cases, "alpha")[1:]

    with pytest.raises(EQUIVALENCE.EquivalenceRunError, match="網羅しない"):
        _run(required_cases, intermediate, "alpha", cases)


def test_equivalent_implementations_pass_all_four_surfaces(
    required_cases: dict[str, Any],
    intermediate: dict[str, Any],
) -> None:
    """等価な二実装が要求 case 全件で四比較面を実際に完走する。"""
    reports = {
        target_class: _run(required_cases, intermediate, target_class)
        for target_class in TARGET_CLASSES
    }

    assert len(reports) == 4
    assert all(report.complete for report in reports.values())
    assert all(
        report.coverage.required == report.coverage.observed
        for report in reports.values()
    )
    assert all(report.comparison.complete for report in reports.values())
