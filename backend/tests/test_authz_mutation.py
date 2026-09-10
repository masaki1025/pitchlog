"""資産駆動 mutation ランナーと kill 判定を DB なしで検証する。"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import replace

import pytest
from db.authz.mutation import (
    CLAIM_MUTANT_MAP_PATH,
    ApplicationObservation,
    CatalogDelta,
    ChannelObservation,
    ExecutionPhase,
    ExecutionStatus,
    FailureKind,
    IsolationReceipt,
    MutantSpec,
    MutationCatalog,
    MutationContractError,
    MutationEnvironment,
    MutationObservation,
    MutationPlan,
    MutationRunner,
    MutationVerdict,
    MutationVerdictError,
    NotRunReason,
    judge_mutation,
    load_mutation_catalog,
    load_mutation_catalog_data,
    mutation_plan,
)


def _raw_asset() -> dict[str, object]:
    """実資産を独立した可変 object として読む。"""
    raw = json.loads(CLAIM_MUTANT_MAP_PATH.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return raw


@pytest.fixture(scope="module")
def mutation_catalog() -> MutationCatalog:
    """実資産から構築した mutation 契約を返す。"""
    return load_mutation_catalog()


def _only_spec(
    catalog: MutationCatalog,
    predicate: Callable[[MutantSpec], bool],
) -> MutantSpec:
    """述語に一致する最初の mutation を資産から選ぶ。"""
    return next(spec for spec in catalog.mutants if predicate(spec))


def _application_observation(spec: MutantSpec) -> ApplicationObservation:
    """資産の適用期待値を満たす観測値を作る。"""
    if spec.expected_application_outcome == "applies":
        return ApplicationObservation.success()
    prefix = "fails_expected_sqlstate_"
    if spec.expected_application_outcome.startswith(prefix):
        return ApplicationObservation.expected_sqlstate_failure(
            spec.expected_application_outcome.removeprefix(prefix)
        )
    raise AssertionError(f"未対応の適用期待値: {spec.expected_application_outcome}")


def _channel_observation(expected_outcome: str) -> ChannelObservation:
    """資産の各期待結果を満たすチャネル観測値を作る。"""
    if expected_outcome in {"red", "kill"}:
        return ChannelObservation.expected_assertion_failure()
    if expected_outcome in {"pass", "survives_layered_defense"}:
        return ChannelObservation.passed()
    if expected_outcome == "availability_failure":
        return ChannelObservation.availability_failure()
    if expected_outcome == "handoff":
        return ChannelObservation.not_run(NotRunReason.HANDOFF)
    if expected_outcome == "not_run_application_failed":
        return ChannelObservation.not_run(NotRunReason.APPLICATION_FAILED)
    raise AssertionError(f"未対応のチャネル期待値: {expected_outcome}")


def _valid_observation(spec: MutantSpec) -> MutationObservation:
    """指定 mutation の全期待値を満たす合成観測を返す。"""
    return MutationObservation(
        application=_application_observation(spec),
        catalog_delta=CatalogDelta(changed_element_ids=spec.target_element_ids),
        schema_drift=_channel_observation(spec.expected_drift_outcome),
        runtime_cross_tenant=_channel_observation(spec.expected_runtime_outcome),
        runtime_positive_case=_channel_observation(spec.expected_positive_outcome),
    )


def _isolation_receipt(
    spec: MutantSpec,
    *,
    database_id: str = "database-1",
    cluster_is_fresh: bool | None = None,
) -> IsolationReceipt:
    """指定 mutation の計画を満たす隔離証跡を返す。"""
    fresh_cluster = (
        spec.requires_disposable_cluster
        if cluster_is_fresh is None
        else cluster_is_fresh
    )
    return IsolationReceipt(
        database_id=database_id,
        cluster_id="fresh-cluster" if fresh_cluster else "shared-cluster",
        database_is_fresh=True,
        cluster_is_fresh=fresh_cluster,
    )


def _judge(
    catalog: MutationCatalog,
    spec: MutantSpec,
    observation: MutationObservation,
    *,
    isolation: IsolationReceipt | None = None,
) -> MutationVerdict:
    """資産由来計画と指定観測を組み合わせて判定する。"""
    return judge_mutation(
        catalog,
        spec,
        observation,
        mutation_plan(spec),
        isolation or _isolation_receipt(spec),
    )


def _condition_id(catalog: MutationCatalog, requirement: str) -> str:
    """実装要件から資産由来 condition ID を一意に得る。"""
    matches = tuple(
        condition.condition_id
        for condition in catalog.kill_contract.conditions
        if condition.requirement == requirement
    )
    assert len(matches) == 1
    return matches[0]


class _FakeIsolationProvider:
    """DB を作らずランナーの隔離経路だけを記録する。"""

    def __init__(self, *, reuse_database_id: bool = False) -> None:
        """DB ID を再利用する負例を任意に有効化する。"""
        self.calls: list[str] = []
        self._counter = 0
        self._reuse_database_id = reuse_database_id

    def _environment(
        self,
        plan: MutationPlan,
        *,
        fresh_cluster: bool,
    ) -> MutationEnvironment:
        """呼出し回数から合成した一意な環境を返す。"""
        self._counter += 1
        serial = 1 if self._reuse_database_id else self._counter
        cluster_id = f"cluster-{self._counter}" if fresh_cluster else "shared-cluster"
        return MutationEnvironment(
            mutant_id=plan.mutant_id,
            database_dsn=f"postgresql:///mutation_{serial}",
            isolation=IsolationReceipt(
                database_id=f"database-{serial}",
                cluster_id=cluster_id,
                database_is_fresh=True,
                cluster_is_fresh=fresh_cluster,
            ),
        )

    @contextmanager
    def isolated_database(self, plan: MutationPlan) -> Iterator[MutationEnvironment]:
        """共有クラスタの新 DB 経路を記録する。"""
        self.calls.append("database")
        yield self._environment(plan, fresh_cluster=False)

    @contextmanager
    def isolated_cluster_database(
        self, plan: MutationPlan
    ) -> Iterator[MutationEnvironment]:
        """新クラスタかつ新 DB の経路を記録する。"""
        self.calls.append("cluster_database")
        yield self._environment(plan, fresh_cluster=True)


def _synthetic_executor(
    spec: MutantSpec,
    environment: MutationEnvironment,
) -> MutationObservation:
    """隔離経路試験用に資産期待値を満たす合成観測を返す。"""
    assert environment.mutant_id == spec.mutant_id
    return _valid_observation(spec)


def test_contract_is_derived_from_asset_rows(
    mutation_catalog: MutationCatalog,
) -> None:
    """条件・チャネル・期待値語彙を資産の全行から導出する。"""
    raw = _raw_asset()
    raw_contract = raw["kill_contract"]
    raw_mutants = raw["mutants"]
    assert isinstance(raw_contract, dict)
    assert isinstance(raw_mutants, list)
    raw_conditions = raw_contract["conditions"]
    raw_channels = raw_contract["verdict_channels"]
    assert isinstance(raw_conditions, list)
    assert isinstance(raw_channels, dict)

    assert tuple(
        (condition.condition_id, condition.requirement)
        for condition in mutation_catalog.kill_contract.conditions
    ) == tuple(
        (row["condition_id"], row["requirement"])
        for row in raw_conditions
        if isinstance(row, dict)
    )
    assert tuple(
        (channel.channel_id, channel.requirement)
        for channel in mutation_catalog.kill_contract.channels
    ) == tuple(raw_channels.items())
    assert mutation_catalog.outcome_vocabularies.application == frozenset(
        row["expected_application_outcome"]
        for row in raw_mutants
        if isinstance(row, dict)
    )
    assert mutation_catalog.outcome_vocabularies.schema_drift == frozenset(
        row["expected_drift_outcome"] for row in raw_mutants if isinstance(row, dict)
    )
    assert mutation_catalog.outcome_vocabularies.runtime_cross_tenant == frozenset(
        row["expected_runtime_outcome"] for row in raw_mutants if isinstance(row, dict)
    )
    assert mutation_catalog.outcome_vocabularies.runtime_positive_case == frozenset(
        row["expected_positive_outcome"] for row in raw_mutants if isinstance(row, dict)
    )


def test_unimplemented_sixth_condition_is_rejected() -> None:
    """資産へ未実装 condition が増えた場合は読み込み時点で拒否する。"""
    raw = copy.deepcopy(_raw_asset())
    contract = raw["kill_contract"]
    assert isinstance(contract, dict)
    conditions = contract["conditions"]
    assert isinstance(conditions, list)
    conditions.append(
        {
            "condition_id": "KILL-UNIMPLEMENTED",
            "requirement": "unimplemented_requirement",
        }
    )

    with pytest.raises(MutationContractError, match="未実装"):
        load_mutation_catalog_data(raw)


@pytest.mark.parametrize(
    "field",
    (
        "expected_application_outcome",
        "expected_drift_outcome",
        "expected_runtime_outcome",
        "expected_positive_outcome",
    ),
)
def test_unknown_expected_outcome_is_rejected(field: str) -> None:
    """期待値フィールドへ未知語彙を加えると読み込み時点で拒否する。"""
    raw = copy.deepcopy(_raw_asset())
    mutants = raw["mutants"]
    assert isinstance(mutants, list)
    first = mutants[0]
    assert isinstance(first, dict)
    first[field] = "unknown_outcome"

    with pytest.raises(MutationContractError, match="未実装"):
        load_mutation_catalog_data(raw)


def test_expected_application_sqlstate_failure_is_not_execution_error(
    mutation_catalog: MutationCatalog,
) -> None:
    """資産が期待する 42501 の適用失敗と後続未実行を合格させる。"""
    spec = _only_spec(
        mutation_catalog,
        lambda mutant: mutant.expected_application_outcome != "applies",
    )

    verdict = _judge(mutation_catalog, spec, _valid_observation(spec))

    assert verdict.accepted


def test_isolation_plans_use_new_database_and_asset_selected_cluster(
    mutation_catalog: MutationCatalog,
) -> None:
    """全変異を新 DB、資産フラグの対象だけを新クラスタへ割り当てる。"""
    plans = tuple(mutation_plan(spec) for spec in mutation_catalog.mutants)

    assert all(plan.fresh_database for plan in plans)
    assert {plan.mutant_id for plan in plans if plan.fresh_cluster} == {
        spec.mutant_id
        for spec in mutation_catalog.mutants
        if spec.requires_disposable_cluster
    }


def test_runner_routes_database_and_cluster_without_running_full_population(
    mutation_catalog: MutationCatalog,
) -> None:
    """選択した各 1 変異を資産フラグに対応する隔離経路へ送る。"""
    shared_spec = _only_spec(
        mutation_catalog,
        lambda mutant: not mutant.requires_disposable_cluster,
    )
    disposable_spec = _only_spec(
        mutation_catalog,
        lambda mutant: mutant.requires_disposable_cluster,
    )
    provider = _FakeIsolationProvider()
    runner = MutationRunner(mutation_catalog, provider)

    assert runner.run_one(shared_spec.mutant_id, _synthetic_executor).accepted
    assert runner.run_one(disposable_spec.mutant_id, _synthetic_executor).accepted
    assert provider.calls == ["database", "cluster_database"]


def test_runner_rejects_reused_database_between_mutants(
    mutation_catalog: MutationCatalog,
) -> None:
    """異なる変異へ同じ DB を再利用する隔離プロバイダを拒否する。"""
    shared_specs = tuple(
        spec
        for spec in mutation_catalog.mutants
        if not spec.requires_disposable_cluster
    )
    first, second, *_rest = shared_specs
    runner = MutationRunner(
        mutation_catalog,
        _FakeIsolationProvider(reuse_database_id=True),
    )
    runner.run_one(first.mutant_id, _synthetic_executor)

    with pytest.raises(MutationVerdictError, match="新しいDB"):
        runner.run_one(second.mutant_id, _synthetic_executor)


def test_negative_undeclared_catalog_delta_is_not_counted(
    mutation_catalog: MutationCatalog,
) -> None:
    """KILL-01: 宣言外の属性も変えた変異を kill と数えない。"""
    spec = mutation_catalog.mutants[0]
    observation = _valid_observation(spec)
    observation = replace(
        observation,
        catalog_delta=CatalogDelta(
            changed_element_ids=spec.target_element_ids | {"UNDECLARED:ATTRIBUTE"}
        ),
    )

    verdict = _judge(mutation_catalog, spec, observation)

    assert not verdict.accepted
    assert (
        _condition_id(
            mutation_catalog,
            "only_declared_target_attributes_changed",
        )
        in verdict.failure_ids
    )


@pytest.mark.parametrize(
    "phase",
    (ExecutionPhase.SETUP, ExecutionPhase.TEARDOWN),
)
def test_negative_fixture_failure_is_not_counted(
    mutation_catalog: MutationCatalog,
    phase: ExecutionPhase,
) -> None:
    """KILL-04: setup・teardown の失敗を kill と数えない。"""
    spec = mutation_catalog.mutants[0]
    observation = _valid_observation(spec)
    observation = replace(
        observation,
        schema_drift=replace(observation.schema_drift, phase=phase),
    )

    verdict = _judge(mutation_catalog, spec, observation)

    assert not verdict.accepted
    assert (
        _condition_id(
            mutation_catalog,
            "setup_and_teardown_failure_never_counts",
        )
        in verdict.failure_ids
    )


def test_negative_global_state_mutant_on_shared_cluster_is_red(
    mutation_catalog: MutationCatalog,
) -> None:
    """KILL-05: 資産が指定した変異を共有クラスタで走らせると拒否する。"""
    spec = _only_spec(
        mutation_catalog,
        lambda mutant: (
            mutant.requires_disposable_cluster and mutant.axis == "configuration"
        ),
    )
    shared_cluster = _isolation_receipt(spec, cluster_is_fresh=False)

    verdict = _judge(
        mutation_catalog,
        spec,
        _valid_observation(spec),
        isolation=shared_cluster,
    )

    assert not verdict.accepted
    assert (
        _condition_id(
            mutation_catalog,
            "role_attribute_membership_default_acl_use_disposable_cluster",
        )
        in verdict.failure_ids
    )


@pytest.mark.parametrize(
    "status",
    (ExecutionStatus.SKIPPED, ExecutionStatus.XFAIL, ExecutionStatus.ERROR),
)
def test_negative_nonexecuted_status_is_not_counted(
    mutation_catalog: MutationCatalog,
    status: ExecutionStatus,
) -> None:
    """KILL-02: skip・xfail・error を実行済みの kill と数えない。"""
    spec = mutation_catalog.mutants[0]
    observation = _valid_observation(spec)
    observation = replace(
        observation,
        schema_drift=replace(observation.schema_drift, status=status),
    )

    verdict = _judge(mutation_catalog, spec, observation)

    assert not verdict.accepted
    assert (
        _condition_id(
            mutation_catalog,
            "not_skip_not_xfail_not_error",
        )
        in verdict.failure_ids
    )


def test_negative_unexpected_failure_kind_is_not_counted(
    mutation_catalog: MutationCatalog,
) -> None:
    """KILL-03: 期待外の例外種別を kill と数えない。"""
    spec = mutation_catalog.mutants[0]
    observation = _valid_observation(spec)
    observation = replace(
        observation,
        schema_drift=replace(
            observation.schema_drift,
            failure_kind=FailureKind.OTHER,
        ),
    )

    verdict = _judge(mutation_catalog, spec, observation)

    assert not verdict.accepted
    assert (
        _condition_id(
            mutation_catalog,
            "expected_assertion_or_sqlstate_only",
        )
        in verdict.failure_ids
    )


def test_negative_schema_drift_cannot_replace_runtime_result(
    mutation_catalog: MutationCatalog,
) -> None:
    """Schema-drift の red だけで runtime kill を満たした扱いにしない。"""
    spec = _only_spec(
        mutation_catalog,
        lambda mutant: mutant.expected_runtime_outcome == "kill",
    )
    observation = _valid_observation(spec)
    observation = replace(
        observation,
        runtime_cross_tenant=ChannelObservation.not_run(NotRunReason.HANDOFF),
    )

    verdict = _judge(mutation_catalog, spec, observation)

    assert not verdict.accepted
    assert "runtime_cross_tenant" in verdict.failure_ids
    assert "schema_drift" not in verdict.failure_ids


def test_negative_survives_layered_defense_cannot_be_treated_as_kill(
    mutation_catalog: MutationCatalog,
) -> None:
    """Runtime の survives_layered_defense を kill の失敗結果で代替しない。"""
    spec = _only_spec(
        mutation_catalog,
        lambda mutant: mutant.expected_runtime_outcome == "survives_layered_defense",
    )
    observation = _valid_observation(spec)
    observation = replace(
        observation,
        runtime_cross_tenant=ChannelObservation.expected_assertion_failure(),
    )

    verdict = _judge(mutation_catalog, spec, observation)

    assert not verdict.accepted
    assert "runtime_cross_tenant" in verdict.failure_ids
    assert "schema_drift" not in verdict.failure_ids


def test_real_asset_rows_have_a_satisfiable_verdict_contract(
    mutation_catalog: MutationCatalog,
) -> None:
    """全資産行の多値期待を合成観測で解釈できることだけを確認する。"""
    verdicts = tuple(
        _judge(mutation_catalog, spec, _valid_observation(spec))
        for spec in mutation_catalog.mutants
    )

    assert all(verdict.accepted for verdict in verdicts)
    assert {verdict.mutant_id for verdict in verdicts} == set(
        mutation_catalog.mutant_by_id
    )
