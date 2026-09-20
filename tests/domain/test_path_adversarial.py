"""経路一致の敵対 fixture を既存の収集器と比較器へ投入する。"""

from __future__ import annotations

import copy
import importlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC = ROOT / "backend/src"
FIXTURE_DIR = ROOT / "backend/tests/domain/fixtures/adversarial_path"
TEST_SOURCE = Path(__file__)
CURRENT_HASHES = {
    "sql": f"sha256:{'1' * 64}",
    "typed-receiver": f"sha256:{'2' * 64}",
    "formatter": f"sha256:{'3' * 64}",
}
MISMATCH_HASH = f"sha256:{'9' * 64}"
FIXTURE_FIELDS = {
    "fixtureId",
    "attack",
    "targetClass",
    "stages",
    "mutation",
    "expected",
    "assurance",
}

sys.path.insert(0, str(BACKEND_SRC))
COLLECTOR = importlib.import_module("pitchlog.domaincheck.collect_layers")
PATH_MATCH = importlib.import_module("pitchlog.domaincheck.path_match")


def _load_fixture(name: str) -> dict[str, Any]:
    """名前を指定して敵対 fixture を読む。"""
    value = json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    assert set(value) == FIXTURE_FIELDS
    assert set(value["mutation"]) == {"kind", "stage"}
    assert set(value["expected"]) == {"combinedAcceptance"}
    return value


def _all_fixtures() -> list[dict[str, Any]]:
    """敵対 fixture の全件をファイル名順で返す。"""
    return [
        _load_fixture(path.name)
        for path in sorted(FIXTURE_DIR.glob("*.json"))
    ]


def _calculation(fixture: dict[str, Any]) -> str:
    """Fixture の対象区分から合成対象計算 ID を返す。"""
    suffix = str(fixture["targetClass"]).replace("-", "_")
    return f"synthetic_{suffix}"


def _numeric(value: int) -> dict[str, object]:
    """比較面へ渡す整数 NumericValue を返す。"""
    return {"kind": "integer", "value": value}


def _expected_rows() -> list[dict[str, object]]:
    """合成経路の期待値を返す。"""
    return [{"value": _numeric(1)}]


def _stage_io(
    stages: list[str],
    expected: list[dict[str, object]],
) -> list[dict[str, object]]:
    """全段の値が連鎖する基準 I/O を組み立てる。"""
    previous: object = {"source": "synthetic-fixture"}
    items: list[dict[str, object]] = []
    for index, stage in enumerate(stages):
        output: object
        if index == len(stages) - 1:
            output = copy.deepcopy(expected)
        else:
            output = {"stage": stage, "value": index + 1}
        items.append(
            {
                "stage": stage,
                "artifactHash": CURRENT_HASHES[stage],
                "input": previous,
                "output": output,
            }
        )
        previous = output
    return items


def _trace(fixture: dict[str, Any]) -> dict[str, object]:
    """Fixture の変異を適用した runner 生 trace を返す。"""
    stages = [str(stage) for stage in fixture["stages"]]
    expected = _expected_rows()
    trace: dict[str, object] = {
        "vector": "adversarialVector",
        "case": str(fixture["fixtureId"]),
        "entrypointId": "syntheticEntrypoint",
        "directTargetId": "syntheticDirectTarget",
        "expected": copy.deepcopy(expected),
        "entrypointOutput": copy.deepcopy(expected),
        "directTargetOutput": copy.deepcopy(expected),
        "artifactHashes": {
            stage: CURRENT_HASHES[stage] for stage in stages
        },
        "issuedSqlOrAst": "SELECT value FROM generated_source",
        "stageIO": _stage_io(stages, expected),
    }
    attack = fixture["attack"]
    stage = str(fixture["mutation"]["stage"])
    if attack == "forged-sql":
        forged = [{"value": _numeric(999)}]
        trace["issuedSqlOrAst"] = "SELECT 999 AS forged_value"
        trace["directTargetOutput"] = forged
        stage_io = trace["stageIO"]
        assert isinstance(stage_io, list)
        stage_io[-1]["output"] = forged
    elif attack == "stage-hash-mismatch":
        hashes = trace["artifactHashes"]
        assert isinstance(hashes, dict)
        hashes[stage] = MISMATCH_HASH
        stage_io = trace["stageIO"]
        assert isinstance(stage_io, list)
        matching = next(item for item in stage_io if item["stage"] == stage)
        matching["artifactHash"] = MISMATCH_HASH
    elif attack == "expected-value-shortcut":
        trace["issuedSqlOrAst"] = ""
        trace["stageIO"] = []
    elif attack == "stage-chain-mismatch":
        stage_io = trace["stageIO"]
        assert isinstance(stage_io, list)
        matching = next(item for item in stage_io if item["stage"] == stage)
        matching["input"] = {"value": "not-previous-output"}
    elif attack == "adapter-five-true-claim":
        trace["judgments"] = {
            "entrypointExecuted": True,
            "directTargetExecuted": True,
            "entrypointEqualsExpected": True,
            "directTargetEqualsExpected": True,
            "pathsEqual": True,
        }
    elif attack != "coherent-bypass-residual":
        raise AssertionError(f"未知の敵対 fixture: {attack}")
    return trace


def _expectations(fixture: dict[str, Any]) -> dict[tuple[str, str], Any]:
    """Generated 宣言に相当する段別 hash の正を返す。"""
    stages = tuple(
        COLLECTOR.StageExpectation(str(stage), CURRENT_HASHES[str(stage)])
        for stage in fixture["stages"]
    )
    target = COLLECTOR.TargetExpectation(
        calculation=_calculation(fixture),
        direct_target_id="syntheticDirectTarget",
        kind="composite",
        stages=stages,
    )
    return {(target.calculation, target.direct_target_id): target}


def _write_report(
    tmp_path: Path,
    fixture: dict[str, Any],
    trace: dict[str, object],
) -> Path:
    """収集器へ渡す Vitest reporter JSON を一時領域へ書く。"""
    properties = {
        "calculation": _calculation(fixture),
        "propertyId": "adversarialEquivalence",
        "propertyKind": "equivalence",
        "generatedCases": 1,
        "status": "passed",
        "trace": trace,
    }
    report = {
        "numTotalTests": 1,
        "numPassedTests": 1,
        "numFailedTests": 0,
        "numPendingTests": 0,
        "numTodoTests": 0,
        "testResults": [
            {
                "name": "adversarial.test.ts",
                "assertionResults": [
                    {
                        "title": fixture["fixtureId"],
                        "fullName": fixture["fixtureId"],
                        "status": "passed",
                        "meta": {"pitchlog": properties},
                    }
                ],
            }
        ],
    }
    path = tmp_path / f"{fixture['fixtureId']}.json"
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _comparison_contract() -> Any:
    """合成値を全フィールド比較する lossless 契約を返す。"""
    return PATH_MATCH.ComparisonContract(
        surface="structured-only",
        fields=(
            PATH_MATCH.FieldContract(
                "value", "structured", "exact-number", False, 0
            ),
        ),
        normalizations=frozenset({"exact-numeric-representation"}),
    )


def _exercise(
    fixture: dict[str, Any],
    tmp_path: Path,
) -> tuple[Any, Any | None, dict[str, object]]:
    """敵対 fixture を収集器と比較器へ順に通す。"""
    trace = _trace(fixture)
    report_path = _write_report(tmp_path, fixture, trace)
    collected = COLLECTOR.collect_vitest_reporter(
        report_path,
        _expectations(fixture),
    )
    if not collected.evidence:
        return collected, None, trace
    layer_evidence = collected.evidence[0]
    submission = PATH_MATCH.submission_from_collected(
        layer_evidence,
        expected=trace["expected"],
        entrypoint_output=trace["entrypointOutput"],
        direct_target_output=trace["directTargetOutput"],
    )
    matched = PATH_MATCH.compare_path_set(
        [submission.key],
        [submission],
        {_calculation(fixture): _comparison_contract()},
    )
    return collected, matched, trace


def _combined_acceptance(collected: Any, matched: Any | None) -> bool:
    """収集器と比較器の双方が成立したかを返す。"""
    return bool(
        collected.complete
        and matched is not None
        and matched.complete
    )


def test_fixture_population_has_four_attacks_and_one_residual_record() -> None:
    """4 種の負例と保証範囲外の 1 記録が資産に存在する。"""
    fixtures = _all_fixtures()
    attacks = {fixture["attack"] for fixture in fixtures}

    assert {
        "forged-sql",
        "stage-hash-mismatch",
        "expected-value-shortcut",
        "stage-chain-mismatch",
    } <= attacks
    assert "coherent-bypass-residual" in attacks


@pytest.mark.parametrize(
    "fixture_name",
    [
        "forged_sql.json",
        "hash_mismatch_beta_1_5_sql.json",
        "expected_value_shortcut.json",
        "stage_chain_mismatch.json",
    ],
)
def test_each_of_four_adversarial_kinds_fails(
    fixture_name: str,
    tmp_path: Path,
) -> None:
    """4 種の敵対提出を既存機構で個別に不合格にする。"""
    fixture = _load_fixture(fixture_name)
    collected, matched, _ = _exercise(fixture, tmp_path)

    assert fixture["expected"]["combinedAcceptance"] is False
    assert not _combined_acceptance(collected, matched)


def test_forged_sql_fails_the_five_judgments(tmp_path: Path) -> None:
    """偽 SQL の異なる結果を直接経路の期待値不一致として検出する。"""
    fixture = _load_fixture("forged_sql.json")
    collected, matched, trace = _exercise(fixture, tmp_path)

    assert trace["issuedSqlOrAst"] == "SELECT 999 AS forged_value"
    assert not collected.evidence[0].judgments.direct_target_equals_expected
    assert matched is not None
    assert not matched.evidence[0].judgments.direct_target_equals_expected
    assert not matched.evidence[0].judgments.paths_equal


def test_every_composite_stage_hash_mismatch_fails(tmp_path: Path) -> None:
    """3 段と 2 段の各段を一つずつ壊して generated hash 差を検出する。"""
    fixtures = [
        fixture
        for fixture in _all_fixtures()
        if fixture["attack"] == "stage-hash-mismatch"
    ]
    stages_by_class: dict[str, set[str]] = {}
    for fixture in fixtures:
        collected, matched, _ = _exercise(fixture, tmp_path)
        stages_by_class.setdefault(fixture["targetClass"], set()).add(
            fixture["mutation"]["stage"]
        )
        assert len(collected.evidence) == 1
        assert not collected.evidence[0].artifact_hashes_valid
        assert not _combined_acceptance(collected, matched)

    assert len(fixtures) == 5
    assert stages_by_class == {
        "beta-1-5": {"sql", "typed-receiver", "formatter"},
        "beta-7": {"sql", "typed-receiver"},
    }


def test_expected_value_shortcut_lacks_stage_execution_evidence(
    tmp_path: Path,
) -> None:
    """期待値直返しは値だけ一致しても段別実行証跡の欠落で不合格になる。"""
    fixture = _load_fixture("expected_value_shortcut.json")
    collected, matched, _ = _exercise(fixture, tmp_path)

    assert collected.evidence[0].judgments.complete
    assert not collected.evidence[0].stage_chain_valid
    assert matched is not None and matched.complete
    assert not _combined_acceptance(collected, matched)


def test_stage_chain_mismatch_fails_independent_chain_check(
    tmp_path: Path,
) -> None:
    """前段出力と後段入力の差を収集器自身の連鎖検査で落とす。"""
    fixture = _load_fixture("stage_chain_mismatch.json")
    collected, matched, _ = _exercise(fixture, tmp_path)

    assert collected.evidence[0].artifact_hashes_valid
    assert not collected.evidence[0].stage_chain_valid
    assert matched is not None and matched.complete
    assert not _combined_acceptance(collected, matched)


def test_adapter_five_true_claim_cannot_replace_raw_evidence(
    tmp_path: Path,
) -> None:
    """アダプタが真を 5 個返す自己申告を厳密 trace 契約で拒否する。"""
    fixture = _load_fixture("adapter_five_true_claim.json")
    collected, matched, trace = _exercise(fixture, tmp_path)
    claimed = trace["judgments"]

    assert isinstance(claimed, dict)
    assert len(claimed) == 5
    assert all(value is True for value in claimed.values())
    assert collected.executed_count == 0
    assert "unexpected=['judgments']" in collected.rejected[0].reason
    assert matched is None
    assert not _combined_acceptance(collected, matched)


def test_coherent_bypass_is_recorded_as_an_undetected_residual_risk(
    tmp_path: Path,
) -> None:
    """整合する提出が通る限界を保証範囲外として正直に記録する。"""
    fixture = _load_fixture("coherent_bypass_residual.json")
    collected, matched, _ = _exercise(fixture, tmp_path)

    assert fixture["expected"]["combinedAcceptance"] is True
    assert _combined_acceptance(collected, matched)
    assert "保証範囲外" in fixture["assurance"]
    assert "不検出" in fixture["assurance"]


def test_assets_and_test_do_not_claim_residual_risk_is_precluded() -> None:
    """残余リスクを完全排除したと謳う文言が無いことを静的検査する。"""
    forbidden = (
        "".join(("迂回", "を検出")),
        "".join(("迂回", "検出を保証")),
        "detects" + "-coherent-bypass",
        "guarantees" + "-bypass-detection",
    )
    sources = [TEST_SOURCE, *sorted(FIXTURE_DIR.glob("*.json"))]
    violations = [
        (source.name, phrase)
        for source in sources
        for phrase in forbidden
        if phrase in source.read_text(encoding="utf-8")
    ]

    assert violations == []


def test_fixture_directory_is_not_a_backend_pytest_suite() -> None:
    """Backend pytest が敵対 fixture をテストとして収集しない配置を保つ。"""
    assert list(FIXTURE_DIR.glob("test_*.py")) == []
    assert all(path.suffix == ".json" for path in FIXTURE_DIR.iterdir())
