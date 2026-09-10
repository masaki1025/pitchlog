"""ステップ20の全資産をDBなしで実行する。"""

from __future__ import annotations

import os

from db.authz.mutation_composition import (
    load_step20_catalog,
    run_step20,
    select_step20_work,
    step20_selection_from_environment,
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
    """seal由来の凍結パスがorigin/developから変更されていない。"""
    verify_frozen_oracle_unchanged()
