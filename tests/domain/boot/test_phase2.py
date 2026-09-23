"""段階 2 判定が対象単位の意味差分に従うことを検査する。"""

from __future__ import annotations

import ast
import copy
import importlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
BACKEND_SRC = ROOT / "backend/src"
PHASE2_SOURCE = BACKEND_SRC / "pitchlog/domaincheck/boot/phase2.py"
BOOT_SEAL_PATH = ROOT / "backend/domain/boot-seal.json"
CHECK_SETS_PATH = ROOT / "backend/domain/check-sets.json"

sys.path.insert(0, str(BACKEND_SRC))
PHASE2 = importlib.import_module("pitchlog.domaincheck.boot.phase2")
STALL = importlib.import_module("pitchlog.domaincheck.boot.stall")


@pytest.fixture(scope="module")
def universe() -> Any:
    """実資産から導出した対象母集合を返す。"""
    return PHASE2.load_target_universe(ROOT)


def _write_json(path: Path, value: object) -> None:
    """合成資産を読みやすい JSON で書く。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _snapshot(
    *,
    declarations: set[str] | frozenset[str] = frozenset(),
    generated: set[str] | frozenset[str] = frozenset(),
    product_calls: set[str] | frozenset[str] = frozenset(),
    vector_checks: set[str] | frozenset[str] = frozenset(),
    property_checks: set[str] | frozenset[str] = frozenset(),
    mutation_checks: set[str] | frozenset[str] = frozenset(),
) -> Any:
    """指定した意味要素を持つ判定可能な実測を返す。"""
    return PHASE2.SemanticSnapshot(
        declarations=frozenset(declarations),
        generated=frozenset(generated),
        product_calls=frozenset(product_calls),
        vector_checks=frozenset(vector_checks),
        property_checks=frozenset(property_checks),
        mutation_checks=frozenset(mutation_checks),
    )


def _complete_snapshot(target_ids: set[str] | frozenset[str]) -> Any:
    """4 点と 3 層が揃った実測を返す。"""
    return _snapshot(
        declarations=target_ids,
        generated=target_ids,
        product_calls=target_ids,
        vector_checks=target_ids,
        property_checks=target_ids,
        mutation_checks=target_ids,
    )


def _active_state(universe: Any) -> Any:
    """ステップ 17 の型で発効済み状態を返す。"""
    state = STALL.defined_state(len(universe.identifiers))
    return STALL.activate(state, "synthetic-activation")


def _target_ids(universe: Any, count: int) -> tuple[str, ...]:
    """資産の並びから指定数の安定 ID を返す。"""
    values = tuple(target.identifier for target in universe.targets[:count])
    assert len(values) == count
    return values


def test_target_universe_is_read_from_existing_assets(
    tmp_path: Path,
    universe: Any,
) -> None:
    boot_seal = json.loads(BOOT_SEAL_PATH.read_text(encoding="utf-8"))
    check_sets = json.loads(CHECK_SETS_PATH.read_text(encoding="utf-8"))
    copied = copy.deepcopy(boot_seal)
    original = copied["derivedInputs"]["targets"][0]
    original_id = original["id"]
    original_name = original["name"]
    original["id"] = "synthetic-stable-target"
    original["name"] = "合成対象名"
    _write_json(tmp_path / "backend/domain/boot-seal.json", copied)
    _write_json(tmp_path / "backend/domain/check-sets.json", check_sets)

    changed = PHASE2.load_target_universe(tmp_path)

    assert original_id in universe.identifiers
    assert original_id not in changed.identifiers
    assert "synthetic-stable-target" in changed.identifiers
    assert original_name != changed.targets[0].name
    source_constants = {
        node.value
        for node in ast.walk(ast.parse(PHASE2_SOURCE.read_text(encoding="utf-8")))
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert source_constants.isdisjoint(universe.identifiers)
    assert source_constants.isdisjoint(
        {target.name for target in universe.targets}
    )


def test_changed_paths_are_not_phase2_inputs() -> None:
    tree = ast.parse(PHASE2_SOURCE.read_text(encoding="utf-8"))
    imports = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import | ast.ImportFrom)
        for alias in node.names
    }
    identifiers = {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name)
    } | {
        node.arg
        for node in ast.walk(tree)
        if isinstance(node, ast.arg)
    } | {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    forbidden_identifiers = {
        "changed_paths",
        "diff_files",
        "file_changes",
        "paths",
        "touched_paths",
    }
    git_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_run_git"
    ]
    snapshots = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "SemanticSnapshot"
    )
    snapshot_fields = {
        node.target.id
        for node in snapshots.body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
    }

    assert imports.isdisjoint({"subprocess"})
    assert identifiers.isdisjoint(forbidden_identifiers)
    assert git_calls == []
    assert snapshot_fields == {
        "declarations",
        "generated",
        "product_calls",
        "vector_checks",
        "property_checks",
        "mutation_checks",
    }


def test_two_complete_targets_are_rejected(universe: Any) -> None:
    first, second = _target_ids(universe, 2)

    with pytest.raises(PHASE2.CheckerViolation, match="1 件ごと"):
        PHASE2.classify_phase2(
            _active_state(universe),
            universe,
            PHASE2.SemanticSnapshot.empty(),
            _complete_snapshot({first, second}),
        )


def test_declaration_only_change_is_not_rejected_or_resolved(
    universe: Any,
) -> None:
    (target_id,) = _target_ids(universe, 1)

    decision = PHASE2.classify_phase2(
        _active_state(universe),
        universe,
        PHASE2.SemanticSnapshot.empty(),
        _snapshot(declarations={target_id}),
    )

    assert decision.status == PHASE2.Phase2Status.NOT_PHASE2
    assert decision.declaration_only_target_ids == frozenset({target_id})
    assert decision.resolution_target_ids == frozenset()


def test_declaration_for_unclassified_target_is_rejected(universe: Any) -> None:
    with pytest.raises(PHASE2.CheckerViolation, match="対象欄にない宣言"):
        PHASE2.classify_phase2(
            _active_state(universe),
            universe,
            PHASE2.SemanticSnapshot.empty(),
            _snapshot(declarations={"synthetic-unclassified-target"}),
        )


def test_missing_baseline_before_activation_is_treated_as_empty(
    universe: Any,
) -> None:
    (target_id,) = _target_ids(universe, 1)
    state = STALL.defined_state(len(universe.identifiers))

    decision = PHASE2.classify_phase2(
        state,
        universe,
        PHASE2.SemanticSnapshot.missing(),
        _snapshot(declarations={target_id}),
    )

    assert decision.status == PHASE2.Phase2Status.NOT_PHASE2
    assert decision.baseline_absence_treated_as_empty is True
    assert decision.indeterminate_components == ()


def test_missing_baseline_after_activation_is_indeterminate_phase2(
    universe: Any,
) -> None:
    decision = PHASE2.classify_phase2(
        _active_state(universe),
        universe,
        PHASE2.SemanticSnapshot.missing(),
        PHASE2.SemanticSnapshot.empty(),
    )

    assert decision.status == PHASE2.Phase2Status.INDETERMINATE_PHASE2
    assert decision.is_phase2 is True
    assert decision.phase2_target_ids == universe.identifiers
    assert decision.baseline_absence_treated_as_empty is False


def test_all_four_points_must_be_added_by_same_pr(universe: Any) -> None:
    (target_id,) = _target_ids(universe, 1)
    before = _snapshot(generated={target_id})
    after = _complete_snapshot({target_id})

    decision = PHASE2.classify_phase2(
        _active_state(universe),
        universe,
        before,
        after,
    )

    assert decision.status == PHASE2.Phase2Status.NOT_PHASE2
    assert decision.resolution_target_ids == frozenset()
    assert decision.partial_target_ids == frozenset({target_id})


def test_exclusion_is_applied_only_to_the_complete_target(universe: Any) -> None:
    complete, declaration_only = _target_ids(universe, 2)
    after = _complete_snapshot({complete})
    after = PHASE2.SemanticSnapshot(
        declarations=after.declarations | {declaration_only},
        generated=after.generated,
        product_calls=after.product_calls,
        vector_checks=after.vector_checks,
        property_checks=after.property_checks,
        mutation_checks=after.mutation_checks,
    )

    decision = PHASE2.classify_phase2(
        _active_state(universe),
        universe,
        PHASE2.SemanticSnapshot.empty(),
        after,
    )

    assert decision.phase2_target_ids == frozenset({complete})
    assert decision.resolution_target_ids == frozenset({complete})
    assert decision.declaration_only_target_ids == frozenset({declaration_only})


def test_one_complete_target_is_classified_as_phase2(universe: Any) -> None:
    (target_id,) = _target_ids(universe, 1)

    decision = PHASE2.evaluate_phase2(
        ROOT,
        _active_state(universe),
        PHASE2.SemanticSnapshot.empty(),
        _complete_snapshot({target_id}),
    )

    assert decision.status == PHASE2.Phase2Status.PHASE2
    assert decision.is_phase2 is True
    assert decision.phase2_target_ids == frozenset({target_id})
    assert decision.resolution_target_ids == frozenset({target_id})
    assert PHASE2.StallState is STALL.StallState
