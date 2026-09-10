"""全量 mutation executor の資産駆動境界を DB なしで検証する。"""

from __future__ import annotations

import json
from dataclasses import fields, replace

import pytest
from db.authz.mutation import MutationContractError, load_mutation_catalog
from db.authz.mutation_execution import (
    MutationBatchError,
    MutationExecutionRecord,
    _observe_assertion,
    bind_operator_implementations,
    mutation_batches,
    mutation_blueprint,
    observe_schema_drift,
    select_mutation_batches,
)


def test_asset_operator_set_is_bound_to_exact_implementation_set() -> None:
    """資産の全 operator に過不足ない実装がある。"""
    catalog = load_mutation_catalog()
    implementations = bind_operator_implementations(catalog)

    assert frozenset(implementations) == frozenset(
        spec.operator_id for spec in catalog.mutants
    )


def test_unknown_asset_operator_is_rejected_by_exact_binding() -> None:
    """資産へ未実装 operator が増えたら黙って無視しない。"""
    catalog = load_mutation_catalog()
    first = catalog.mutants[0]
    mutated = replace(first, operator_id="UNIMPLEMENTED_OPERATOR")
    mutated_catalog = replace(
        catalog,
        mutants=(mutated, *catalog.mutants[1:]),
    )

    with pytest.raises(MutationContractError, match="未実装"):
        bind_operator_implementations(mutated_catalog)


def test_every_blueprint_uses_all_asset_declared_targets() -> None:
    """各 operator の対象を claim_ids と target_element_ids だけから導出する。"""
    catalog = load_mutation_catalog()
    implementations = bind_operator_implementations(catalog)

    for spec in catalog.mutants:
        blueprint = mutation_blueprint(spec, implementations)
        assert blueprint.mutant_id == spec.mutant_id
        assert blueprint.operator_id == spec.operator_id
        assert blueprint.changed_element_ids == spec.target_element_ids


def test_all_schema_drift_mutations_are_rejected_by_independent_checker() -> None:
    """資産由来の全 mutation が静的 drift チャネル単独で red になる。"""
    catalog = load_mutation_catalog()
    implementations = bind_operator_implementations(catalog)

    observations = {
        spec.mutant_id: observe_schema_drift(
            spec, mutation_blueprint(spec, implementations)
        )
        for spec in catalog.mutants
    }

    assert frozenset(observations) == frozenset(catalog.mutant_by_id)
    assert all(
        observation.status == "failed"
        and observation.phase == "call"
        and observation.failure_kind == "assertion"
        for observation in observations.values()
    )


def test_batches_are_complete_and_sorted_by_derived_population() -> None:
    """少数 axis・少数 operator 順の刻みが全 mutation と exact-set 一致する。"""
    catalog = load_mutation_catalog()
    batches = mutation_batches(catalog)
    selected_ids = tuple(
        mutant_id for batch in batches for mutant_id in batch.mutant_ids
    )
    axis_counts = {
        axis: sum(spec.axis == axis for spec in catalog.mutants)
        for axis in catalog.mutant_axes
    }

    assert len(selected_ids) == len(set(selected_ids))
    assert frozenset(selected_ids) == frozenset(catalog.mutant_by_id)
    assert [axis_counts[batch.axis] for batch in batches] == sorted(
        axis_counts[batch.axis] for batch in batches
    )
    for axis in catalog.mutant_axes:
        operator_sizes = [
            len(batch.mutant_ids) for batch in batches if batch.axis == axis
        ]
        assert operator_sizes == sorted(operator_sizes)


def test_axis_and_operator_filters_use_closed_asset_vocabularies() -> None:
    """実機用フィルタは資産にある axis・operator だけを選ぶ。"""
    catalog = load_mutation_catalog()
    first = mutation_batches(catalog)[0]

    selected = select_mutation_batches(
        catalog,
        axis=first.axis,
        operator_id=first.operator_id,
    )

    assert selected
    assert all(batch.axis == first.axis for batch in selected)
    assert all(batch.operator_id == first.operator_id for batch in selected)
    with pytest.raises(MutationContractError, match="未知のmutation axis"):
        select_mutation_batches(catalog, axis="unknown", operator_id=None)
    with pytest.raises(MutationContractError, match="未知のmutation operator"):
        select_mutation_batches(catalog, axis=None, operator_id="unknown")


def test_handoff_runtime_has_no_database_mutation_execution_mode() -> None:
    """Contract-only runtime は DB 実行へ誤配線せず handoff のままにする。"""
    catalog = load_mutation_catalog()
    implementations = bind_operator_implementations(catalog)
    handoff_specs = tuple(
        spec for spec in catalog.mutants if spec.expected_runtime_outcome == "handoff"
    )
    executable_specs = tuple(
        spec for spec in catalog.mutants if spec.expected_runtime_outcome != "handoff"
    )

    assert handoff_specs
    assert executable_specs
    assert all(
        mutation_blueprint(spec, implementations).database_mode
        == "no_database_mutation"
        for spec in handoff_specs
    )
    assert all(
        mutation_blueprint(spec, implementations).database_mode
        != "no_database_mutation"
        for spec in executable_specs
    )


def test_survivor_output_is_machine_readable_and_has_no_equivalence_decision() -> None:
    """生存出力に人手判定用の項目を持ち、自動除外欄を持たない。"""
    record = MutationExecutionRecord(
        mutant_id="MUT:EXAMPLE",
        axis="configuration",
        operator_id="example_operator",
        failed_checks=("runtime_cross_tenant",),
        surviving_channels=("runtime_cross_tenant",),
        observation={"runtime_cross_tenant": {"status": "passed"}},
        execution_error=None,
    )

    error = MutationBatchError((record,))
    payload = json.loads(str(error).splitlines()[1])

    assert payload["mutant_id"] == record.mutant_id
    assert payload["axis"] == record.axis
    assert payload["operator_id"] == record.operator_id
    assert payload["surviving_channels"] == ["runtime_cross_tenant"]
    assert "equivalent" not in {field.name for field in fields(record)}


def test_pytest_raises_failure_is_observed_as_expected_assertion_failure() -> None:
    """pytest.raises の DID NOT RAISE を kill 信号として観測する。"""

    def did_not_raise() -> None:
        with pytest.raises(ValueError):
            pass

    observation = _observe_assertion(did_not_raise)

    assert observation.status == "failed"
    assert observation.phase == "call"
    assert observation.failure_kind == "assertion"
    assert observation.expected_failure_kind == "assertion"


def test_pytest_fail_is_observed_as_expected_assertion_failure() -> None:
    """pytest.fail.Exception も同じ kill 信号として観測する。"""

    def fail() -> None:
        pytest.fail("mutation probe failure")

    observation = _observe_assertion(fail)

    assert observation.status == "failed"
    assert observation.failure_kind == "assertion"


@pytest.mark.parametrize("error", [KeyboardInterrupt(), SystemExit()])
def test_process_control_base_exceptions_are_not_observed_as_kills(
    error: BaseException,
) -> None:
    """割り込みとプロセス終了を kill として飲み込まない。"""

    def raise_control_exception() -> None:
        raise error

    with pytest.raises(type(error)):
        _observe_assertion(raise_control_exception)


def test_unexpected_exception_is_not_observed_as_assertion_kill() -> None:
    """期待外の通常例外を KILL-03 の assertion kill に数えない。"""

    def raise_unexpected_exception() -> None:
        raise RuntimeError("unexpected mutation probe error")

    with pytest.raises(RuntimeError, match="unexpected mutation probe error"):
        _observe_assertion(raise_unexpected_exception)
