"""cases 展開器の実行時ファイル依存を検証する。"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EXPANDER_CHECKER_PATH = REPOSITORY_ROOT / "scripts/check_expander_dependencies.py"
DERIVER_CHECKER_PATH = REPOSITORY_ROOT / "scripts/check_deriver_dependencies.py"
DESCRIPTOR_CHECKER_PATH = REPOSITORY_ROOT / "scripts/check_input_axes_descriptor.py"
FREEZE_CHECKER_PATH = REPOSITORY_ROOT / "scripts/state_transition_freeze.py"
POLICY_PATH = (
    REPOSITORY_ROOT
    / "contracts/state-transition/expander_dependency_policy_v1.json"
)
DESIGN_PATH = REPOSITORY_ROOT / "docs/features/appendix-e-golden-vectors/design.md"
DISALLOWED_PATH = REPOSITORY_ROOT / "pyproject.toml"
MANUAL_FIXTURE_PATH = (
    REPOSITORY_ROOT
    / "contracts/state-transition/state_transition_manual_fixtures_v1.json"
)
CONTRACT_PATH = (
    REPOSITORY_ROOT / "contracts/state-transition/state_transition_contract_v1.json"
)
SCHEMA_PATH = (
    REPOSITORY_ROOT / "contracts/state-transition/state_transition_contract_schema_v1.json"
)
GAME_END_CONTRACT_PATH = (
    REPOSITORY_ROOT / "contracts/state-transition/game_end_contract_v1.json"
)
GAME_END_SCHEMA_PATH = (
    REPOSITORY_ROOT / "contracts/state-transition/game_end_contract_schema_v1.json"
)
GAME_END_MANUAL_FIXTURE_PATH = (
    REPOSITORY_ROOT / "contracts/state-transition/game_end_manual_fixtures_v1.json"
)
BRANCH_ROW_MAPPING_PATH = (
    REPOSITORY_ROOT / "contracts/state-transition/branch_row_mapping_v1.json"
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
schema_checker = _load_module("check_input_axes_descriptor", DESCRIPTOR_CHECKER_PATH)
_load_module("check_deriver_dependencies", DERIVER_CHECKER_PATH)
checker = _load_module("check_expander_dependencies", EXPANDER_CHECKER_PATH)
representative_selection = _load_module(
    "representative_selection",
    REPOSITORY_ROOT / "scripts/representative_selection.py",
)
_load_module(
    "state_transition_normalization",
    REPOSITORY_ROOT / "scripts/state_transition_normalization.py",
)
state_transition_expander = _load_module(
    "expand_state_transition_cases",
    REPOSITORY_ROOT / "scripts/expand_state_transition_cases.py",
)
game_end_expander = _load_module(
    "expand_game_end_cases",
    REPOSITORY_ROOT / "scripts/expand_game_end_cases.py",
)


def _policy() -> Any:
    """リポジトリの展開器依存宣言を返す。"""
    return checker.validate_repository_policy(REPOSITORY_ROOT)


def _first_rule(policy: Any) -> Any:
    """宣言順で最初の展開器規則を返す。"""
    return next(iter(policy.expanders.values()))


def _assert_disallowed_read_fails(operation: Callable[[], object]) -> None:
    """allowlist 外の読み取りが監査違反になることを確認する。"""
    policy = _policy()
    rule = _first_rule(policy)
    with pytest.raises(checker.ExpanderDependencyError, match="allowlist外"):
        checker.trace_expander_file_reads(
            REPOSITORY_ROOT,
            policy,
            rule.expander_id,
            operation,
        )


def test_repository_expander_dependency_policy_is_valid() -> None:
    policy = _policy()
    assert POLICY_PATH.is_file()
    assert policy.expanders
    for rule in policy.expanders.values():
        assert rule.allowed_read_paths
        assert any((REPOSITORY_ROOT / path).is_file() for path in rule.allowed_read_paths)


def test_claim_boundary_limits_the_claim_to_executable_expanders() -> None:
    policy = _policy()
    boundary = policy.claim_boundary
    assert boundary["subject"] == "executable-expanders-only"
    assert boundary["deriverCoverage"] == "not-covered-step-41-policy"
    assert boundary["fixtureIndependenceClaim"] == (
        "manual-fixtures-independent-from-expander-only"
    )
    assert boundary["clauseBranchRegisterIndependence"] == "not-claimed"
    assert "independence-from-clause-branch-register" in boundary["notGuaranteed"]
    design = DESIGN_PATH.read_text(encoding="utf-8")
    assert "実行可能な展開器の追跡対象呼出区間で観測したファイル読み取りだけ" in design
    assert "`clauseBranchRegister` からの独立を主張しない" in design


def test_declared_read_is_traced_and_allowed() -> None:
    policy = _policy()
    rule = _first_rule(policy)
    allowed_relative = next(
        path
        for path in rule.allowed_read_paths
        if (REPOSITORY_ROOT / path).is_file()
    )
    allowed_path = REPOSITORY_ROOT / allowed_relative

    value, trace = checker.trace_expander_file_reads(
        REPOSITORY_ROOT,
        policy,
        rule.expander_id,
        lambda: allowed_path.read_bytes(),
    )

    assert value
    assert trace.observed_read_paths == (allowed_relative,)


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
        except checker.ExpanderDependencyError:
            pass
        except ValueError:
            pass

    _assert_disallowed_read_fails(swallow_violation)


def test_untraced_subprocess_is_fail_closed() -> None:
    policy = _policy()
    rule = _first_rule(policy)

    def spawn_child() -> None:
        subprocess.run([sys.executable, "-c", "pass"], check=True)

    with pytest.raises(checker.ExpanderDependencyError, match="未追跡の子プロセス"):
        checker.trace_expander_file_reads(
            REPOSITORY_ROOT,
            policy,
            rule.expander_id,
            spawn_child,
        )


def test_state_transition_expander_output_is_traced_and_schema_valid() -> None:
    """規範行からの派生ケースが宣言済みの読み取りとschemaを満たす。"""
    cases, trace = state_transition_expander.expand_traced(REPOSITORY_ROOT, limit=1)
    policy = _policy()
    rule = policy.expanders["state-transition-cases"]
    assert len(cases) == 1
    assert trace.observed_read_paths == rule.allowed_read_paths
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert contract["cases"][0] == cases[0]
    schema_checker._validate_instance(contract, schema, schema, "$")


@pytest.mark.parametrize("disallowed", [DISALLOWED_PATH, MANUAL_FIXTURE_PATH])
def test_state_transition_expander_rejects_unlisted_reads(
    monkeypatch: pytest.MonkeyPatch, disallowed: Path
) -> None:
    """実際の展開呼出区間で宣言外資産と手作業fixtureを拒否する。"""
    original_read = state_transition_expander._read_document

    def read_with_disallowed(root: Path, relative: PurePosixPath) -> dict[str, Any]:
        """展開中の読み取りへ未宣言資産を混入する。"""
        disallowed.read_text(encoding="utf-8")
        return original_read(root, relative)

    monkeypatch.setattr(state_transition_expander, "_read_document", read_with_disallowed)
    with pytest.raises(checker.ExpanderDependencyError, match="allowlist外"):
        state_transition_expander.expand_traced(REPOSITORY_ROOT, limit=1)


def test_game_end_expander_output_is_traced_and_schema_valid() -> None:
    """通常終了と延長継続の派生ケースが宣言済み入力とschemaを満たす。"""
    cases, trace = game_end_expander.expand_traced(REPOSITORY_ROOT, limit=2)
    rule = _policy().expanders["game-end-cases"]
    assert len(cases) == 2
    assert trace.observed_read_paths == rule.allowed_read_paths
    contract = json.loads(GAME_END_CONTRACT_PATH.read_text(encoding="utf-8"))
    schema = json.loads(GAME_END_SCHEMA_PATH.read_text(encoding="utf-8"))
    assert contract["cases"] == cases
    assert contract["validationErrors"] == []
    assert [case["branchId"] for case in cases] == [
        "GAME-END-NORMAL",
        "GAME-END-EXTRA-CONTINUE",
    ]
    for case, row in zip(cases, contract["decisionRows"][:2], strict=True):
        assert case["branchId"] == row["branchId"]
        assert case["rowRef"]["coordinate"]["branchId"] == row["branchId"]
        assert game_end_expander._predicate_holds(row["precondition"], case["inputCoordinate"])
        assert case["decision"] == row["decision"]
    schema_checker._validate_instance(contract, schema, schema, "$")


def test_game_end_expander_can_process_all_current_decision_rows() -> None:
    """メモリ上では現行5行すべてを行自身の分岐IDから展開できる。"""
    cases, trace = game_end_expander.expand_traced(REPOSITORY_ROOT, limit=5)
    contract = json.loads(GAME_END_CONTRACT_PATH.read_text(encoding="utf-8"))
    assert len(cases) == len(contract["decisionRows"])
    assert [case["branchId"] for case in cases] == [
        row["branchId"] for row in contract["decisionRows"]
    ]
    for case, row in zip(cases, contract["decisionRows"], strict=True):
        assert game_end_expander._predicate_holds(row["precondition"], case["inputCoordinate"])
        assert case["decision"] == row["decision"]
    assert trace.observed_read_paths == _policy().expanders["game-end-cases"].allowed_read_paths


def test_representative_policy_covers_eq_not_in_and_composites() -> None:
    """宣言順で最初の成立値を選び、述語の各形と逆順宣言に従う。"""
    policy = json.loads(
        (REPOSITORY_ROOT / "contracts/state-transition/representative_selection_policy_v1.json")
        .read_text(encoding="utf-8")
    )
    values = {"axis": ["a", "b", "c"]}
    eq = {"op": "eq", "axisId": "axis", "value": "c"}
    included = {"op": "in", "axisId": "axis", "values": ["c", "b"]}
    not_b = {"op": "not", "args": [{"op": "eq", "axisId": "axis", "value": "b"}]}
    combined = {"op": "and", "args": [included, not_b]}
    alternative = {"op": "or", "args": [eq, included]}
    assert representative_selection.select_coordinate(eq, values, ["axis"], policy) == {
        "axis": "c"
    }
    assert representative_selection.select_coordinate(included, values, ["axis"], policy) == {
        "axis": "b"
    }
    assert representative_selection.select_coordinate(not_b, values, ["axis"], policy) == {
        "axis": "a"
    }
    assert representative_selection.select_coordinate(combined, values, ["axis"], policy) == {
        "axis": "c"
    }
    assert representative_selection.select_coordinate(alternative, values, ["axis"], policy) == {
        "axis": "b"
    }
    reversed_policy = {**policy, "valueOrder": "reverse-descriptor-declaration-order"}
    assert representative_selection.select_coordinate(
        included, values, ["axis"], reversed_policy
    ) == {"axis": "c"}
    last_policy = {**policy, "candidateSelection": "last-satisfying-cartesian-product"}
    assert representative_selection.select_coordinate(
        included, values, ["axis"], last_policy
    ) == {"axis": "c"}
    numeric_values = {"count": [0, 1, 2]}
    assert representative_selection.select_coordinate(
        {"op": "gte", "axisId": "count", "value": 1},
        numeric_values, ["count"], policy,
    ) == {"count": 1}
    assert representative_selection.select_coordinate(
        {"op": "lte", "axisId": "count", "value": 1},
        numeric_values, ["count"], policy,
    ) == {"count": 0}


def test_game_end_expander_rejects_nonrepresentative_coordinate() -> None:
    """述語は満たしても規則と異なる展開座標を拒否する。"""
    contract = json.loads(GAME_END_CONTRACT_PATH.read_text(encoding="utf-8"))
    descriptor = json.loads(
        (REPOSITORY_ROOT / "contracts/state-transition/input_axes_descriptor_v1.json")
        .read_text(encoding="utf-8")
    )
    policy = json.loads(
        (REPOSITORY_ROOT / "contracts/state-transition/representative_selection_policy_v1.json")
        .read_text(encoding="utf-8")
    )
    values = representative_selection.axis_values(
        descriptor, ("gameEndAxes", "stateTransitionAxes")
    )
    used = set().union(
        *(representative_selection.predicate_axes(row["precondition"])
          for row in contract["decisionRows"])
    )
    axes = [axis_id for axis_id in values if axis_id in used]
    wrong = dict(contract["cases"][0]["inputCoordinate"])
    wrong["state.score"] = "home-lead:M"
    assert game_end_expander._predicate_holds(contract["decisionRows"][0]["precondition"], wrong)
    with pytest.raises(
        representative_selection.RepresentativeSelectionError,
        match="代表値規則に一致しない",
    ):
        representative_selection.validate_coordinate(
            contract["decisionRows"][0]["precondition"], wrong, values, axes, policy
        )


def test_game_end_expander_uses_declared_selection_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """資産側の選択方式を変えると展開器の代表値も変わる。"""
    original_read = game_end_expander._read_document

    def read_with_last_choice(root: Path, relative: PurePosixPath) -> dict[str, Any]:
        """監査下の読み取りを維持しつつ選択方式だけを変異させる。"""
        document = original_read(root, relative)
        if "predicateEvaluation" in document:
            document["candidateSelection"] = "last-satisfying-cartesian-product"
        return document

    monkeypatch.setattr(game_end_expander, "_read_document", read_with_last_choice)
    cases, trace = game_end_expander.expand_traced(REPOSITORY_ROOT, limit=1)
    assert cases[0]["inputCoordinate"]["state.score"] == "home-lead:M+1"
    assert trace.observed_read_paths == _policy().expanders["game-end-cases"].allowed_read_paths


def test_positive_manual_fixture_inputs_follow_representative_policy() -> None:
    """通常行と終了判定のfixture入力だけを代表値規則と照合する。"""
    policy = json.loads(
        (REPOSITORY_ROOT / "contracts/state-transition/representative_selection_policy_v1.json")
        .read_text(encoding="utf-8")
    )
    descriptor = json.loads(
        (REPOSITORY_ROOT / "contracts/state-transition/input_axes_descriptor_v1.json")
        .read_text(encoding="utf-8")
    )
    mappings = json.loads(BRANCH_ROW_MAPPING_PATH.read_text(encoding="utf-8"))["mappings"]
    state_fixtures = {
        item["case"]["branchId"]: item["case"]["inputCoordinate"]
        for item in json.loads(MANUAL_FIXTURE_PATH.read_text(encoding="utf-8"))["fixtures"]
    }
    game_fixtures = {
        item["case"]["branchId"]: item["case"]["inputCoordinate"]
        for item in json.loads(GAME_END_MANUAL_FIXTURE_PATH.read_text(encoding="utf-8"))["fixtures"]
    }
    state_values = representative_selection.axis_values(descriptor, ("stateTransitionAxes",))
    game_values = representative_selection.axis_values(
        descriptor, ("gameEndAxes", "stateTransitionAxes")
    )
    game_contract = json.loads(GAME_END_CONTRACT_PATH.read_text(encoding="utf-8"))
    game_used = set().union(
        *(representative_selection.predicate_axes(row["precondition"])
          for row in game_contract["decisionRows"])
    )
    game_axes = [axis_id for axis_id in game_values if axis_id in game_used]
    checked = 0
    for mapping in mappings:
        branch_id = mapping["branchId"]
        reference = mapping["rowRef"]["coordinate"]
        if mapping["fixtureRelation"] == "row-output":
            predicate = reference["precondition"]
            used = representative_selection.predicate_axes(predicate)
            axes = [axis_id for axis_id in state_values if axis_id in used]
            selected = representative_selection.select_coordinate(
                predicate, state_values, axes, policy
            )
            expected = {
                "eventKind": reference["eventKind"], "resultId": reference["resultId"],
                **selected,
            }
            assert state_fixtures[branch_id] == expected
            checked += 1
        elif mapping["fixtureRelation"] == "decision-output":
            row = next(
                row for row in game_contract["decisionRows"] if row["branchId"] == branch_id
            )
            expected = representative_selection.select_coordinate(
                row["precondition"], game_values, game_axes, policy
            )
            assert game_fixtures[branch_id] == expected
            checked += 1
    assert checked == 20


@pytest.mark.parametrize(
    "disallowed",
    [DISALLOWED_PATH, GAME_END_MANUAL_FIXTURE_PATH, BRANCH_ROW_MAPPING_PATH],
)
def test_game_end_expander_rejects_unlisted_reads(
    monkeypatch: pytest.MonkeyPatch, disallowed: Path
) -> None:
    """宣言外ファイル・手作業fixture・対応表の読み取りを拒否する。"""
    original_read = game_end_expander._read_document

    def read_with_disallowed(root: Path, relative: PurePosixPath) -> dict[str, Any]:
        """終了判定の展開中に未宣言の読み取りを混入する。"""
        disallowed.read_text(encoding="utf-8")
        return original_read(root, relative)

    monkeypatch.setattr(game_end_expander, "_read_document", read_with_disallowed)
    with pytest.raises(checker.ExpanderDependencyError, match="allowlist外"):
        game_end_expander.expand_traced(REPOSITORY_ROOT, limit=1)
