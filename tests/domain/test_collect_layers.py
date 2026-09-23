"""Pytest・Vitest の層別実行証跡を独立採取できることを検証する。"""

from __future__ import annotations

import hashlib
import importlib
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC = ROOT / "backend/src"
COLLECTOR_SOURCE = BACKEND_SRC / "pitchlog/domaincheck/collect_layers.py"
ADR = ROOT / "docs/adr/ADR-003-domain-calc-method.md"
REVIEW_TRIGGERS = ROOT / "backend/domain/review-triggers.json"
HASH_SQL = f"sha256:{'1' * 64}"
HASH_RECEIVER = f"sha256:{'2' * 64}"

sys.path.insert(0, str(BACKEND_SRC))
COLLECTOR = importlib.import_module("pitchlog.domaincheck.collect_layers")


def _read_json(path: Path) -> dict[str, Any]:
    """JSON object を UTF-8 で読み込む。"""
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _expectations() -> dict[tuple[str, str], Any]:
    """2 段 composite の宣言済み構成を返す。"""
    target = COLLECTOR.TargetExpectation(
        calculation="syntheticCalculation",
        direct_target_id="syntheticComposite",
        kind="composite",
        stages=(
            COLLECTOR.StageExpectation("sql", HASH_SQL),
            COLLECTOR.StageExpectation("typed-receiver", HASH_RECEIVER),
        ),
    )
    return {(target.calculation, target.direct_target_id): target}


def _trace() -> dict[str, object]:
    """収集器が 5 判定と段別値連鎖を計算できる生値を返す。"""
    sql_output = [{"value": "ready"}]
    final_output = {"value": "ready"}
    return {
        "vector": "syntheticVector",
        "case": "syntheticCase",
        "entrypointId": "syntheticEntrypoint",
        "directTargetId": "syntheticComposite",
        "expected": final_output,
        "entrypointOutput": final_output,
        "directTargetOutput": final_output,
        "artifactHashes": {
            "sql": HASH_SQL,
            "typed-receiver": HASH_RECEIVER,
        },
        "issuedSqlOrAst": "SELECT value FROM synthetic_source",
        "stageIO": [
            {
                "stage": "sql",
                "artifactHash": HASH_SQL,
                "input": {"source": "synthetic"},
                "output": sql_output,
            },
            {
                "stage": "typed-receiver",
                "artifactHash": HASH_RECEIVER,
                "input": sql_output,
                "output": final_output,
            },
        ],
    }


def _properties(
    *,
    generated_cases: int = 1,
    trace: dict[str, object] | None = None,
) -> dict[str, object]:
    """ADR-003 D-11 ③ の必須 5 項目と生 trace を返す。"""
    return {
        "calculation": "syntheticCalculation",
        "propertyId": "syntheticEquivalence",
        "propertyKind": "equivalence",
        "generatedCases": generated_cases,
        "status": "passed",
        "trace": _trace() if trace is None else trace,
    }


def _write_junit(
    path: Path,
    properties: dict[str, object],
    *,
    state: str = "passed",
) -> Path:
    """負例用の Pytest JUnit envelope を作る。"""
    suites = ET.Element("testsuites", {"name": "pytest tests"})
    suite = ET.SubElement(suites, "testsuite", {"name": "pytest"})
    testcase = ET.SubElement(
        suite,
        "testcase",
        {"classname": "synthetic", "name": f"test_{state}"},
    )
    container = ET.SubElement(testcase, "properties")
    for name, value in properties.items():
        serialized = json.dumps(value, ensure_ascii=False) if name == "trace" else str(value)
        ET.SubElement(
            container,
            "property",
            {"name": name, "value": serialized},
        )
    if state == "skip":
        ET.SubElement(testcase, "skipped", {"type": "pytest.skip"})
    elif state == "xfail":
        ET.SubElement(testcase, "skipped", {"type": "pytest.xfail"})
    elif state == "failed":
        ET.SubElement(testcase, "failure", {"message": "synthetic failure"})
    ET.ElementTree(suites).write(path, encoding="utf-8", xml_declaration=True)
    return path


def _write_vitest(
    path: Path,
    properties: dict[str, object],
    *,
    state: str = "passed",
) -> Path:
    """Vitest JSON reporter と同じ envelope を作る。"""
    passed = 1 if state == "passed" else 0
    pending = 1 if state == "skipped" else 0
    todo = 1 if state == "todo" else 0
    failed = 1 if state == "failed" else 0
    report = {
        "numTotalTests": 1,
        "numPassedTests": passed,
        "numFailedTests": failed,
        "numPendingTests": pending,
        "numTodoTests": todo,
        "testResults": [
            {
                "name": "synthetic.test.ts",
                "assertionResults": [
                    {
                        "title": f"synthetic {state}",
                        "fullName": f"synthetic {state}",
                        "status": state,
                        "meta": {"pitchlog": properties},
                    }
                ],
            }
        ],
    }
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _run_real_pytest(tmp_path: Path) -> Path:
    """実際の Pytest に properties を出力させ JUnit XML を返す。"""
    properties = _properties()
    source_lines = ["def test_runner_output(record_property):"]
    for name, value in properties.items():
        serialized = json.dumps(value, ensure_ascii=False) if name == "trace" else str(value)
        source_lines.append(
            f"    record_property({name!r}, {serialized!r})"
        )
    source = tmp_path / "test_runner_output.py"
    output = tmp_path / "pytest-report.xml"
    source.write_text("\n".join(source_lines) + "\n", encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            str(source),
            f"--junitxml={output}",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return output


def test_five_required_items_are_derived_from_adr_d11() -> None:
    """5 項目の名称と件数を正本の逐語へ束縛する。"""
    source = ADR.read_text(encoding="utf-8")
    d11 = source.split("### D-11:", maxsplit=1)[1].split(
        "### D-12:", maxsplit=1
    )[0]
    expected = {
        "calculation",
        "propertyId",
        "propertyKind",
        "generatedCases",
        "status",
    }

    assert len(COLLECTOR.REQUIRED_LAYER_PROPERTIES) == 5
    assert COLLECTOR.REQUIRED_LAYER_PROPERTIES == expected
    assert all(f"`{item}`" in d11 for item in expected)
    assert "この 5 項目を出力しないテスト" in d11
    assert "ADR-003 D-11 ③ 宣言された構成の完全性" in (
        COLLECTOR_SOURCE.read_text(encoding="utf-8")
    )


@pytest.mark.parametrize(
    ("state", "runner", "expected_reason"),
    [
        ("skip", "pytest", "skip"),
        ("xfail", "pytest", "xfail"),
        ("todo", "vitest", "todo"),
        ("zero", "pytest", "zero-generated-cases"),
    ],
)
def test_non_executed_states_fail_individually(
    state: str,
    runner: str,
    expected_reason: str,
    tmp_path: Path,
) -> None:
    """Skip・xfail・todo・0 case を個別に実行済みから除外する。"""
    properties = _properties(generated_cases=0 if state == "zero" else 1)
    if runner == "pytest":
        document = _write_junit(
            tmp_path / f"{state}.xml",
            properties,
            state="passed" if state == "zero" else state,
        )
        result = COLLECTOR.collect_pytest_junit(document, _expectations())
    else:
        document = _write_vitest(
            tmp_path / f"{state}.json",
            properties,
            state=state,
        )
        result = COLLECTOR.collect_vitest_reporter(document, _expectations())

    assert result.executed_count == 0
    assert len(result.rejected) == 1
    assert result.rejected[0].reason == expected_reason
    assert not result.complete


@pytest.mark.parametrize(
    "missing",
    [
        "calculation",
        "propertyId",
        "propertyKind",
        "generatedCases",
        "status",
    ],
)
def test_each_missing_required_item_fails_individually(
    missing: str,
    tmp_path: Path,
) -> None:
    """必須 5 項目の各欠落を別々に実行済みから除外する。"""
    properties = _properties()
    del properties[missing]
    document = _write_junit(tmp_path / f"missing-{missing}.xml", properties)

    result = COLLECTOR.collect_pytest_junit(document, _expectations())

    assert result.executed_count == 0
    assert len(result.rejected) == 1
    assert result.rejected[0].reason == f"missing-properties:{missing}"
    assert not result.complete


def test_composite_without_stage_io_fails(tmp_path: Path) -> None:
    """Composite の段別 I/O が空なら値連鎖を成立させない。"""
    trace = _trace()
    trace["stageIO"] = []
    document = _write_junit(
        tmp_path / "missing-stage-io.xml",
        _properties(trace=trace),
    )

    result = COLLECTOR.collect_pytest_junit(document, _expectations())

    assert result.executed_count == 1
    assert not result.evidence[0].stage_chain_valid
    assert not result.complete


def test_collector_computes_chain_instead_of_accepting_adapter_claim(
    tmp_path: Path,
) -> None:
    """前段出力と次段入力の不一致を収集器自身が検出する。"""
    trace = _trace()
    stage_io = trace["stageIO"]
    assert isinstance(stage_io, list)
    second_stage = stage_io[1]
    assert isinstance(second_stage, dict)
    second_stage["input"] = [{"value": "different"}]
    document = _write_vitest(
        tmp_path / "broken-chain.json",
        _properties(trace=trace),
    )

    result = COLLECTOR.collect_vitest_reporter(document, _expectations())

    assert result.executed_count == 1
    assert result.evidence[0].judgments.complete
    assert result.evidence[0].artifact_hashes_valid
    assert not result.evidence[0].stage_chain_valid
    assert not result.complete


def test_adapter_chain_valid_self_claim_is_rejected(tmp_path: Path) -> None:
    """Adapter が等値判定を自己申告できる未知キーを拒否する。"""
    trace = _trace()
    trace["chainValid"] = True
    document = _write_vitest(
        tmp_path / "self-claim.json",
        _properties(trace=trace),
    )

    result = COLLECTOR.collect_vitest_reporter(document, _expectations())

    assert result.executed_count == 0
    assert result.rejected[0].reason.startswith("invalid-evidence:")
    assert "unexpected=['chainValid']" in result.rejected[0].reason


def test_handwritten_normalized_evidence_is_not_a_runner_output(
    tmp_path: Path,
) -> None:
    """手書きの正規化済み証跡を runner provenance として受理しない。"""
    document = tmp_path / "handwritten.json"
    document.write_text(
        json.dumps({"evidence": [_properties()]}, ensure_ascii=False),
        encoding="utf-8",
    )

    with pytest.raises(COLLECTOR.CollectionError, match="生成元 marker"):
        COLLECTOR.collect_vitest_reporter(document, _expectations())


def test_real_pytest_junit_output_is_counted_with_provenance(
    tmp_path: Path,
) -> None:
    """実 Pytest の JUnit XML から正しい証跡を実行済みに数える。"""
    document = _run_real_pytest(tmp_path)
    digest = f"sha256:{hashlib.sha256(document.read_bytes()).hexdigest()}"

    result = COLLECTOR.collect_pytest_junit(document, _expectations())

    assert result.executed_count == 1
    assert result.rejected == ()
    assert result.complete
    assert result.evidence[0].complete
    assert result.evidence[0].provenance.runner.value == "pytest"
    assert result.evidence[0].provenance.source_format == "junit-xml"
    assert result.evidence[0].provenance.source_hash == digest


def test_vitest_reporter_output_is_counted(tmp_path: Path) -> None:
    """Vitest reporter JSON の正しい証跡を実行済みに数える。"""
    document = _write_vitest(tmp_path / "vitest.json", _properties())

    result = COLLECTOR.collect_vitest_reporter(document, _expectations())

    assert result.executed_count == 1
    assert result.rejected == ()
    assert result.complete
    evidence = result.evidence[0]
    assert evidence.provenance.runner.value == "vitest"
    assert evidence.provenance.source_format == "vitest-reporter-json"
    assert evidence.judgments.complete
    assert evidence.artifact_hashes_valid
    assert evidence.stage_chain_valid


def test_trigger_fourteen_record_is_bound_to_measured_chain_result(
    tmp_path: Path,
) -> None:
    """トリガー 14 の記録を独立な段別 I/O 実測へ束縛する。"""
    document = _write_vitest(tmp_path / "trigger-14.json", _properties())
    measured = COLLECTOR.collect_vitest_reporter(document, _expectations())
    asset = _read_json(REVIEW_TRIGGERS)
    trigger = next(item for item in asset["triggers"] if item["id"] == 14)

    assert measured.complete
    assert trigger["evaluation"] == {"fired": not measured.complete}
    assert trigger["evidenceLocation"] == "tests/domain/test_collect_layers.py"
