"""ステップ20の資産導出と負例をDBなしで検証する。"""

from __future__ import annotations

from dataclasses import replace
from itertools import combinations
from types import MappingProxyType

import pytest
from db.authz.mutation import load_mutation_catalog
from db.authz.mutation_composition import (
    ATTACK_TREE_PATH,
    CLAIM_MUTANT_MAP_PATH,
    MCDC_MAP_PATH,
    MutationCompositionError,
    execute_mcdc_pair,
    load_step20_catalog,
    load_step20_catalog_data,
)
from db.authz.mutation_execution import _read_json_object


def _raw_assets() -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    """負例で変更する三つの資産コピーを返す。"""
    return (
        _read_json_object(CLAIM_MUTANT_MAP_PATH),
        _read_json_object(ATTACK_TREE_PATH),
        _read_json_object(MCDC_MAP_PATH),
    )


def test_two_factor_population_is_derived_from_configuration_axis() -> None:
    """非順序対がconfiguration軸の直積上三角とexact-set一致する。"""
    catalog = load_step20_catalog()
    configuration_ids = sorted(
        spec.mutant_id
        for spec in catalog.mutation_catalog.mutants
        if spec.axis == "configuration"
    )
    derived = frozenset(combinations(configuration_ids, 2))

    assert frozenset(row.factor_mutant_ids for row in catalog.interactions) == derived
    assert all(
        all(
            catalog.mutation_catalog.mutant_by_id[mutant_id].axis == "configuration"
            for mutant_id in row.factor_mutant_ids
        )
        for row in catalog.interactions
    )


def test_missing_two_factor_interaction_is_rejected() -> None:
    """資産から相互作用を1件落とすと導出母集合との照合がredになる。"""
    claim_map, attack_tree, mcdc_map = _raw_assets()
    interactions = claim_map["two_factor_interactions"]
    assert isinstance(interactions, list) and interactions
    interactions.pop()

    with pytest.raises(MutationCompositionError, match="exact-set不一致"):
        load_step20_catalog_data(
            claim_map,
            attack_tree,
            mcdc_map,
            load_mutation_catalog(),
        )


@pytest.mark.parametrize("single_mutation_sufficient", [True, False])
def test_cut_set_rejects_one_element_removal(
    single_mutation_sufficient: bool,
) -> None:
    """単独・複数要素cut setのいずれも1要素欠落を拒否する。"""
    claim_map, attack_tree, mcdc_map = _raw_assets()
    cut_sets = attack_tree["minimal_cut_sets"]
    assert isinstance(cut_sets, list)
    cut_set = next(
        row
        for row in cut_sets
        if isinstance(row, dict)
        and row.get("single_mutation_sufficient") is single_mutation_sufficient
    )
    mutant_ids = cut_set["mutant_ids"]
    assert isinstance(mutant_ids, list) and mutant_ids
    mutant_ids.pop()

    with pytest.raises(MutationCompositionError):
        load_step20_catalog_data(
            claim_map,
            attack_tree,
            mcdc_map,
            load_mutation_catalog(),
        )


def test_added_configuration_mutant_expands_pair_population_and_is_rejected() -> None:
    """configuration変異を増やすと未更新の相互作用資産をredにする。"""
    claim_map, attack_tree, mcdc_map = _raw_assets()
    mutation_catalog = load_mutation_catalog()
    source = next(
        spec for spec in mutation_catalog.mutants if spec.axis == "configuration"
    )
    added = replace(source, mutant_id=f"{source.mutant_id}:ADDED")
    mutants = (*mutation_catalog.mutants, added)
    expanded_catalog = replace(
        mutation_catalog,
        mutants=mutants,
        mutant_by_id=MappingProxyType({spec.mutant_id: spec for spec in mutants}),
    )

    with pytest.raises(MutationCompositionError, match="exact-set不一致"):
        load_step20_catalog_data(
            claim_map,
            attack_tree,
            mcdc_map,
            expanded_catalog,
        )


def test_mcdc_pair_without_result_reversal_is_rejected_at_execution() -> None:
    """対象条件を反転しても実判定が反転しない入力対をredにする。"""
    catalog = load_step20_catalog()
    source = next(pair for pair in catalog.mcdc_pairs if pair.decision_form == "AND")
    target_index = source.condition_ids.index(source.condition_id)
    input_a = [False] * len(source.condition_ids)
    input_b = [False] * len(source.condition_ids)
    input_b[target_index] = True
    non_reversing = replace(
        source,
        input_a=tuple(input_a),
        input_b=tuple(input_b),
        observed_results=(False, False),
    )

    with pytest.raises(MutationCompositionError, match="判定結果が反転しない"):
        execute_mcdc_pair(non_reversing)


def test_mcdc_execution_population_matches_all_mapped_conditions() -> None:
    """判定ごとのconditionと実行対象pairがexact-set一致する。"""
    catalog = load_step20_catalog()
    actual = {(pair.decision_id, pair.condition_id) for pair in catalog.mcdc_pairs}

    assert len(actual) == len(catalog.mcdc_pairs)
    assert {decision_id for decision_id, _condition_id in actual} == set(
        catalog.mcdc_decision_ids
    )
