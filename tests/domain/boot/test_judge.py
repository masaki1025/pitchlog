"""移行判定器が全 BOOT 条項の免除前結果を束ねることを検査する。"""

from __future__ import annotations

import ast
import importlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
BACKEND_SRC = ROOT / "backend/src"
JUDGE_SOURCE = BACKEND_SRC / "pitchlog/domaincheck/boot/judge.py"
CLAUSES_ASSET = ROOT / "backend/domain/boot-clauses.json"
REQUIREMENTS = ROOT / "docs/requirements/requirements-pitchlog-2026-07-22.md"

sys.path.insert(0, str(BACKEND_SRC))
JUDGE = importlib.import_module("pitchlog.domaincheck.boot.judge")
CLAUSES = importlib.import_module("pitchlog.domaincheck.boot.clauses")
PHASE2 = importlib.import_module("pitchlog.domaincheck.boot.phase2")
REPORT = importlib.import_module("pitchlog.domaincheck.boot.report")
STALL = importlib.import_module("pitchlog.domaincheck.boot.stall")
BOOT_SEAL = importlib.import_module("pitchlog.domaincheck.boot_seal")


@pytest.fixture(scope="module")
def clause_ids() -> tuple[str, ...]:
    """対応表から逆引き検証済みの条項 ID を返す。"""
    return tuple(
        clause.identifier for clause in CLAUSES.load_and_validate_registry(ROOT)
    )


@pytest.fixture
def judge_root(tmp_path: Path) -> Path:
    """正本と対応表だけを持つ合成リポジトリルートを返す。"""
    root = tmp_path / "repository"
    asset_path = root / CLAUSES_ASSET.relative_to(ROOT)
    requirements_path = root / REQUIREMENTS.relative_to(ROOT)
    asset_path.parent.mkdir(parents=True)
    requirements_path.parent.mkdir(parents=True)
    shutil.copy2(CLAUSES_ASSET, asset_path)
    shutil.copy2(REQUIREMENTS, requirements_path)
    return root


def _evidence(
    clause_ids: tuple[str, ...],
    outcome: str = "conforming",
) -> dict[str, Any]:
    """全条項が指定結果を持つ免除前の合成入力を返す。"""
    return {
        "schemaVersion": 1,
        "evidenceStage": "raw-unexempted-checks",
        "clauseResults": [
            {"clauseId": clause_id, "outcome": outcome}
            for clause_id in clause_ids
        ],
    }


def _write_json(path: Path, value: object) -> None:
    """合成入力を読みやすい JSON で書く。"""
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _run_judge(
    root: Path,
    evidence: object,
) -> subprocess.CompletedProcess[str]:
    """移行判定器を独立プロセスで実行する。"""
    evidence_path = root / "raw-evidence.json"
    _write_json(evidence_path, evidence)
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pitchlog.domaincheck.boot.judge",
            "--root",
            str(root),
            "--evidence",
            evidence_path.name,
        ],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(BACKEND_SRC)},
        capture_output=True,
        text=True,
        check=False,
    )


def test_all_registry_clauses_have_exactly_one_detection_route(
    clause_ids: tuple[str, ...],
) -> None:
    routes = JUDGE.build_detection_routes(ROOT)
    route_ids = tuple(route.clause_id for route in routes)

    assert len(clause_ids) == 12
    assert route_ids == clause_ids
    assert len(route_ids) == len(set(route_ids))
    assert all(callable(route.detector) for route in routes)


def test_missing_and_unknown_detection_routes_fail_set_comparison(
    clause_ids: tuple[str, ...],
) -> None:
    routes = JUDGE.build_detection_routes(ROOT)
    missing = routes[:-1]
    unknown = (
        *routes,
        JUDGE.DetectionRoute(
            clause_id="synthetic-unknown-clause",
            criterion_authority="synthetic-authority",
            detector=routes[0].detector,
        ),
    )

    with pytest.raises(JUDGE.CheckerViolation, match="集合差"):
        JUDGE.assert_route_coverage(clause_ids, missing)
    with pytest.raises(JUDGE.CheckerViolation, match="集合差"):
        JUDGE.assert_route_coverage(clause_ids, unknown)


def test_clause_ids_are_not_handwritten_in_judge(
    clause_ids: tuple[str, ...],
) -> None:
    source = JUDGE_SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    string_constants = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }

    assert string_constants.isdisjoint(clause_ids)
    assert all(clause_id not in source for clause_id in clause_ids)


def test_existing_mechanisms_are_reused_without_reimplementation() -> None:
    bundle = JUDGE.existing_mechanisms()

    assert bundle.seal_verifier is BOOT_SEAL.verify_boot_seal
    assert bundle.state_activator is STALL.activate
    assert bundle.state_observer is STALL.observe_pr_integration
    assert bundle.state_reapprover is STALL.reapprove_from_git
    assert bundle.phase2_evaluator is PHASE2.evaluate_phase2
    assert bundle.report_acceptor is REPORT.accept_transition_green
    assert bundle.clause_loader is CLAUSES.load_and_validate_registry


def test_input_type_and_ast_exclude_post_exemption_result() -> None:
    tree = ast.parse(JUDGE_SOURCE.read_text(encoding="utf-8"))
    identifiers = {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    } | {
        node.arg for node in ast.walk(tree) if isinstance(node, ast.arg)
    } | {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    result_type = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and node.name == "RawUnexemptedResults"
    )
    fields = {
        node.target.id
        for node in result_type.body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
    }

    assert fields == {"clause_results"}
    assert identifiers.isdisjoint(
        {"green", "exempted_green", "post_exemption", "granted_result"}
    )


def test_post_exemption_evidence_stage_is_indeterminate(
    judge_root: Path,
    clause_ids: tuple[str, ...],
) -> None:
    evidence = _evidence(clause_ids)
    evidence["evidenceStage"] = "post-exemption"

    result = _run_judge(judge_root, evidence)

    assert result.returncode == 2
    assert "免除前の生結果" in result.stderr


def test_all_conforming_raw_results_exit_zero(
    judge_root: Path,
    clause_ids: tuple[str, ...],
) -> None:
    result = _run_judge(judge_root, _evidence(clause_ids))

    assert result.returncode == 0, result.stderr


def test_one_nonconforming_raw_result_exits_one(
    judge_root: Path,
    clause_ids: tuple[str, ...],
) -> None:
    evidence = _evidence(clause_ids)
    evidence["clauseResults"][0]["outcome"] = "nonconforming"

    result = _run_judge(judge_root, evidence)

    assert result.returncode == 1


def test_one_indeterminate_raw_result_exits_two(
    judge_root: Path,
    clause_ids: tuple[str, ...],
) -> None:
    evidence = _evidence(clause_ids)
    evidence["clauseResults"][0]["outcome"] = "indeterminate"

    result = _run_judge(judge_root, evidence)

    assert result.returncode == 2


def test_indeterminate_takes_precedence_over_nonconforming(
    judge_root: Path,
    clause_ids: tuple[str, ...],
) -> None:
    evidence = _evidence(clause_ids)
    evidence["clauseResults"][0]["outcome"] = "nonconforming"
    evidence["clauseResults"][1]["outcome"] = "indeterminate"

    result = _run_judge(judge_root, evidence)

    assert result.returncode == 2


def test_missing_raw_clause_result_is_indeterminate(
    judge_root: Path,
    clause_ids: tuple[str, ...],
) -> None:
    evidence = _evidence(clause_ids)
    evidence["clauseResults"].pop()

    result = _run_judge(judge_root, evidence)

    assert result.returncode == 2
    assert "集合差" in result.stderr


def test_existing_exit_contract_maps_to_three_distinct_raw_outcomes() -> None:
    outcomes = {
        JUDGE.outcome_from_exit_code(code) for code in (0, 1, 2)
    }

    assert outcomes == set(JUDGE.RawOutcome)
    with pytest.raises(JUDGE.CheckerExecutionError, match="未知の exit"):
        JUDGE.outcome_from_exit_code(3)


def test_raw_check_adapter_keeps_violation_and_execution_failure_separate() -> None:
    def violating() -> None:
        raise JUDGE.CheckerViolation("synthetic violation")

    def impossible() -> None:
        raise JUDGE.CheckerExecutionError("synthetic execution failure")

    assert JUDGE.run_raw_check(lambda: None) == JUDGE.RawOutcome.CONFORMING
    assert JUDGE.run_raw_check(violating) == JUDGE.RawOutcome.NONCONFORMING
    assert JUDGE.run_raw_check(impossible) == JUDGE.RawOutcome.INDETERMINATE
