"""通常動作の正例が BOOT-GRANT と再承認を実際に機能させることを検査する。"""

from __future__ import annotations

import ast
import copy
import importlib
import json
import subprocess
import sys
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
BACKEND_SRC = ROOT / "backend/src"
POSITIVE_DIR = ROOT / "backend/tests/domain/boot/positives_b"
CLAUSES_ASSET = ROOT / "backend/domain/boot-clauses.json"
STEP_AUTHORITIES = ROOT / "backend/domain/step-authorities.json"
BOOT_SEAL_ASSET = ROOT / "backend/domain/boot-seal.json"
CHECK_SETS_ASSET = ROOT / "backend/domain/check-sets.json"
POSITIVE_FIXTURES = tuple(sorted(POSITIVE_DIR.glob("*.json")))

sys.path.insert(0, str(BACKEND_SRC))
CLAUSES = importlib.import_module("pitchlog.domaincheck.boot.clauses")
JUDGE = importlib.import_module("pitchlog.domaincheck.boot.judge")
PHASE2 = importlib.import_module("pitchlog.domaincheck.boot.phase2")
STALL = importlib.import_module("pitchlog.domaincheck.boot.stall")

_KEYS_BY_TYPE = {
    "grant-merge": frozenset(
        {
            "schemaVersion",
            "fixtureType",
            "caseId",
            "clauseIds",
            "findingSource",
            "semanticChange",
            "expected",
        }
    ),
    "reapproval-recovery": frozenset(
        {
            "schemaVersion",
            "fixtureType",
            "caseId",
            "clauseIds",
            "record",
            "expected",
        }
    ),
    "implementation-policy": frozenset(
        {
            "schemaVersion",
            "fixtureType",
            "policyId",
            "allowGrantMerge",
            "allowReapproval",
        }
    ),
    "step-positive-b-coverage": frozenset(
        {
            "schemaVersion",
            "fixtureType",
            "implementedThroughStep",
            "evidence",
        }
    ),
}
_EVIDENCE_KEYS = frozenset(
    {"stepId", "evidenceId", "testPath", "testName"}
)


@dataclass(frozen=True)
class _ReapprovalRepository:
    """失効後の専用再承認 PR を持つ合成履歴。"""

    root: Path
    activation: str
    expiry: str
    approval: str


def _load_fixture(path: Path) -> dict[str, Any]:
    """fixture 種別ごとの厳密キー集合を検査して読む。"""
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    fixture_type = value.get("fixtureType")
    assert fixture_type in _KEYS_BY_TYPE
    assert frozenset(value) == _KEYS_BY_TYPE[fixture_type]
    assert value["schemaVersion"] == 1
    return value


def _fixture(fixture_type: str) -> dict[str, Any]:
    """指定種別が一意な fixture を返す。"""
    matches = [
        _load_fixture(path)
        for path in POSITIVE_FIXTURES
        if _load_fixture(path)["fixtureType"] == fixture_type
    ]
    assert len(matches) == 1
    return matches[0]


def _write_json(path: Path, value: object) -> None:
    """合成履歴へ可読な JSON を書く。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _git(root: Path, *arguments: str) -> str:
    """合成リポジトリで Git を実行し標準出力を返す。"""
    result = subprocess.run(
        ["git", *arguments],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _initialise_repository(root: Path) -> None:
    """Develop を持つ空の合成リポジトリを初期化する。"""
    root.mkdir()
    _git(root, "init", "--quiet", "--initial-branch=develop")
    _git(root, "config", "user.email", "positive-b@example.invalid")
    _git(root, "config", "user.name", "Positive B Test")
    (root / "base.txt").write_text("base\n", encoding="utf-8")
    _git(root, "add", "base.txt")
    _git(root, "commit", "--quiet", "-m", "base")


def _merge_change(
    root: Path,
    branch: str,
    files: Mapping[str, str],
) -> str:
    """合成 PR を no-ff で develop へ統合する。"""
    _git(root, "switch", "--quiet", "-c", branch)
    for relative, contents in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")
    _git(root, "add", "--all")
    _git(root, "commit", "--quiet", "-m", f"{branch} change")
    _git(root, "switch", "--quiet", "develop")
    _git(
        root,
        "merge",
        "--quiet",
        "--no-ff",
        branch,
        "-m",
        f"Merge pull request for {branch}",
    )
    return _git(root, "rev-parse", "HEAD")


def _all_boot_clauses_conform() -> bool:
    """既存判定器へ全12条項の免除前適合結果を渡す。"""
    clauses = CLAUSES.load_and_validate_registry(ROOT)
    results = JUDGE.RawUnexemptedResults(
        tuple(
            JUDGE.RawClauseResult(
                clause.identifier,
                JUDGE.RawOutcome.CONFORMING,
            )
            for clause in clauses
        )
    )
    return JUDGE.judge_raw_results(ROOT, results) == 0


def _grant_allows_sealed_failure(case: dict[str, Any], deny_all: bool) -> bool:
    """既存状態・段階2・集合宣言から授権のマージ判定を合成する。"""
    sealed_asset = json.loads(BOOT_SEAL_ASSET.read_text(encoding="utf-8"))
    check_sets = json.loads(CHECK_SETS_ASSET.read_text(encoding="utf-8"))
    element = next(
        item
        for item in sealed_asset["elements"]
        if item["constructor"] == "declaration_absence"
        and isinstance(item["arguments"].get("target"), str)
    )
    target_id = element["arguments"]["target"]
    finding_id = element["id"]
    universe = PHASE2.load_target_universe(ROOT)
    state = STALL.activate(
        STALL.defined_state(len(sealed_asset["elements"])),
        "activation",
    )
    decision = PHASE2.classify_phase2(
        state,
        universe,
        PHASE2.SemanticSnapshot.empty(),
        PHASE2.SemanticSnapshot.empty(),
    )
    exemption = check_sets["exemptionDecision"]
    predicate = exemption["predicate"]
    sealed_ids = {item["id"] for item in sealed_asset["elements"]}
    declared_rule_is_valid = (
        case["findingSource"] == "backend/domain/boot-seal.json#elements"
        and case["semanticChange"] == "no-phase2-target-added"
        and predicate["operator"] == "set-subset"
        and set(exemption["dependsOnlyOn"])
        == {"findingId", "sealedSet.unresolvedFindingIds"}
    )
    normally_allowed = (
        declared_rule_is_valid
        and state.grant == STALL.GrantStatus.ACTIVE
        and {finding_id} <= sealed_ids
        and target_id not in decision.phase2_target_ids
        and _all_boot_clauses_conform()
    )
    return normally_allowed and not deny_all


def _assert_grant_merge_succeeds(
    case: dict[str, Any],
    deny_all: bool,
    root: Path,
) -> None:
    """授権された候補 PR を実 Git 履歴へマージできることを要求する。"""
    _initialise_repository(root)
    _git(root, "switch", "--quiet", "-c", "sealed-failure-change")
    _write_json(root / "finding.json", {"source": case["findingSource"]})
    _git(root, "add", "finding.json")
    _git(root, "commit", "--quiet", "-m", "change with sealed failure")
    candidate = _git(root, "rev-parse", "HEAD")
    _git(root, "switch", "--quiet", "develop")
    before = _git(root, "rev-parse", "HEAD")
    allowed = _grant_allows_sealed_failure(case, deny_all)
    if allowed:
        _git(
            root,
            "merge",
            "--quiet",
            "--no-ff",
            "sealed-failure-change",
            "-m",
            "Merge granted sealed failure change",
        )
    after = _git(root, "rev-parse", "HEAD")
    parents = _git(root, "show", "-s", "--format=%P", after).split()

    assert allowed is case["expected"]["mergeAllowed"]
    assert (after != before and candidate in parents) is case["expected"][
        "candidateMerged"
    ]


def _approval_json(record: Mapping[str, object]) -> str:
    """既存再承認機構の厳密キー集合を持つ記録を返す。"""
    return json.dumps(
        {
            "schemaVersion": 1,
            "approvalId": record["approvalId"],
            "approver": record["approver"],
        },
        ensure_ascii=False,
        indent=2,
    ) + "\n"


def _build_reapproval_repository(
    root: Path,
    case: dict[str, Any],
) -> _ReapprovalRepository:
    """失効より後に専用再承認 PR がある Git 履歴を作る。"""
    _initialise_repository(root)
    activation = _merge_change(
        root,
        "activation",
        {"activation.txt": "active\n"},
    )
    expiry = _merge_change(
        root,
        "expiry",
        {"expiry.txt": "fiftieth merge\n"},
    )
    record = case["record"]
    approval = _merge_change(
        root,
        "valid-reapproval",
        {record["path"]: _approval_json(record)},
    )
    return _ReapprovalRepository(root, activation, expiry, approval)


def _assert_reapproval_recovers(
    case: dict[str, Any],
    deny_all: bool,
    root: Path,
) -> None:
    """正当な再承認が失効済み授権を実際に回復することを要求する。"""
    repository = _build_reapproval_repository(root, case)
    state = STALL.activate(STALL.defined_state(1), repository.activation)
    for index in range(STALL.STALL_MERGE_LIMIT - 1):
        state = STALL.observe_pr_integration(
            state,
            f"no-progress-{index}",
            1,
        )
    expired = STALL.observe_pr_integration(state, repository.expiry, 1)
    recovered = expired
    if not deny_all:
        recovered = STALL.reapprove_from_git(
            repository.root,
            expired,
            case["record"]["path"],
            repository.approval,
        )
    expected = case["expected"]

    assert expired.grant == STALL.GrantStatus.EXPIRED
    assert recovered.grant.value == expected["grant"]
    assert recovered.epoch.reason.value == expected["epochReason"]
    assert recovered.epoch.merge_count == expected["mergeCount"]


def _assert_positive_b_coverage(
    target_step_ids: Collection[int],
    authority_rows: Collection[Mapping[str, object]],
    evidence: Collection[Mapping[str, object]],
) -> None:
    """任意の対象ステップ集合について正例B要求と証跡を双方向照合する。"""
    def step_id(item: Mapping[str, object]) -> int:
        """台帳または証跡から Boolean でないステップ ID を返す。"""
        value = item["stepId"]
        if not isinstance(value, int) or isinstance(value, bool):
            raise AssertionError("stepIdが整数でない")
        return value

    targets = frozenset(target_step_ids)
    rows_by_id = {step_id(row): row for row in authority_rows}
    missing_rows = targets - frozenset(rows_by_id)
    if missing_rows:
        raise AssertionError(f"対象ステップの台帳行が不足={sorted(missing_rows)!r}")
    required = frozenset(
        step_id
        for step_id in targets
        if rows_by_id[step_id]["requiresPositiveB"] is True
    )
    forbidden = targets - required
    observed = frozenset(
        step_id(item)
        for item in evidence
        if step_id(item) in targets
    )
    missing = required - observed
    unexpected = forbidden & observed
    if missing or unexpected:
        raise AssertionError(
            "正例B証跡の集合差: "
            f"不足={sorted(missing)!r}, "
            f"不要な証跡={sorted(unexpected)!r}"
        )


def _coverage_fixture() -> dict[str, Any]:
    """実装済み範囲の正例B証跡 fixture を返す。"""
    return _fixture("step-positive-b-coverage")


def test_positive_b_case_ids_are_linked_without_overwriting_positive_a() -> None:
    cases = (_fixture("grant-merge"), _fixture("reapproval-recovery"))
    case_ids = frozenset(case["caseId"] for case in cases)
    expected_by_clause: dict[str, set[str]] = {}
    for case in cases:
        for clause_id in case["clauseIds"]:
            expected_by_clause.setdefault(clause_id, set()).add(case["caseId"])
    registry = json.loads(CLAUSES_ASSET.read_text(encoding="utf-8"))

    for entry in registry["clauses"]:
        observed = set(entry["positiveCaseIds"]) & case_ids
        assert observed == expected_by_clause.get(entry["id"], set())


def test_positive_fixtures_are_not_pytest_modules() -> None:
    assert POSITIVE_FIXTURES
    assert all(path.suffix == ".json" for path in POSITIVE_FIXTURES)
    assert all(not path.name.startswith("test_") for path in POSITIVE_FIXTURES)


def test_sealed_failure_change_is_actually_merged_by_grant(
    tmp_path: Path,
) -> None:
    _assert_grant_merge_succeeds(
        _fixture("grant-merge"),
        deny_all=False,
        root=tmp_path / "grant",
    )


def test_valid_reapproval_actually_recovers_grant(tmp_path: Path) -> None:
    _assert_reapproval_recovers(
        _fixture("reapproval-recovery"),
        deny_all=False,
        root=tmp_path / "reapproval",
    )


def test_deny_all_breaks_the_grant_normal_operation(tmp_path: Path) -> None:
    policy = _fixture("implementation-policy")
    assert policy["policyId"] == "deny-all"

    with pytest.raises(AssertionError):
        _assert_grant_merge_succeeds(
            _fixture("grant-merge"),
            deny_all=not policy["allowGrantMerge"],
            root=tmp_path / "deny-grant",
        )


def test_deny_all_breaks_the_reapproval_normal_operation(tmp_path: Path) -> None:
    policy = _fixture("implementation-policy")
    assert policy["policyId"] == "deny-all"

    with pytest.raises(AssertionError):
        _assert_reapproval_recovers(
            _fixture("reapproval-recovery"),
            deny_all=not policy["allowReapproval"],
            root=tmp_path / "deny-reapproval",
        )


def test_positive_b_evidence_references_existing_test_functions() -> None:
    coverage = _coverage_fixture()
    evidence_ids: list[str] = []
    for item in coverage["evidence"]:
        assert frozenset(item) == _EVIDENCE_KEYS
        path = Path(item["testPath"])
        assert not path.is_absolute() and ".." not in path.parts
        tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
        function_names = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        }
        assert item["testName"] in function_names
        evidence_ids.append(item["evidenceId"])
    assert len(evidence_ids) == len(set(evidence_ids))


def test_positive_b_coverage_passes_for_steps_one_through_twenty_five() -> None:
    coverage = _coverage_fixture()
    registry = json.loads(STEP_AUTHORITIES.read_text(encoding="utf-8"))
    target_steps = frozenset(range(1, coverage["implementedThroughStep"] + 1))

    _assert_positive_b_coverage(target_steps, registry["steps"], coverage["evidence"])


def test_missing_positive_b_for_required_step_fails_set_difference() -> None:
    coverage = _coverage_fixture()
    registry = json.loads(STEP_AUTHORITIES.read_text(encoding="utf-8"))
    target_steps = frozenset(range(1, coverage["implementedThroughStep"] + 1))
    required_step = next(
        row["stepId"]
        for row in registry["steps"]
        if row["stepId"] in target_steps and row["requiresPositiveB"] is True
    )
    changed = [
        item for item in coverage["evidence"] if item["stepId"] != required_step
    ]

    with pytest.raises(AssertionError, match="不足"):
        _assert_positive_b_coverage(target_steps, registry["steps"], changed)


def test_positive_b_for_nonrequired_step_fails_reverse_difference() -> None:
    coverage = _coverage_fixture()
    registry = json.loads(STEP_AUTHORITIES.read_text(encoding="utf-8"))
    target_steps = frozenset(range(1, coverage["implementedThroughStep"] + 1))
    nonrequired_step = next(
        row["stepId"]
        for row in registry["steps"]
        if row["stepId"] in target_steps and row["requiresPositiveB"] is False
    )
    changed = copy.deepcopy(coverage["evidence"])
    synthetic = copy.deepcopy(changed[0])
    synthetic["stepId"] = nonrequired_step
    synthetic["evidenceId"] = "synthetic-unrequired-positive-b"
    changed.append(synthetic)

    with pytest.raises(AssertionError, match="不要な証跡"):
        _assert_positive_b_coverage(target_steps, registry["steps"], changed)
