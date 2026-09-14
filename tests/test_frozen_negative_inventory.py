"""両 pytest root の凍結基準負例を exact-set で固定する。"""

from __future__ import annotations

import ast
import shutil
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FROZEN_NEGATIVE_TESTS = frozenset(
    {
        (
            "backend/tests/test_authz_mutation_composition_full.py",
            "test_frozen_oracle_rejects_meaning_tampering_after_reseal",
        ),
        (
            "backend/tests/test_authz_mutation_composition_full.py",
            "test_frozen_oracle_rejects_input_change_without_baseline_advance",
        ),
        (
            "tests/test_check_frozen_baselines.py",
            "test_n3_empty_approved_by_is_red",
        ),
        (
            "tests/test_check_authz_catalog.py",
            "test_n4_unreachable_oracle_commit_is_red",
        ),
        (
            "tests/test_check_frozen_baselines.py",
            "test_n5_changed_existing_approval_is_red",
        ),
        (
            "tests/test_check_frozen_baselines.py",
            "test_n6_unlinked_supersedes_is_red",
        ),
        (
            "tests/test_check_frozen_baselines.py",
            "test_n7_changed_corpus_without_version_advance_is_red",
        ),
        (
            "tests/test_check_frozen_baselines.py",
            "test_n8_derived_assets_must_follow_corpus_version",
        ),
        (
            "tests/test_check_frozen_baselines.py",
            "test_n9_initial_commit_mismatch_is_red",
        ),
        (
            "tests/test_check_frozen_baselines.py",
            "test_n10_changed_base_source_constant_is_red",
        ),
        (
            "tests/test_check_frozen_baselines.py",
            "test_n11_unlisted_source_pair_is_red",
        ),
        (
            "tests/test_check_frozen_baselines.py",
            "test_n12_stale_allowlist_pair_is_red",
        ),
        (
            "tests/test_check_frozen_baselines.py",
            "test_n13_pending_removal_after_ledger_introduction_is_red",
        ),
        (
            "tests/test_ci_wiring.py",
            "test_n14_missing_fetch_depth_is_red",
        ),
    }
)
TEST_ROOTS = (Path("backend/tests"), Path("tests"))


def _is_frozen_negative_marker(decorator: ast.expr) -> bool:
    """decorator が pytest.mark.frozen_negative なら真を返す。"""
    return (
        isinstance(decorator, ast.Attribute)
        and decorator.attr == "frozen_negative"
        and isinstance(decorator.value, ast.Attribute)
        and decorator.value.attr == "mark"
        and isinstance(decorator.value.value, ast.Name)
        and decorator.value.value.id == "pytest"
    )


def _collect_frozen_negative_tests(root: Path) -> frozenset[tuple[str, str]]:
    """marker の付いた負例を両 pytest root のソースから収集する。"""
    marked: set[tuple[str, str]] = set()
    for test_root in TEST_ROOTS:
        for path in sorted((root / test_root).rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if any(_is_frozen_negative_marker(item) for item in node.decorator_list):
                    marked.add((path.relative_to(root).as_posix(), node.name))
    return frozenset(marked)


def _assert_frozen_negative_tests_are_exact_set(root: Path) -> None:
    """凍結基準負例がパスと名前の期待集合に完全一致することを検査する。"""
    marked = _collect_frozen_negative_tests(root)
    assert marked == FROZEN_NEGATIVE_TESTS, (
        f"凍結基準負例の集合が不一致: "
        f"missing={sorted(FROZEN_NEGATIVE_TESTS - marked)!r}, "
        f"unexpected={sorted(marked - FROZEN_NEGATIVE_TESTS)!r}"
    )


def test_frozen_negative_tests_across_both_roots_are_exact_set() -> None:
    """N1〜N14 を名前の接頭辞に頼らず marker で数える。"""
    _assert_frozen_negative_tests_are_exact_set(REPOSITORY_ROOT)


def test_frozen_negative_exact_set_rejects_one_removed_marker(
    tmp_path: Path,
) -> None:
    """負例 marker を1件消す変異が exact-set を red にする。"""
    root = tmp_path / "repository"
    for relative_path in {Path(path) for path, _ in FROZEN_NEGATIVE_TESTS}:
        destination = root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPOSITORY_ROOT / relative_path, destination)

    target_relative_path = Path("tests/test_ci_wiring.py")
    target = root / target_relative_path
    text = target.read_text(encoding="utf-8")
    marker_and_test = (
        "@pytest.mark.frozen_negative\n"
        "def test_n14_missing_fetch_depth_is_red"
    )
    count = text.count(marker_and_test)
    replaced = text.replace(
        marker_and_test,
        "def test_n14_missing_fetch_depth_is_red",
        1,
    )
    assert count == 1
    target.write_text(replaced, encoding="utf-8")

    with pytest.raises(AssertionError, match="test_n14_missing_fetch_depth_is_red"):
        _assert_frozen_negative_tests_are_exact_set(root)
