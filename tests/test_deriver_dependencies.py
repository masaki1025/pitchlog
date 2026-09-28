"""requiredSet 導出器の実行時ファイル依存を検証する。"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from collections.abc import Callable
from copy import deepcopy
from dataclasses import replace
from pathlib import Path, PurePosixPath
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CHECKER_PATH = REPOSITORY_ROOT / "scripts/check_deriver_dependencies.py"
DESCRIPTOR_CHECKER_PATH = REPOSITORY_ROOT / "scripts/check_input_axes_descriptor.py"
FREEZE_CHECKER_PATH = REPOSITORY_ROOT / "scripts/state_transition_freeze.py"
POLICY_PATH = (
    REPOSITORY_ROOT
    / "contracts/state-transition/deriver_dependency_policy_v1.json"
)
ROW_RULES_PATH = (
    REPOSITORY_ROOT
    / "contracts/state-transition/required_set_row_rules_v1.json"
)
VOCABULARY_MANIFEST_PATH = (
    REPOSITORY_ROOT / "contracts/vocabulary/vocabulary_manifest_v1.json"
)
VOCABULARY_SEED_PATH = (
    REPOSITORY_ROOT / "contracts/vocabulary/input_vocabulary_v1.json"
)
REQUIREMENTS_PATH = (
    REPOSITORY_ROOT
    / "docs/requirements/requirements-pitchlog-2026-07-22.md"
)
DESIGN_PATH = (
    REPOSITORY_ROOT / "docs/features/appendix-e-golden-vectors/design.md"
)
DISALLOWED_PATH = REPOSITORY_ROOT / "pyproject.toml"


def _load_module(name: str, path: Path) -> Any:
    """テスト対象を sys.path の変更なしで読み込む。"""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_load_module("state_transition_freeze", FREEZE_CHECKER_PATH)
_load_module("check_input_axes_descriptor", DESCRIPTOR_CHECKER_PATH)
checker = _load_module("check_deriver_dependencies", CHECKER_PATH)


def _policy() -> Any:
    """リポジトリの依存宣言を返す。"""
    return checker.validate_repository_policy(REPOSITORY_ROOT)


def _first_rule(policy: Any) -> Any:
    """宣言順で最初の導出器規則を返す。"""
    return next(iter(policy.derivers.values()))


def _json(path: Path) -> Any:
    """テスト用にJSON資産を読み込む。"""
    return json.loads(path.read_text(encoding="utf-8"))


def _row_requirement_documents() -> tuple[Any, Any, Any, frozenset[str]]:
    """純粋導出関数へ渡す実資産の複製を返す。"""
    clause_ids = checker.descriptor_checker.load_clause_ids_from_paths(
        REPOSITORY_ROOT,
        (PurePosixPath(REQUIREMENTS_PATH.relative_to(REPOSITORY_ROOT).as_posix()),),
    )
    return (
        _json(ROW_RULES_PATH),
        _json(VOCABULARY_MANIFEST_PATH),
        _json(VOCABULARY_SEED_PATH),
        frozenset(f"req:{clause_id}" for clause_id in clause_ids),
    )


def _assert_disallowed_read_fails(operation: Callable[[], object]) -> None:
    """allowlist 外の読み取りが監査違反になることを確認する。"""
    policy = _policy()
    rule = _first_rule(policy)
    with pytest.raises(checker.DeriverDependencyError, match="allowlist外"):
        checker.trace_deriver_file_reads(
            REPOSITORY_ROOT,
            policy,
            rule.deriver_id,
            operation,
        )


def test_repository_deriver_dependency_policy_is_valid() -> None:
    policy = _policy()
    assert POLICY_PATH.is_file()
    assert policy.derivers
    for rule in policy.derivers.values():
        assert rule.allowed_read_paths
        assert all((REPOSITORY_ROOT / path).is_file() for path in rule.allowed_read_paths)


def test_row_requirement_axis_assignments_cover_all_vocabulary_axes() -> None:
    """語彙16軸がresultId源か非resultId源へちょうど一度分類される。"""
    rules, _, seed, _ = _row_requirement_documents()
    assignments = rules["axisAssignments"]
    assert len(assignments) == 16
    assert {item["axisId"] for item in assignments} == {
        axis["axisId"] for axis in seed["axes"]
    }
    assert {
        item["axisId"]: item.get("eventKind")
        for item in assignments
        if item["role"] == "result-id-source"
    } == {
        "batting-result": "batting-result",
        "secondary-result": "secondary-result",
        "strategy-category": "runner-event",
        "pitcher-pickoff-destination": "runner-event",
        "catcher-pickoff-destination": "runner-event",
    }


def test_unclassified_existing_vocabulary_axis_fails() -> None:
    """既存軸を分類宣言から落とす変異を拒否する。"""
    rules, manifest, seed, clause_ids = _row_requirement_documents()
    rules["axisAssignments"].pop()
    with pytest.raises(checker.DeriverDependencyError, match="語彙軸分類がexact-set不一致"):
        checker.derive_row_requirements_from_documents(
            rules, manifest, seed, clause_ids
        )


def test_future_vocabulary_axis_without_classification_fails() -> None:
    """将来軸を追加して分類を追随しない変異を拒否する。"""
    rules, manifest, seed, clause_ids = _row_requirement_documents()
    seed["axes"].append(
        {
            "axisId": "future-axis",
            "sourceRef": "test-only",
            "entries": [
                {
                    "id": "future-axis.value",
                    "initialDisplayName": "テスト",
                    "classification": "test",
                }
            ],
        }
    )
    with pytest.raises(checker.DeriverDependencyError, match="語彙軸分類がexact-set不一致"):
        checker.derive_row_requirements_from_documents(
            rules, manifest, seed, clause_ids
        )


def test_repository_row_requirements_have_declared_count_and_sources() -> None:
    """5規則から47行を導出し、全要求に実在条文IDを残す。"""
    policy = _policy()
    requirements, trace = checker.derive_repository_row_requirements(
        REPOSITORY_ROOT, policy
    )
    assert len(requirements) == 47
    assert len({item.identity for item in requirements}) == 47
    assert all(item.source_clause_ids for item in requirements)
    assert set(trace.observed_read_paths) == set(
        policy.derivers["required-set-row-requirements"].allowed_read_paths
    )
    assert {
        event_kind: sum(item.event_kind == event_kind for item in requirements)
        for event_kind in {item.event_kind for item in requirements}
    } == {
        "batting-result": 27,
        "secondary-result": 11,
        "runner-event": 9,
    }


def test_missing_normative_row_requirement_fails() -> None:
    """導出した規範行要求を1行削る変異を拒否する。"""
    requirements, _ = checker.derive_repository_row_requirements(REPOSITORY_ROOT)
    with pytest.raises(checker.DeriverDependencyError, match="exact-set不一致"):
        checker.validate_row_requirement_coverage(requirements, requirements[:-1])


def test_unrequired_normative_row_requirement_fails() -> None:
    """要求集合にない規範行要求を1行足す変異を拒否する。"""
    requirements, _ = checker.derive_repository_row_requirements(REPOSITORY_ROOT)
    unexpected = replace(requirements[0], partition_id="unexpected-test-partition")
    with pytest.raises(checker.DeriverDependencyError, match="exact-set不一致"):
        checker.validate_row_requirement_coverage(
            requirements, (*requirements, unexpected)
        )


def test_partition_rule_without_source_clause_fails() -> None:
    """典拠条文IDを空にした分割規則を拒否する。"""
    rules, manifest, seed, clause_ids = _row_requirement_documents()
    mutant = deepcopy(rules)
    mutant["partitionRules"][1]["sourceClauseIds"] = []
    with pytest.raises(checker.DeriverDependencyError, match="典拠の無い分割規則"):
        checker.derive_row_requirements_from_documents(
            mutant, manifest, seed, clause_ids
        )


def test_claim_boundary_limits_the_claim_to_executable_derivers() -> None:
    policy = _policy()
    boundary = policy.claim_boundary
    assert boundary["subject"] == "executable-derivers-only"
    assert boundary["expanderCoverage"] == "not-covered-step-42"
    assert boundary["notGuaranteed"]
    design = DESIGN_PATH.read_text(encoding="utf-8")
    assert "実行可能な導出器の追跡対象呼出区間で観測したファイル読み取りだけ" in design
    assert "手作業で何を読んだか" in design


def test_declared_read_is_traced_and_allowed() -> None:
    policy = _policy()
    rule = _first_rule(policy)
    allowed_path = REPOSITORY_ROOT / rule.allowed_read_paths[0]

    value, trace = checker.trace_deriver_file_reads(
        REPOSITORY_ROOT,
        policy,
        rule.deriver_id,
        lambda: allowed_path.read_bytes(),
    )

    assert value
    assert trace.observed_read_paths == (rule.allowed_read_paths[0],)


def test_builtin_open_outside_allowlist_fails() -> None:
    def read_with_builtin() -> str:
        with open(DISALLOWED_PATH, encoding="utf-8") as stream:
            return stream.read()

    _assert_disallowed_read_fails(read_with_builtin)


def test_pathlib_read_outside_allowlist_fails() -> None:
    _assert_disallowed_read_fails(
        lambda: DISALLOWED_PATH.read_text(encoding="utf-8")
    )


def test_os_open_outside_allowlist_fails() -> None:
    def read_with_os_open() -> int:
        descriptor = os.open(DISALLOWED_PATH, os.O_RDONLY)
        os.close(descriptor)
        return descriptor

    _assert_disallowed_read_fails(read_with_os_open)


def test_swallowed_audit_exception_still_fails() -> None:
    def swallow_violation() -> None:
        try:
            DISALLOWED_PATH.read_bytes()
        except checker.DeriverDependencyError:
            pass

    _assert_disallowed_read_fails(swallow_violation)


def test_untraced_subprocess_is_fail_closed() -> None:
    policy = _policy()
    rule = _first_rule(policy)

    def spawn_child() -> None:
        subprocess.run([sys.executable, "-c", "pass"], check=True)

    with pytest.raises(checker.DeriverDependencyError, match="未追跡の子プロセス"):
        checker.trace_deriver_file_reads(
            REPOSITORY_ROOT,
            policy,
            rule.deriver_id,
            spawn_child,
        )
