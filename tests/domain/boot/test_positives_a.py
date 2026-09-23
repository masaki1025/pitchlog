"""履歴 fixture で軸①の昇格と軸②の失効が実際に成立することを検査する。"""

from __future__ import annotations

import ast
import importlib
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
BACKEND_SRC = ROOT / "backend/src"
POSITIVE_DIR = ROOT / "backend/tests/domain/boot/positives_a"
CLAUSES_ASSET = ROOT / "backend/domain/boot-clauses.json"
STALL_SOURCE = BACKEND_SRC / "pitchlog/domaincheck/boot/stall.py"
POSITIVE_FIXTURES = tuple(sorted(POSITIVE_DIR.glob("*.json")))

sys.path.insert(0, str(BACKEND_SRC))
STALL = importlib.import_module("pitchlog.domaincheck.boot.stall")

_FIXTURE_KEYS = frozenset(
    {
        "schemaVersion",
        "caseId",
        "clauseIds",
        "historyType",
        "history",
        "boundary",
        "expected",
    }
)


@dataclass(frozen=True)
class _GitHistory:
    """第一親上の50統合と feature 側の取り込みマージを持つ履歴。"""

    root: Path
    activation: str
    integrations: tuple[str, ...]
    final_integration: str
    feature_side_merge: str


def _load_fixture(path: Path) -> dict[str, Any]:
    """正例Aの履歴 fixture を厳密なトップレベル形で読む。"""
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    assert frozenset(value) == _FIXTURE_KEYS
    assert value["schemaVersion"] == 1
    assert isinstance(value["caseId"], str) and value["caseId"]
    assert isinstance(value["clauseIds"], list) and value["clauseIds"]
    assert isinstance(value["historyType"], str) and value["historyType"]
    assert isinstance(value["history"], dict)
    assert isinstance(value["expected"], dict)
    return value


def _fixture_by_type(history_type: str) -> dict[str, Any]:
    """履歴種別が一意な fixture を返す。"""
    matches = [
        _load_fixture(path)
        for path in POSITIVE_FIXTURES
        if _load_fixture(path)["historyType"] == history_type
    ]
    assert len(matches) == 1
    return matches[0]


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


def _write_file(root: Path, relative: str, contents: str) -> None:
    """合成履歴の変更ファイルを書く。"""
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")


def _merge_change(root: Path, branch: str, relative: str) -> str:
    """1件の変更を no-ff で develop へ統合する。"""
    _git(root, "switch", "--quiet", "-c", branch)
    _write_file(root, relative, f"{branch}\n")
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


def _build_git_history(root: Path, case: dict[str, Any]) -> _GitHistory:
    """fixture の指定から第一親と feature 側マージを含む履歴を作る。"""
    history = case["history"]
    ordinary_count = history["ordinaryIntegrationCount"]
    total_count = history["noProgressMergeCount"]
    if ordinary_count + 1 != total_count:
        raise AssertionError("通常統合と最終統合の件数が履歴 fixture と一致しない")
    root.mkdir()
    _git(root, "init", "--quiet", "--initial-branch=develop")
    _git(root, "config", "user.email", "positive-a@example.invalid")
    _git(root, "config", "user.name", "Positive A Test")
    _write_file(root, "base.txt", "base\n")
    _git(root, "add", "base.txt")
    _git(root, "commit", "--quiet", "-m", "base")
    activation = _merge_change(
        root,
        "activation",
        "history/activation.txt",
    )

    feature_branch = history["finalIntegrationBranch"]
    _git(root, "switch", "--quiet", "-c", feature_branch)
    _write_file(root, "history/long-lived.txt", "feature work\n")
    _git(root, "add", "--all")
    _git(root, "commit", "--quiet", "-m", "long lived feature work")
    _git(root, "switch", "--quiet", "develop")

    integrations = [
        _merge_change(
            root,
            f"no-progress-{index}",
            f"history/no-progress-{index}.txt",
        )
        for index in range(ordinary_count)
    ]

    _git(root, "switch", "--quiet", feature_branch)
    _git(
        root,
        "merge",
        "--quiet",
        "--no-ff",
        "develop",
        "-m",
        history["featureSideMergeMessage"],
    )
    feature_side_merge = _git(root, "rev-parse", "HEAD")
    _git(root, "switch", "--quiet", "develop")
    _git(
        root,
        "merge",
        "--quiet",
        "--no-ff",
        feature_branch,
        "-m",
        f"Merge pull request for {feature_branch}",
    )
    final_integration = _git(root, "rev-parse", "HEAD")
    integrations.append(final_integration)
    return _GitHistory(
        root=root,
        activation=activation,
        integrations=tuple(integrations),
        final_integration=final_integration,
        feature_side_merge=feature_side_merge,
    )


@pytest.fixture(scope="module")
def stall_case() -> dict[str, Any]:
    """軸②失効の履歴 fixture を返す。"""
    return _fixture_by_type("develop-first-parent-pr-integrations")


@pytest.fixture(scope="module")
def git_history(
    tmp_path_factory: pytest.TempPathFactory,
    stall_case: dict[str, Any],
) -> _GitHistory:
    """軸②失効用の実 Git 履歴を一度だけ構築する。"""
    parent = tmp_path_factory.mktemp("positive-a-history")
    return _build_git_history(parent / "repository", stall_case)


def test_positive_a_has_exactly_two_history_cases_and_registry_links() -> None:
    cases = tuple(_load_fixture(path) for path in POSITIVE_FIXTURES)
    case_ids = frozenset(case["caseId"] for case in cases)
    expected_by_clause: dict[str, set[str]] = {}
    for case in cases:
        for clause_id in case["clauseIds"]:
            expected_by_clause.setdefault(clause_id, set()).add(case["caseId"])
    registry = json.loads(CLAUSES_ASSET.read_text(encoding="utf-8"))

    assert len(cases) == 2
    assert len(case_ids) == len(cases)
    for entry in registry["clauses"]:
        observed = set(entry["positiveCaseIds"]) & case_ids
        assert observed == expected_by_clause.get(entry["id"], set())
    assert set().union(*expected_by_clause.values()) == set(case_ids)


def test_positive_fixtures_are_not_pytest_modules() -> None:
    assert POSITIVE_FIXTURES
    assert all(path.suffix == ".json" for path in POSITIVE_FIXTURES)
    assert all(not path.name.startswith("test_") for path in POSITIVE_FIXTURES)


def test_zero_unresolved_elements_automatically_promotes_program() -> None:
    case = _fixture_by_type("unresolved-count-transition")
    history = case["history"]
    state = STALL.activate(
        STALL.defined_state(history["initialUnresolvedCount"]),
        history["activationCommit"],
    )
    for integration in history["integrations"]:
        state = STALL.observe_pr_integration(
            state,
            integration["commit"],
            integration["unresolvedCount"],
        )
    expected = case["expected"]

    assert state.program.value == expected["program"]
    assert state.grant.value == expected["grant"]
    assert state.unresolved_count == expected["unresolvedCount"]
    assert state.epoch is expected["epoch"]


def test_promoted_program_does_not_return_to_transition() -> None:
    case = _fixture_by_type("unresolved-count-transition")
    history = case["history"]
    activated = STALL.activate(
        STALL.defined_state(history["initialUnresolvedCount"]),
        history["activationCommit"],
    )
    integration = history["integrations"][0]
    promoted = STALL.observe_pr_integration(
        activated,
        integration["commit"],
        integration["unresolvedCount"],
    )

    observed = STALL.observe_pr_integration(promoted, "later-pr", 1)

    assert observed == promoted
    assert observed.program == STALL.ProgramStatus.PROMOTED


def test_no_implementation_path_writes_transition_after_initial_state() -> None:
    tree = ast.parse(STALL_SOURCE.read_text(encoding="utf-8"))
    writers: list[tuple[str, str]] = []
    for function in (
        node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    ):
        for call in (
            node for node in ast.walk(function) if isinstance(node, ast.Call)
        ):
            for keyword in call.keywords:
                value = keyword.value
                if (
                    keyword.arg == "program"
                    and isinstance(value, ast.Attribute)
                    and value.attr == "TRANSITION"
                ):
                    callable_name = (
                        call.func.id
                        if isinstance(call.func, ast.Name)
                        else ast.unparse(call.func)
                    )
                    writers.append((function.name, callable_name))

    assert writers == [("defined_state", "StallState")]


def test_fifty_first_parent_pr_integrations_without_progress_expire_grant(
    stall_case: dict[str, Any],
    git_history: _GitHistory,
) -> None:
    fixture_history = stall_case["history"]
    history = STALL.collect_first_parent_history(git_history.root)
    integrations = STALL.pr_integrations_after(history, git_history.activation)
    state = STALL.activate(
        STALL.defined_state(fixture_history["initialUnresolvedCount"]),
        git_history.activation,
    )
    measured = STALL.measure_without_progress(state, history)

    assert STALL.STALL_MERGE_LIMIT == 50
    assert fixture_history["noProgressMergeCount"] == STALL.STALL_MERGE_LIMIT
    assert integrations == git_history.integrations
    assert len(integrations) == STALL.STALL_MERGE_LIMIT
    assert measured.grant.value == stall_case["expected"]["expiredGrant"]
    assert measured.expired_at_commit == git_history.final_integration


def test_feature_side_develop_uptake_is_not_in_first_parent_population(
    git_history: _GitHistory,
) -> None:
    history = STALL.collect_first_parent_history(git_history.root)
    integrations = STALL.pr_integrations_after(history, git_history.activation)

    assert git_history.feature_side_merge not in history.commits
    assert git_history.feature_side_merge not in history.pr_integrations
    assert git_history.feature_side_merge not in integrations
    assert git_history.final_integration in integrations


def test_decrease_and_promotion_win_when_the_fiftieth_merge_is_same_change(
    stall_case: dict[str, Any],
    git_history: _GitHistory,
) -> None:
    fixture_history = stall_case["history"]
    unresolved = fixture_history["initialUnresolvedCount"]
    before_boundary = STALL.activate(
        STALL.defined_state(unresolved),
        git_history.activation,
    )
    for commit_oid in git_history.integrations[:-1]:
        before_boundary = STALL.observe_pr_integration(
            before_boundary,
            commit_oid,
            unresolved,
        )
    unchanged = STALL.observe_pr_integration(
        before_boundary,
        git_history.final_integration,
        unresolved,
    )
    decreased = STALL.observe_pr_integration(
        before_boundary,
        git_history.final_integration,
        stall_case["boundary"]["decreasedUnresolvedCount"],
    )
    promoted = STALL.observe_pr_integration(
        before_boundary,
        git_history.final_integration,
        stall_case["boundary"]["promotedUnresolvedCount"],
    )
    expected = stall_case["expected"]

    assert before_boundary.epoch.merge_count == STALL.STALL_MERGE_LIMIT - 1
    assert unchanged.grant.value == expected["expiredGrant"]
    assert decreased.grant.value == expected["decreaseGrant"]
    assert decreased.epoch.reason == STALL.EpochStartReason.DECREASE
    assert decreased.epoch.merge_count == 0
    assert promoted.program.value == expected["promotionProgram"]
    assert promoted.grant.value == expected["promotionGrant"]
    assert promoted.epoch is None
