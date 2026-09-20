"""典拠付き不変条件 runner が生成 case と実行証跡を検査することを示す。"""

from __future__ import annotations

import importlib
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
BACKEND_SRC = ROOT / "backend/src"
AUTHORITIES_PATH = ROOT / "backend/domain/step-authorities.json"
PROPERTIES_SOURCE = (
    BACKEND_SRC / "pitchlog/domaincheck/runners/properties.py"
)
ARTIFACT_HASH = f"sha256:{'7' * 64}"
CALCULATION = "syntheticInvariantCalculation"
DIRECT_TARGET = "syntheticInvariantTarget"

sys.path.insert(0, str(BACKEND_SRC))
COLLECTOR = importlib.import_module("pitchlog.domaincheck.collect_layers")
PROPERTIES = importlib.import_module(
    "pitchlog.domaincheck.runners.properties"
)


@pytest.fixture(scope="module")
def authorities() -> dict[str, Any]:
    """ステップ 3 の台帳から条項 ID の逐語位置を導出する。"""
    registry = json.loads(AUTHORITIES_PATH.read_text(encoding="utf-8"))
    return PROPERTIES.authorities_from_registry(registry)


def _object(value: object) -> dict[str, object] | None:
    """文字列キーの object だけを返す。"""
    if not isinstance(value, dict) or not all(
        isinstance(key, str) for key in value
    ):
        return None
    return value


def _count_is_nonnegative(value: object) -> bool:
    """計数が boolean でない非負整数であることを判定する。"""
    item = _object(value)
    if item is None:
        return False
    count = item.get("count")
    return (
        isinstance(count, int)
        and not isinstance(count, bool)
        and count >= 0
    )


def _empty_aggregate_has_null_and_completed_display(value: object) -> bool:
    """全欠損なら null と MINUS SIGN を含む完成表示値か判定する。"""
    item = _object(value)
    if item is None:
        return False
    if item.get("aggregateEmpty") is not True:
        return True
    expected = "−(0球)" if item.get("hasCompanion") is True else "−"
    return item.get("structured") is None and item.get("display") == expected


def _predicates() -> tuple[Any, ...]:
    """二つの独立な合成規範述語を返す。"""
    return (
        PROPERTIES.InvariantPredicate(
            property_id="countNonnegative",
            authority_id="ADR-003 D-11 3 層表 プロパティ層",
            evaluate=_count_is_nonnegative,
        ),
        PROPERTIES.InvariantPredicate(
            property_id="emptyAggregateDisplay",
            authority_id="付録A-1 表示書式の共通規定",
            evaluate=_empty_aggregate_has_null_and_completed_display,
        ),
    )


def _valid_cases() -> tuple[Any, ...]:
    """二つの述語を満たす生成 case を返す。"""
    return (
        PROPERTIES.InvariantCase(
            "ordinaryCase",
            {
                "count": 3,
                "aggregateEmpty": False,
                "structured": 3,
                "display": "3",
                "hasCompanion": False,
            },
        ),
        PROPERTIES.InvariantCase(
            "allMissingCase",
            {
                "count": 0,
                "aggregateEmpty": True,
                "structured": None,
                "display": "−(0球)",
                "hasCompanion": True,
            },
        ),
    )


def _expectations() -> dict[tuple[str, str], Any]:
    """層別収集器へ単一 target の宣言済み構成を渡す。"""
    target = COLLECTOR.TargetExpectation(
        calculation=CALCULATION,
        direct_target_id=DIRECT_TARGET,
        kind="single",
        stages=(COLLECTOR.StageExpectation("python", ARTIFACT_HASH),),
    )
    return {(target.calculation, target.direct_target_id): target}


def _trace(case_id: str) -> dict[str, object]:
    """既存収集器が独立計算できる生の単一 target trace を返す。"""
    output = {"value": "ok"}
    return {
        "vector": "syntheticInvariantVector",
        "case": case_id,
        "entrypointId": "syntheticInvariantEntrypoint",
        "directTargetId": DIRECT_TARGET,
        "expected": output,
        "entrypointOutput": output,
        "directTargetOutput": output,
        "artifactHashes": {"python": ARTIFACT_HASH},
        "issuedSqlOrAst": None,
        "stageIO": [],
    }


def _property_row(
    property_id: str,
    property_kind: str,
    generated_cases: int,
) -> dict[str, object]:
    """ADR-003 D-11 ③ の必須 5 項目と trace を返す。"""
    return {
        "calculation": CALCULATION,
        "propertyId": property_id,
        "propertyKind": property_kind,
        "generatedCases": generated_cases,
        "status": "passed",
        "trace": _trace(f"{property_id}Case"),
    }


def _write_junit(path: Path, rows: list[dict[str, object]]) -> Path:
    """複数 property の Pytest JUnit XML を作る。"""
    suites = ET.Element("testsuites", {"name": "pytest properties"})
    suite = ET.SubElement(suites, "testsuite", {"name": "pytest"})
    for index, row in enumerate(rows):
        testcase = ET.SubElement(
            suite,
            "testcase",
            {
                "classname": "synthetic.properties",
                "name": f"test_property_{index}",
            },
        )
        container = ET.SubElement(testcase, "properties")
        for name, value in row.items():
            serialized = (
                json.dumps(value, ensure_ascii=False)
                if name == "trace"
                else str(value)
            )
            ET.SubElement(
                container,
                "property",
                {"name": name, "value": serialized},
            )
    ET.ElementTree(suites).write(path, encoding="utf-8", xml_declaration=True)
    return path


def _collection(
    tmp_path: Path,
    *,
    invariant_count: int | None = 2,
    include_equivalence: bool = True,
) -> Any:
    """既存収集器を通した property 証跡を返す。"""
    rows: list[dict[str, object]] = []
    if invariant_count is not None:
        rows.extend(
            _property_row(predicate.property_id, "invariant", invariant_count)
            for predicate in _predicates()
        )
    if include_equivalence:
        rows.append(_property_row("generatedBodiesAgree", "equivalence", 2))
    report = _write_junit(tmp_path / "properties.xml", rows)
    return COLLECTOR.collect_pytest_junit(report, _expectations())


def _run(
    tmp_path: Path,
    authorities: dict[str, Any],
    *,
    predicates: tuple[Any, ...] | None = None,
    cases: tuple[Any, ...] | None = None,
    collection: Any | None = None,
) -> Any:
    """既定の正しい入力を補って不変条件 runner を実行する。"""
    return PROPERTIES.run_invariants(
        root=ROOT,
        calculation=CALCULATION,
        predicates=_predicates() if predicates is None else predicates,
        cases=_valid_cases() if cases is None else cases,
        collection=(
            _collection(tmp_path)
            if collection is None
            else collection
        ),
        authorities=authorities,
    )


def test_false_predicate_fails(
    tmp_path: Path,
    authorities: dict[str, Any],
) -> None:
    """生成 case が規範述語を偽にすると不変条件違反になる。"""
    invalid_cases = list(_valid_cases())
    invalid_cases[0] = PROPERTIES.InvariantCase(
        "ordinaryCase",
        {
            "count": -1,
            "aggregateEmpty": False,
            "structured": -1,
            "display": "-1",
            "hasCompanion": False,
        },
    )

    with pytest.raises(PROPERTIES.InvariantRunError, match="不変条件違反"):
        _run(tmp_path, authorities, cases=tuple(invalid_cases))


def test_every_predicate_authority_verbatim_exists(
    authorities: dict[str, Any],
) -> None:
    """全述語の条項 ID と逐語が指定した正本の節に実在する。"""
    predicates = _predicates()

    PROPERTIES.validate_predicate_authorities(
        ROOT,
        predicates,
        authorities,
    )
    assert {predicate.authority_id for predicate in predicates} == {
        "ADR-003 D-11 3 層表 プロパティ層",
        "付録A-1 表示書式の共通規定",
    }

    missing = (
        PROPERTIES.InvariantPredicate(
            property_id="missingAuthority",
            authority_id="ADR-003 D-11 存在しない条項",
            evaluate=lambda value: True,
        ),
    )
    with pytest.raises(PROPERTIES.InvariantRunError, match="台帳に無い"):
        PROPERTIES.validate_predicate_authorities(ROOT, missing, authorities)

    changed = dict(authorities)
    original = changed["ADR-003 D-11 3 層表 プロパティ層"]
    changed[original.authority_id] = PROPERTIES.AuthorityLocation(
        authority_id=original.authority_id,
        source=original.source,
        section=original.section,
        verbatim="正本に存在しない逐語",
    )
    with pytest.raises(PROPERTIES.InvariantRunError, match="逐語が正本に無い"):
        PROPERTIES.validate_predicate_authorities(ROOT, predicates, changed)


def test_zero_generated_cases_are_not_counted_as_executed(
    tmp_path: Path,
    authorities: dict[str, Any],
) -> None:
    """GeneratedCases が 0 の invariant を既存収集器が実行済みに数えない。"""
    collection = _collection(tmp_path, invariant_count=0)

    assert collection.executed_count == 1
    assert {item.reason for item in collection.rejected} == {
        "zero-generated-cases"
    }
    with pytest.raises(PROPERTIES.InvariantRunError, match="実行済みと認めない"):
        _run(tmp_path, authorities, collection=collection)


@pytest.mark.parametrize("missing_kind", ["invariant", "equivalence"])
def test_both_property_kinds_must_complete(
    missing_kind: str,
    tmp_path: Path,
    authorities: dict[str, Any],
) -> None:
    """Invariant と equivalence の片方が 0 件なら個別に拒否する。"""
    collection = _collection(
        tmp_path,
        invariant_count=None if missing_kind == "invariant" else 2,
        include_equivalence=missing_kind != "equivalence",
    )

    assert collection.complete
    with pytest.raises(PROPERTIES.InvariantRunError, match="双方に 1 件以上"):
        _run(tmp_path, authorities, collection=collection)


def test_equivalence_is_only_observed_not_reimplemented() -> None:
    """本 runner が等価性比較を持たず収集済み kind だけを見る。"""
    source = PROPERTIES_SOURCE.read_text(encoding="utf-8")

    assert "from pitchlog.domaincheck.collect_layers import" in source
    assert "item.property_kind == \"equivalence\"" in source
    assert "compare_path_set" not in source
    assert "equivalence_output" not in source


def test_valid_generated_cases_complete_every_predicate(
    tmp_path: Path,
    authorities: dict[str, Any],
) -> None:
    """全述語を満たす生成 case 集合が両 property kind とともに完走する。"""
    predicates = _predicates()
    cases = _valid_cases()

    report = _run(
        tmp_path,
        authorities,
        predicates=predicates,
        cases=cases,
    )

    assert report.complete
    assert report.generated_case_ids == tuple(case.case_id for case in cases)
    assert len(report.evaluations) == len(predicates) * len(cases)
    assert all(evaluation.passed for evaluation in report.evaluations)
    assert report.invariant_property_ids == {
        predicate.property_id for predicate in predicates
    }
    assert report.equivalence_property_ids == {"generatedBodiesAgree"}
