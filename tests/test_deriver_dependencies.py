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
INPUT_AXES_DESCRIPTOR_PATH = (
    REPOSITORY_ROOT
    / "contracts/state-transition/input_axes_descriptor_v1.json"
)
CLAUSE_BRANCH_REGISTER_PATH = (
    REPOSITORY_ROOT
    / "contracts/state-transition/clause_branch_register_v1.json"
)


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


def _input_axes_descriptor() -> Any:
    """入力座標要求の純粋導出へ渡す descriptor の複製を返す。"""
    return _json(INPUT_AXES_DESCRIPTOR_PATH)


def _game_end_required_set() -> Any:
    """実資産から独立導出した終了判定要求集合を返す。"""
    required_set, _ = checker.derive_repository_game_end_required_set(
        REPOSITORY_ROOT
    )
    return required_set


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


def test_repository_input_coordinate_requirements_are_per_axis_values() -> None:
    """26軸から軸ごとの150要求を導出し、軸間直積を主張しない。"""
    policy = _policy()
    requirements, trace = checker.derive_repository_input_coordinate_requirements(
        REPOSITORY_ROOT, policy
    )
    descriptor = _input_axes_descriptor()
    boundary = descriptor["inputCoordinateCoverage"]["axisCombinationBoundary"]

    assert len(requirements) == 150
    assert len({item.identity for item in requirements}) == 150
    assert {item.axis_id for item in requirements} == {
        axis["axisId"] for axis in descriptor["stateTransitionAxes"]
    }
    assert boundary["mechanicallyGuaranteed"] == "per-axis-value-coverage-only"
    assert boundary["notMechanicallyGuaranteed"] == (
        "cross-axis-combination-coverage"
    )
    assert set(trace.observed_read_paths) == set(
        policy.derivers["required-set-input-coordinates"].allowed_read_paths
    )


def test_input_coordinate_bindings_use_normative_row_natural_keys() -> None:
    """軸の適用層と自然キー上の役割がdescriptor宣言から残る。"""
    requirements = checker.derive_input_coordinate_requirements_from_descriptor(
        _input_axes_descriptor()
    )
    by_axis_and_value = {
        item.identity: item
        for item in requirements
    }
    assert by_axis_and_value[("event.perPitch.kind", '"batting-result"')].natural_key_field == (
        "eventKind"
    )
    result_requirement = by_axis_and_value[("event.perPitch.resultId", '"単打"')]
    assert result_requirement.natural_key_field == "resultId"
    assert result_requirement.natural_key_value_projection == (
        "vocabulary-id-to-initial-display-name"
    )
    assert by_axis_and_value[("event.operationKind", '"substitution"')].row_layers == (
        "operationRows",
    )
    assert by_axis_and_value[("event.operationPayload", '"not-applicable"')].row_layers == (
        "matrixRows",
        "undoRows",
    )
    assert by_axis_and_value[("history.depth", "0")].natural_key_field == (
        "precondition"
    )


def test_conditional_coordinate_values_follow_declared_adoption_state() -> None:
    """FR-040の採用状態で条件付き4値を採用または除外する。"""
    requirements = checker.derive_input_coordinate_requirements_from_descriptor(
        _input_axes_descriptor()
    )
    not_adopted = checker.active_input_coordinate_requirements(
        requirements, {"req:FR-040": "not-adopted"}
    )
    adopted = checker.active_input_coordinate_requirements(
        requirements, {"req:FR-040": "adopted"}
    )

    assert len(not_adopted) == 146
    assert len(adopted) == 150
    assert not any(
        item.when_clause_id is not None for item in not_adopted
    )


def test_undecidable_conditional_coordinate_state_fails() -> None:
    """条件付き値の採用状態を与えない経路をfail-closedにする。"""
    requirements = checker.derive_input_coordinate_requirements_from_descriptor(
        _input_axes_descriptor()
    )
    with pytest.raises(checker.DeriverDependencyError, match="採用状態を判定できない"):
        checker.active_input_coordinate_requirements(requirements, {})


def test_all_rows_with_only_one_case_each_do_not_cover_input_coordinates() -> None:
    """全47行へ各1 caseだけ置いても軸ごとの全coverage値を満たせない。"""
    rows, _ = checker.derive_repository_row_requirements(REPOSITORY_ROOT)
    requirements, _ = checker.derive_repository_input_coordinate_requirements(
        REPOSITORY_ROOT
    )
    active = checker.active_input_coordinate_requirements(
        requirements, {"req:FR-040": "not-adopted"}
    )
    one_matrix_case = tuple(
        next(
            item
            for item in active
            if item.axis_id == axis_id and "matrixRows" in item.row_layers
        )
        for axis_id in dict.fromkeys(
            item.axis_id for item in active if "matrixRows" in item.row_layers
        )
    )
    one_case_for_every_row = one_matrix_case * len(rows)

    assert len(rows) == 47
    with pytest.raises(checker.DeriverDependencyError, match="入力座標要求がexact-set不一致"):
        checker.validate_input_coordinate_coverage(active, one_case_for_every_row)


def test_repository_game_end_required_set_follows_descriptor_combinations() -> None:
    """終了側だけのペアワイズと境界値×軸値をdescriptorから導出する。"""
    policy = _policy()
    required_set, trace = checker.derive_repository_game_end_required_set(
        REPOSITORY_ROOT, policy
    )
    descriptor = _input_axes_descriptor()
    valid_value_counts = [
        len(axis["boundaryValues"]) for axis in descriptor["gameEndAxes"]
    ]
    invalid_value_count = sum(
        len(axis["invalidBoundaryValues"])
        for axis in descriptor["gameEndAxes"]
    )
    state_event_coordinates = tuple(
        item
        for item in checker.derive_input_coordinate_requirements_from_descriptor(
            descriptor
        )
        if item.axis_id.split(".", 1)[0] in {"state", "event"}
    )
    pairwise_count = sum(
        left_count * right_count
        for index, left_count in enumerate(valid_value_counts)
        for right_count in valid_value_counts[index + 1 :]
    )
    boundary_coordinate_count = sum(valid_value_counts) * len(
        state_event_coordinates
    )

    assert len(required_set.pairwise_requirements) == pairwise_count
    assert (
        len(required_set.boundary_coordinate_requirements)
        == boundary_coordinate_count
    )
    assert len(required_set.invalid_boundary_requirements) == invalid_value_count
    assert required_set.clause_branch_requirements
    assert required_set.requirement_count == (
        pairwise_count
        + boundary_coordinate_count
        + invalid_value_count
        + len(required_set.clause_branch_requirements)
    )
    assert len({item.identity for item in required_set.requirements}) == (
        required_set.requirement_count
    )
    assert set(trace.observed_read_paths) == set(
        policy.derivers["required-set-game-end"].allowed_read_paths
    )
    assert all(
        "expander" not in path.as_posix()
        for path in trace.observed_read_paths
    )


def test_game_end_required_set_keeps_state_event_axis_combinations_deferred() -> None:
    """終了境界値を軸値ごとに組み、状態・イベント軸間の直積は作らない。"""
    required_set = _game_end_required_set()
    identities = {
        (
            item.game_end_axis_id,
            item.game_end_value_identity,
            item.coordinate_axis_id,
            item.coordinate_value_identity,
        )
        for item in required_set.boundary_coordinate_requirements
    }

    assert len(identities) == len(required_set.boundary_coordinate_requirements)
    assert all(
        item.coordinate_axis_id.split(".", 1)[0] in {"state", "event"}
        for item in required_set.boundary_coordinate_requirements
    )


def test_default_nine_inning_setting_alone_does_not_cover_game_end_requirements() -> None:
    """規定9回の境界値だけを全状態・イベント軸へ当てても不足とする。"""
    required_set = _game_end_required_set()
    descriptor = _input_axes_descriptor()
    regulation_axis_id = descriptor["gameEndAxes"][0]["axisId"]
    nine_identity = checker.descriptor_checker._canonical_json_text(9)
    nine_inning_only = tuple(
        item
        for item in required_set.boundary_coordinate_requirements
        if item.game_end_axis_id == regulation_axis_id
        and item.game_end_value_identity == nine_identity
    )

    assert nine_inning_only
    with pytest.raises(checker.DeriverDependencyError, match="終了判定要求がexact-set不一致"):
        checker.validate_game_end_requirement_coverage(
            required_set, nine_inning_only
        )


def test_game_end_required_set_covers_all_declared_game_outcome_branches() -> None:
    """独立導出後にGAME-*の4役割をregisterと双方向に突合する。"""
    required_set = _game_end_required_set()
    register = _json(CLAUSE_BRANCH_REGISTER_PATH)
    outcome_ids = checker.validate_game_end_outcome_branch_coverage(
        required_set, register
    )

    assert set(outcome_ids) == set(register["gameEndOutcomeBranches"].values())
    assert len(outcome_ids) == len(register["gameEndOutcomeBranches"])


def test_game_end_outcome_with_uncovered_clause_branch_fails() -> None:
    """GAME-*が参照する下位分岐をrequiredSetから落とす変異を拒否する。"""
    required_set = _game_end_required_set()
    register = _json(CLAUSE_BRANCH_REGISTER_PATH)
    first_outcome_id = next(iter(register["gameEndOutcomeBranches"].values()))
    first_outcome = next(
        branch
        for branch in register["branches"]
        if branch["branchId"] == first_outcome_id
    )
    omitted_branch_id = first_outcome["relatedClauseBranchIds"][0]
    mutant = replace(
        required_set,
        clause_branch_requirements=tuple(
            requirement
            for requirement in required_set.clause_branch_requirements
            if requirement.branch_id != omitted_branch_id
        ),
    )

    with pytest.raises(checker.DeriverDependencyError, match="requiredSetにない"):
        checker.validate_game_end_outcome_branch_coverage(mutant, register)


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
