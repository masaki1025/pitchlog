"""状態系 BOOT 条項の負例が既存機構を個別に落とすことを検査する。"""

from __future__ import annotations

import ast
import copy
import importlib
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
BACKEND_SRC = ROOT / "backend/src"
NEGATIVE_DIR = ROOT / "backend/tests/domain/boot/negatives/state"
CLAUSES_ASSET = ROOT / "backend/domain/boot-clauses.json"
BOOT_SEAL_ASSET = ROOT / "backend/domain/boot-seal.json"
BOOT_REPORT_SCHEMA = ROOT / "backend/domain/boot-report.schema.json"
STALL_SOURCE = BACKEND_SRC / "pitchlog/domaincheck/boot/stall.py"
NEGATIVE_FIXTURES = tuple(sorted(NEGATIVE_DIR.glob("*.json")))

sys.path.insert(0, str(BACKEND_SRC))
CLAUSES = importlib.import_module("pitchlog.domaincheck.boot.clauses")
JUDGE = importlib.import_module("pitchlog.domaincheck.boot.judge")
PHASE2 = importlib.import_module("pitchlog.domaincheck.boot.phase2")
REPORT = importlib.import_module("pitchlog.domaincheck.boot.report")
STALL = importlib.import_module("pitchlog.domaincheck.boot.stall")

_CASE_KEYS = frozenset({"caseId", "clauseId", "mechanism", "violation"})


def _load_case(path: Path) -> dict[str, Any]:
    """厳密キー集合を持つ負例 fixture を読む。"""
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    assert frozenset(value) == _CASE_KEYS
    string_fields = _CASE_KEYS - {"violation"}
    assert all(
        isinstance(value[field], str) and value[field] for field in string_fields
    )
    assert isinstance(value["violation"], dict)
    return value


def _state_clause_ids() -> frozenset[str]:
    """対応表の逆引き結果から封印系を除いた状態系条項を選ぶ。"""
    clauses = CLAUSES.load_and_validate_registry(ROOT)
    seal_semantic_markers = (
        "宣言の更新のみをもって解消としてはならない",
        "出力のない緑は本規定の充足とみなさない",
    )
    seal_ids = frozenset(
        clause.identifier
        for clause in clauses
        if clause.identifier.startswith("BOOT-SEAL")
        or any(
            marker in clause.normative_text for marker in seal_semantic_markers
        )
    )
    return frozenset(clause.identifier for clause in clauses) - seal_ids


def _promotion_has_disjunctive_guard(source: str) -> bool:
    """軸①の昇格を別条件との論理和で発火する経路があるか調べる。"""
    tree = ast.parse(source)
    parents = {
        child: parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }
    for call in ast.walk(tree):
        if not isinstance(call, ast.Call):
            continue
        promotes = any(
            keyword.arg == "program"
            and isinstance(keyword.value, ast.Attribute)
            and keyword.value.attr == "PROMOTED"
            for keyword in call.keywords
        )
        if not promotes:
            continue
        parent = parents.get(call)
        while parent is not None and not isinstance(parent, ast.If):
            parent = parents.get(parent)
        if (
            isinstance(parent, ast.If)
            and isinstance(parent.test, ast.BoolOp)
            and isinstance(parent.test.op, ast.Or)
        ):
            return True
    return False


def _second_program_termination(
    case: dict[str, Any],
    _temporary_root: Path,
    disabled: bool,
) -> int:
    """軸①の既存終了条件へ第2条件を足したソース変異を検出する。"""
    source = STALL_SOURCE.read_text(encoding="utf-8")
    violation = case["violation"]
    if not disabled:
        changed = source.replace(
            violation["originalGuard"],
            violation["mutatedGuard"],
            1,
        )
        if changed == source:
            return 2
        source = changed
    return 1 if _promotion_has_disjunctive_guard(source) else 0


def _indeterminate_not_phase2(
    case: dict[str, Any],
    _temporary_root: Path,
    disabled: bool,
) -> int:
    """判定不能を段階2から外す主張を既存の fail-closed 判定と照合する。"""
    universe = PHASE2.load_target_universe(ROOT)
    state = STALL.activate(STALL.defined_state(1), "activation")
    decision = PHASE2.classify_phase2(
        state,
        universe,
        PHASE2.SemanticSnapshot.empty(),
        PHASE2.SemanticSnapshot.missing(),
    )
    claim = True if disabled else case["violation"]["claimsPhase2"]
    return 0 if claim == decision.is_phase2 else 1


def _expired_state(used_ids: frozenset[str]) -> Any:
    """再承認条件を満たす失効済みの合成状態を返す。"""
    return STALL.StallState(
        effective=True,
        program=STALL.ProgramStatus.TRANSITION,
        grant=STALL.GrantStatus.EXPIRED,
        unresolved_count=1,
        epoch=STALL.StallEpoch(
            start_commit="activation",
            reason=STALL.EpochStartReason.ACTIVATION,
            starting_unresolved_count=1,
            merge_count=STALL.STALL_MERGE_LIMIT,
        ),
        expired_at_commit="expiry",
        used_reapproval_ids=used_ids,
    )


def _reused_reapproval_record(
    case: dict[str, Any],
    _temporary_root: Path,
    disabled: bool,
) -> int:
    """消費済みの承認 ID を再び使う遷移を既存機構へ渡す。"""
    violation = case["violation"]
    approval_id = violation["approvalId"]
    record_path = violation["recordPath"]
    used_ids = frozenset() if disabled else frozenset({approval_id})
    state = _expired_state(used_ids)
    record = STALL.ReapprovalRecord(
        approval_id=approval_id,
        approver=STALL.PO_APPROVER,
        commit_oid="approval",
        path=record_path,
    )
    history = STALL.FirstParentHistory(
        commits=("activation", "expiry", "approval"),
        pr_integrations=("expiry", "approval"),
    )
    try:
        STALL.apply_reapproval(state, record, history, {record_path})
    except STALL.CheckerViolation:
        return 1
    except STALL.CheckerExecutionError:
        return 2
    return 0


def _transition_satisfaction_claim(
    case: dict[str, Any],
    _temporary_root: Path,
    disabled: bool,
) -> int:
    """軸②失効中の充足主張を既存レポート契約へ渡す。"""
    violation = case["violation"]
    try:
        grant = STALL.GrantStatus(violation["grantStatus"])
    except ValueError:
        return 2
    if grant != STALL.GrantStatus.EXPIRED:
        return 2
    sealed_asset = json.loads(BOOT_SEAL_ASSET.read_text(encoding="utf-8"))
    schema = json.loads(BOOT_REPORT_SCHEMA.read_text(encoding="utf-8"))
    report = REPORT.build_boot_report(sealed_asset, frozenset())
    if not disabled:
        report = copy.deepcopy(report)
        report["transitionMeaning"][violation["claimField"]] = violation[
            "claimValue"
        ]
    try:
        REPORT.assert_report_matches(
            sealed_asset,
            frozenset(),
            report,
            schema,
        )
    except REPORT.CheckerViolation:
        return 1
    except REPORT.CheckerExecutionError:
        return 2
    return 0


def _premature_stall_expiry(
    case: dict[str, Any],
    _temporary_root: Path,
    disabled: bool,
) -> int:
    """50本未満での失効主張を第一親上の PR 統合実測と照合する。"""
    violation = case["violation"]
    merge_count = violation["mergeCount"]
    if merge_count != STALL.STALL_MERGE_LIMIT - 1:
        return 2
    integrations = tuple(f"integration-{index}" for index in range(merge_count))
    history = STALL.FirstParentHistory(
        commits=("activation", *integrations),
        pr_integrations=integrations,
    )
    state = STALL.activate(STALL.defined_state(1), "activation")
    measured = STALL.measure_without_progress(state, history)
    is_expired = measured.grant == STALL.GrantStatus.EXPIRED
    claim = is_expired if disabled else violation["claimsExpired"]
    return 0 if claim == is_expired else 1


def _activation_record_conforms(requirements: list[dict[str, Any]]) -> bool:
    """4系統が同じ PR の必須経路で実行されたかを判定する。"""
    expected_keys = {
        "kind",
        "prId",
        "artifactPresent",
        "connectedToRequiredPath",
        "executed",
    }
    if len(requirements) != 4:
        return False
    if any(set(requirement) != expected_keys for requirement in requirements):
        return False
    kinds = {requirement["kind"] for requirement in requirements}
    pr_ids = {requirement["prId"] for requirement in requirements}
    return (
        len(kinds) == len(requirements)
        and len(pr_ids) == 1
        and all(
            requirement["artifactPresent"] is True
            and requirement["connectedToRequiredPath"] is True
            and requirement["executed"] is True
            for requirement in requirements
        )
    )


def _presence_without_execution(
    case: dict[str, Any],
    _temporary_root: Path,
    disabled: bool,
) -> int:
    """存在するが未実行の発効材料を全条項の生結果として判定する。"""
    requirements = copy.deepcopy(case["violation"]["requirements"])
    if disabled:
        for requirement in requirements:
            requirement["executed"] = True
    conforms = _activation_record_conforms(requirements)
    clauses = CLAUSES.load_and_validate_registry(ROOT)
    results = tuple(
        JUDGE.RawClauseResult(
            clause.identifier,
            JUDGE.RawOutcome.CONFORMING
            if clause.identifier != case["clauseId"] or conforms
            else JUDGE.RawOutcome.NONCONFORMING,
        )
        for clause in clauses
    )
    return JUDGE.judge_raw_results(
        ROOT,
        JUDGE.RawUnexemptedResults(results),
    )


CaseExecutor = Callable[[dict[str, Any], Path, bool], int]
_EXECUTORS: dict[str, CaseExecutor] = {
    "second-program-termination": _second_program_termination,
    "indeterminate-not-phase2": _indeterminate_not_phase2,
    "reused-reapproval-record": _reused_reapproval_record,
    "transition-satisfaction-claim": _transition_satisfaction_claim,
    "premature-stall-expiry": _premature_stall_expiry,
    "presence-without-execution": _presence_without_execution,
}


def _execute_case(case: dict[str, Any], root: Path, disabled: bool) -> int:
    """負例が選んだ既存機構を実行し 3 値の結果を返す。"""
    try:
        executor = _EXECUTORS[case["mechanism"]]
    except KeyError:
        return 2
    return executor(case, root, disabled)


def test_state_clause_set_and_existing_negative_cases_have_no_difference() -> None:
    cases = tuple(_load_case(path) for path in NEGATIVE_FIXTURES)
    expected_clauses = _state_clause_ids()
    actual_clauses = frozenset(case["clauseId"] for case in cases)
    registry = json.loads(CLAUSES_ASSET.read_text(encoding="utf-8"))
    registered = {
        entry["id"]: frozenset(entry["negativeCaseIds"])
        for entry in registry["clauses"]
        if entry["id"] in expected_clauses
    }
    fixture_ids = {
        clause_id: frozenset(
            case["caseId"] for case in cases if case["clauseId"] == clause_id
        )
        for clause_id in expected_clauses
    }

    assert len(expected_clauses) == 6
    assert actual_clauses == expected_clauses
    assert all(fixture_ids[clause_id] for clause_id in expected_clauses)
    assert registered == fixture_ids
    assert len({case["caseId"] for case in cases}) == len(cases)


def test_negative_fixtures_are_not_pytest_modules() -> None:
    assert NEGATIVE_FIXTURES
    assert all(path.suffix == ".json" for path in NEGATIVE_FIXTURES)
    assert all(not path.name.startswith("test_") for path in NEGATIVE_FIXTURES)


def test_second_program_termination_condition_is_rejected(
    tmp_path: Path,
) -> None:
    case = next(
        _load_case(path)
        for path in NEGATIVE_FIXTURES
        if _load_case(path)["mechanism"] == "second-program-termination"
    )

    assert _execute_case(case, tmp_path, disabled=False) == 1
    assert _execute_case(case, tmp_path, disabled=True) == 0


@pytest.mark.parametrize("fixture_path", NEGATIVE_FIXTURES, ids=lambda path: path.stem)
def test_each_state_negative_fails_individually(
    fixture_path: Path,
    tmp_path: Path,
) -> None:
    case = _load_case(fixture_path)

    assert _execute_case(case, tmp_path, disabled=False) == 1


@pytest.mark.parametrize("fixture_path", NEGATIVE_FIXTURES, ids=lambda path: path.stem)
def test_disabling_each_state_negative_makes_its_check_green(
    fixture_path: Path,
    tmp_path: Path,
) -> None:
    case = _load_case(fixture_path)

    assert _execute_case(case, tmp_path, disabled=True) == 0
