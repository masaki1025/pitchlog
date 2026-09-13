"""ステップ20の全資産をDBなしで実行する。"""

from __future__ import annotations

import os

import pytest
from db.authz import mutation_composition
from db.authz.mutation_composition import (
    ORACLE_SEAL_RELATIVE_PATH,
    STEP2_BASE_REVISION,
    STEP2_CHANGED_CANONICAL_ASSET_PATHS,
    MutationCompositionError,
    frozen_oracle_paths,
    intentionally_changed_frozen_oracle_paths,
    load_step20_catalog,
    run_step20,
    select_step20_work,
    step20_selection_from_environment,
    unchanged_frozen_oracle_paths,
    verify_frozen_oracle_unchanged,
)


def test_step20_asset_populations_execute_as_exact_sets() -> None:
    """選択した相互作用・cut set・MC/DC pairを全件実行する。"""
    catalog = load_step20_catalog()
    selection = step20_selection_from_environment(os.environ)
    interactions, cut_sets, mcdc_pairs = select_step20_work(catalog, selection)

    result = run_step20(catalog, selection)

    assert {row.interaction_id for row in result.interactions} == {
        row.interaction_id for row in interactions
    }
    assert {row.cut_set_id for row in result.cut_sets} == {
        row.cut_set_id for row in cut_sets
    }
    assert {(row.decision_id, row.condition_id) for row in result.mcdc_pairs} == {
        (row.decision_id, row.condition_id) for row in mcdc_pairs
    }


def test_frozen_oracle_paths_have_no_branch_diff() -> None:
    """固定基準から意図的変更を除いた凍結パスに差分がない。"""
    verify_frozen_oracle_unchanged()


def test_frozen_oracle_exclusions_match_the_resealed_canonical_assets() -> None:
    """canonical差分2本とseal自身だけが不変検査から除外される。"""
    frozen = frozen_oracle_paths(base_ref=STEP2_BASE_REVISION)
    excluded = intentionally_changed_frozen_oracle_paths()
    unchanged = unchanged_frozen_oracle_paths()

    assert excluded
    assert excluded == STEP2_CHANGED_CANONICAL_ASSET_PATHS | {ORACLE_SEAL_RELATIVE_PATH}
    assert set(unchanged) == set(frozen) - excluded
    assert len(unchanged) == len(frozen) - len(excluded)


def test_each_unchanged_frozen_oracle_path_rejects_a_branch_diff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """導出した不変パスを1件ずつ変更した負例がすべてredになる。"""
    frozen = frozen_oracle_paths(base_ref=STEP2_BASE_REVISION)
    expected_excluded = STEP2_CHANGED_CANONICAL_ASSET_PATHS | {
        ORACLE_SEAL_RELATIVE_PATH
    }
    unchanged = tuple(path for path in frozen if path not in expected_excluded)
    escaped: list[str] = []

    for changed_path in unchanged:
        monkeypatch.setattr(
            mutation_composition,
            "_branch_changed_paths",
            lambda _root, _base_ref, paths, path=changed_path: (
                (path,) if path in paths else ()
            ),
        )
        try:
            verify_frozen_oracle_unchanged()
        except MutationCompositionError:
            pass
        else:
            escaped.append(changed_path)

    assert escaped == []
