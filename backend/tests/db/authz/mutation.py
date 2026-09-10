"""資産駆動の mutation 実行計画と kill 判定を提供する。"""

from __future__ import annotations

import json
import secrets
from collections.abc import Callable, Iterator, Mapping
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Protocol

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
CLAIM_MUTANT_MAP_PATH = REPOSITORY_ROOT / "contracts/authz/claim-mutant-map.json"


class MutationContractError(ValueError):
    """Mutation 資産とランナー実装の契約不一致を表す。"""


class MutationVerdictError(AssertionError):
    """観測結果を kill として受理できないことを表す。"""


class ExecutionStatus(StrEnum):
    """テスト呼び出しの終了状態。"""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    XFAIL = "xfail"
    ERROR = "error"
    NOT_RUN = "not_run"


class ExecutionPhase(StrEnum):
    """テスト失敗が発生したフェーズ。"""

    SETUP = "setup"
    CALL = "call"
    TEARDOWN = "teardown"
    NOT_RUN = "not_run"


class FailureKind(StrEnum):
    """テスト失敗の分類。"""

    ASSERTION = "assertion"
    SQLSTATE = "sqlstate"
    AVAILABILITY = "availability"
    OTHER = "other"


class NotRunReason(StrEnum):
    """テストを呼び出さない契約上の理由。"""

    HANDOFF = "handoff"
    APPLICATION_FAILED = "application_failed"


@dataclass(frozen=True, slots=True)
class MutantSpec:
    """資産の mutation レコードを実行用に型付けした値。"""

    mutant_id: str
    axis: str
    operator_id: str
    decision_form: str
    claim_ids: tuple[str, ...]
    target_element_ids: frozenset[str]
    expected_application_outcome: str
    expected_drift_outcome: str
    expected_runtime_outcome: str
    runtime_kill_required: bool
    requires_disposable_cluster: bool
    schema_drift_test_id: str
    runtime_test_id: str
    runtime_kill_waiver_reason: str | None
    expected_positive_outcome: str
    positive_kill_required: bool
    positive_case_scope_id: str | None


@dataclass(frozen=True, slots=True)
class KillCondition:
    """資産が宣言する condition ID と実装要件の対。"""

    condition_id: str
    requirement: str


@dataclass(frozen=True, slots=True)
class VerdictChannelContract:
    """独立判定が必要な verdict チャネル。"""

    channel_id: str
    requirement: str


@dataclass(frozen=True, slots=True)
class OutcomeVocabularies:
    """Mutation 全行から導出した期待結果の閉じた語彙。"""

    application: frozenset[str]
    schema_drift: frozenset[str]
    runtime_cross_tenant: frozenset[str]
    runtime_positive_case: frozenset[str]


@dataclass(frozen=True, slots=True)
class KillContract:
    """資産から導出した kill 判定契約。"""

    channels: tuple[VerdictChannelContract, ...]
    conditions: tuple[KillCondition, ...]
    contract_only_runtime_rule: str
    positive_case_rule: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class MutationCatalog:
    """ランナーが使う mutation と kill 契約の全入力。"""

    mutants: tuple[MutantSpec, ...]
    mutant_by_id: Mapping[str, MutantSpec]
    mutant_axes: frozenset[str]
    kill_contract: KillContract
    outcome_vocabularies: OutcomeVocabularies


@dataclass(frozen=True, slots=True)
class ApplicationObservation:
    """変異適用そのものの観測結果。"""

    applied: bool
    sqlstate: str | None = None

    @classmethod
    def success(cls) -> ApplicationObservation:
        """適用成功の観測値を返す。"""
        return cls(applied=True)

    @classmethod
    def expected_sqlstate_failure(cls, sqlstate: str) -> ApplicationObservation:
        """SQLSTATE を伴う適用失敗の観測値を返す。"""
        return cls(applied=False, sqlstate=sqlstate)


@dataclass(frozen=True, slots=True)
class ChannelObservation:
    """独立した 1 判定チャネルの生のテスト結果。"""

    status: ExecutionStatus
    phase: ExecutionPhase
    failure_kind: FailureKind | None = None
    expected_failure_kind: FailureKind | None = None
    sqlstate: str | None = None
    expected_sqlstate: str | None = None
    not_run_reason: NotRunReason | None = None

    @classmethod
    def passed(cls) -> ChannelObservation:
        """Call フェーズを通過した観測値を返す。"""
        return cls(status=ExecutionStatus.PASSED, phase=ExecutionPhase.CALL)

    @classmethod
    def expected_assertion_failure(cls) -> ChannelObservation:
        """期待した assertion で call が失敗した観測値を返す。"""
        return cls(
            status=ExecutionStatus.FAILED,
            phase=ExecutionPhase.CALL,
            failure_kind=FailureKind.ASSERTION,
            expected_failure_kind=FailureKind.ASSERTION,
        )

    @classmethod
    def expected_sqlstate_failure(cls, sqlstate: str) -> ChannelObservation:
        """期待した SQLSTATE で call が失敗した観測値を返す。"""
        return cls(
            status=ExecutionStatus.FAILED,
            phase=ExecutionPhase.CALL,
            failure_kind=FailureKind.SQLSTATE,
            expected_failure_kind=FailureKind.SQLSTATE,
            sqlstate=sqlstate,
            expected_sqlstate=sqlstate,
        )

    @classmethod
    def availability_failure(cls) -> ChannelObservation:
        """可用性だけを破壊した call の観測値を返す。"""
        return cls(
            status=ExecutionStatus.FAILED,
            phase=ExecutionPhase.CALL,
            failure_kind=FailureKind.AVAILABILITY,
        )

    @classmethod
    def not_run(cls, reason: NotRunReason) -> ChannelObservation:
        """契約上実行しないチャネルの観測値を返す。"""
        return cls(
            status=ExecutionStatus.NOT_RUN,
            phase=ExecutionPhase.NOT_RUN,
            not_run_reason=reason,
        )


@dataclass(frozen=True, slots=True)
class CatalogDelta:
    """変異適用前後で変わったカタログ属性集合。"""

    changed_element_ids: frozenset[str]


@dataclass(frozen=True, slots=True)
class MutationObservation:
    """適用結果と独立 3 チャネルの観測値。"""

    application: ApplicationObservation
    catalog_delta: CatalogDelta
    schema_drift: ChannelObservation
    runtime_cross_tenant: ChannelObservation
    runtime_positive_case: ChannelObservation


@dataclass(frozen=True, slots=True)
class MutationPlan:
    """1 変異に割り当てる DB とクラスタの隔離計画。"""

    mutant_id: str
    fresh_database: bool
    fresh_cluster: bool


@dataclass(frozen=True, slots=True)
class IsolationReceipt:
    """隔離プロバイダが実際に供給した環境の証跡。"""

    database_id: str
    cluster_id: str
    database_is_fresh: bool
    cluster_is_fresh: bool


@dataclass(frozen=True, slots=True)
class MutationEnvironment:
    """単一 mutation 専用 DB の接続情報と隔離証跡。"""

    mutant_id: str
    database_dsn: str
    isolation: IsolationReceipt


@dataclass(frozen=True, slots=True)
class ChannelVerdict:
    """1 チャネルの期待結果と独立した判定結果。"""

    channel_id: str
    expected_outcome: str
    matched: bool


@dataclass(frozen=True, slots=True)
class ConditionVerdict:
    """資産由来 condition 1 件の判定結果。"""

    condition_id: str
    requirement: str
    passed: bool


@dataclass(frozen=True, slots=True)
class MutationVerdict:
    """1 変異を kill として数えられるかの全判定結果。"""

    mutant_id: str
    application_matched: bool
    channel_verdicts: tuple[ChannelVerdict, ...]
    condition_verdicts: tuple[ConditionVerdict, ...]
    isolation_matched: bool

    @property
    def accepted(self) -> bool:
        """全チャネル・全条件・隔離が合格したかを返す。"""
        return (
            self.application_matched
            and all(verdict.matched for verdict in self.channel_verdicts)
            and all(verdict.passed for verdict in self.condition_verdicts)
            and self.isolation_matched
        )

    @property
    def failure_ids(self) -> tuple[str, ...]:
        """不合格になった判定の識別子を返す。"""
        failures: list[str] = []
        if not self.application_matched:
            failures.append("application")
        failures.extend(
            verdict.channel_id
            for verdict in self.channel_verdicts
            if not verdict.matched
        )
        failures.extend(
            verdict.condition_id
            for verdict in self.condition_verdicts
            if not verdict.passed
        )
        if not self.isolation_matched:
            failures.append("fresh_database_or_cluster")
        return tuple(failures)


class MutationCluster(Protocol):
    """既存または使い捨てクラスタから必要な接続情報。"""

    container_name: str
    admin_dsn: str


class MutationIsolationProvider(Protocol):
    """新しい DB と必要時だけ新しいクラスタを供給する境界。"""

    def isolated_database(
        self, plan: MutationPlan
    ) -> AbstractContextManager[MutationEnvironment]:
        """共有クラスタ内の新しい DB を供給する。"""

    def isolated_cluster_database(
        self, plan: MutationPlan
    ) -> AbstractContextManager[MutationEnvironment]:
        """新しいクラスタ内の新しい DB を供給する。"""


MutationExecutor = Callable[[MutantSpec, MutationEnvironment], MutationObservation]
ConditionImplementation = Callable[
    [MutantSpec, MutationObservation, MutationPlan, IsolationReceipt], bool
]
ChannelImplementation = Callable[[ChannelObservation], bool]
ApplicationImplementation = Callable[[ApplicationObservation], bool]


def _expected_failure(observation: ChannelObservation) -> bool:
    """Call フェーズの通常失敗であるかを返す。"""
    return (
        observation.status is ExecutionStatus.FAILED
        and observation.phase is ExecutionPhase.CALL
        and observation.failure_kind is not FailureKind.AVAILABILITY
    )


def _handoff(observation: ChannelObservation) -> bool:
    """受取先へ渡すため未実行であるかを返す。"""
    return (
        observation.status is ExecutionStatus.NOT_RUN
        and observation.phase is ExecutionPhase.NOT_RUN
        and observation.not_run_reason is NotRunReason.HANDOFF
    )


def _not_run_application_failed(observation: ChannelObservation) -> bool:
    """適用失敗により未実行であるかを返す。"""
    return (
        observation.status is ExecutionStatus.NOT_RUN
        and observation.phase is ExecutionPhase.NOT_RUN
        and observation.not_run_reason is NotRunReason.APPLICATION_FAILED
    )


def _passed(observation: ChannelObservation) -> bool:
    """Call フェーズを通過したかを返す。"""
    return (
        observation.status is ExecutionStatus.PASSED
        and observation.phase is ExecutionPhase.CALL
    )


def _availability_failure(observation: ChannelObservation) -> bool:
    """Call フェーズの可用性失敗であるかを返す。"""
    return (
        observation.status is ExecutionStatus.FAILED
        and observation.phase is ExecutionPhase.CALL
        and observation.failure_kind is FailureKind.AVAILABILITY
    )


def _application_applies(observation: ApplicationObservation) -> bool:
    """変異が適用成功したかを返す。"""
    return observation.applied and observation.sqlstate is None


def _application_fails_42501(observation: ApplicationObservation) -> bool:
    """変異適用が期待 SQLSTATE 42501 で失敗したかを返す。"""
    return not observation.applied and observation.sqlstate == "42501"


_APPLICATION_IMPLEMENTATIONS: Mapping[str, ApplicationImplementation] = {
    "applies": _application_applies,
    "fails_expected_sqlstate_42501": _application_fails_42501,
}
_SCHEMA_DRIFT_IMPLEMENTATIONS: Mapping[str, ChannelImplementation] = {
    "red": _expected_failure,
}
_RUNTIME_IMPLEMENTATIONS: Mapping[str, ChannelImplementation] = {
    "handoff": _handoff,
    "kill": _expected_failure,
    "survives_layered_defense": _passed,
    "availability_failure": _availability_failure,
    "not_run_application_failed": _not_run_application_failed,
}
_POSITIVE_IMPLEMENTATIONS: Mapping[str, ChannelImplementation] = {
    "handoff": _handoff,
    "pass": _passed,
    "kill": _expected_failure,
    "not_run_application_failed": _not_run_application_failed,
}


def _channel_schema_drift(observation: MutationObservation) -> ChannelObservation:
    """schema-drift チャネルだけを返す。"""
    return observation.schema_drift


def _channel_runtime(observation: MutationObservation) -> ChannelObservation:
    """越境 runtime チャネルだけを返す。"""
    return observation.runtime_cross_tenant


def _channel_positive(observation: MutationObservation) -> ChannelObservation:
    """正例 runtime チャネルだけを返す。"""
    return observation.runtime_positive_case


def _expected_schema_drift(spec: MutantSpec) -> str:
    """schema-drift の期待値を返す。"""
    return spec.expected_drift_outcome


def _expected_runtime(spec: MutantSpec) -> str:
    """越境 runtime の期待値を返す。"""
    return spec.expected_runtime_outcome


def _expected_positive(spec: MutantSpec) -> str:
    """正例 runtime の期待値を返す。"""
    return spec.expected_positive_outcome


_CHANNEL_OBSERVATION_ACCESSORS: Mapping[
    str, Callable[[MutationObservation], ChannelObservation]
] = {
    "schema_drift": _channel_schema_drift,
    "runtime_cross_tenant": _channel_runtime,
    "runtime_positive_case": _channel_positive,
}
_CHANNEL_EXPECTATION_ACCESSORS: Mapping[str, Callable[[MutantSpec], str]] = {
    "schema_drift": _expected_schema_drift,
    "runtime_cross_tenant": _expected_runtime,
    "runtime_positive_case": _expected_positive,
}
_CHANNEL_IMPLEMENTATIONS: Mapping[str, Mapping[str, ChannelImplementation]] = {
    "schema_drift": _SCHEMA_DRIFT_IMPLEMENTATIONS,
    "runtime_cross_tenant": _RUNTIME_IMPLEMENTATIONS,
    "runtime_positive_case": _POSITIVE_IMPLEMENTATIONS,
}


def _kill_observations(
    spec: MutantSpec,
    observation: MutationObservation,
) -> tuple[ChannelObservation, ...]:
    """資産の期待値が red または kill の独立チャネルだけを返す。"""
    kill_outcomes = {"red", "kill"}
    return tuple(
        _CHANNEL_OBSERVATION_ACCESSORS[channel_id](observation)
        for channel_id, expected_accessor in _CHANNEL_EXPECTATION_ACCESSORS.items()
        if expected_accessor(spec) in kill_outcomes
    )


def _only_declared_targets_changed(
    spec: MutantSpec,
    observation: MutationObservation,
    plan: MutationPlan,
    isolation: IsolationReceipt,
) -> bool:
    """宣言外のカタログ属性が変化していないかを判定する。"""
    del plan, isolation
    changed = observation.catalog_delta.changed_element_ids
    return bool(changed) and changed <= spec.target_element_ids


def _tests_executed(
    spec: MutantSpec,
    observation: MutationObservation,
    plan: MutationPlan,
    isolation: IsolationReceipt,
) -> bool:
    """Kill 対象を skip・xfail・error で代替していないかを判定する。"""
    del plan, isolation
    return all(
        channel.status is ExecutionStatus.FAILED
        for channel in _kill_observations(spec, observation)
    )


def _expected_failures_only(
    spec: MutantSpec,
    observation: MutationObservation,
    plan: MutationPlan,
    isolation: IsolationReceipt,
) -> bool:
    """期待した assertion または SQLSTATE だけで kill したかを判定する。"""
    del plan, isolation
    for channel in _kill_observations(spec, observation):
        if channel.failure_kind is not channel.expected_failure_kind:
            return False
        if channel.failure_kind is FailureKind.ASSERTION:
            if channel.sqlstate is not None or channel.expected_sqlstate is not None:
                return False
            continue
        if channel.failure_kind is FailureKind.SQLSTATE:
            if (
                channel.sqlstate is None
                or channel.sqlstate != channel.expected_sqlstate
            ):
                return False
            continue
        return False
    return True


def _no_fixture_failure(
    spec: MutantSpec,
    observation: MutationObservation,
    plan: MutationPlan,
    isolation: IsolationReceipt,
) -> bool:
    """setup・teardown の失敗を kill と数えていないかを判定する。"""
    del plan, isolation
    return all(
        channel.phase is ExecutionPhase.CALL
        for channel in _kill_observations(spec, observation)
    )


def _global_state_isolated(
    spec: MutantSpec,
    observation: MutationObservation,
    plan: MutationPlan,
    isolation: IsolationReceipt,
) -> bool:
    """資産が要求した変異だけを新しいクラスタへ隔離したかを判定する。"""
    del observation
    return (
        plan.fresh_cluster is spec.requires_disposable_cluster
        and isolation.cluster_is_fresh is spec.requires_disposable_cluster
    )


_CONDITION_IMPLEMENTATIONS: Mapping[str, ConditionImplementation] = {
    "only_declared_target_attributes_changed": _only_declared_targets_changed,
    "not_skip_not_xfail_not_error": _tests_executed,
    "expected_assertion_or_sqlstate_only": _expected_failures_only,
    "setup_and_teardown_failure_never_counts": _no_fixture_failure,
    "role_attribute_membership_default_acl_use_disposable_cluster": (
        _global_state_isolated
    ),
}


def _required_string(value: object, label: str) -> str:
    """空でない文字列を取得する。"""
    if not isinstance(value, str) or not value:
        raise MutationContractError(f"{label}は空でない文字列が必要")
    return value


def _optional_string(value: object, label: str) -> str | None:
    """Null または空でない文字列を取得する。"""
    if value is None:
        return None
    return _required_string(value, label)


def _required_bool(value: object, label: str) -> bool:
    """Boolean 値を取得する。"""
    if not isinstance(value, bool):
        raise MutationContractError(f"{label}はbooleanが必要")
    return value


def _string_tuple(value: object, label: str) -> tuple[str, ...]:
    """重複のない空でない文字列配列を取得する。"""
    if not isinstance(value, list) or not value:
        raise MutationContractError(f"{label}は空でない配列が必要")
    result = tuple(_required_string(item, f"{label}[]") for item in value)
    if len(result) != len(set(result)):
        raise MutationContractError(f"{label}に重複がある")
    return result


def _object_rows(value: object, label: str) -> tuple[dict[str, object], ...]:
    """Object 配列を取得する。"""
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(row, dict) for row in value)
    ):
        raise MutationContractError(f"{label}は空でないobject配列が必要")
    return tuple(row for row in value if isinstance(row, dict))


def _bind_exact_implementations(
    asset_values: frozenset[str],
    implementations: Mapping[str, object],
    label: str,
) -> None:
    """資産語彙と実装済み語彙を exact-set で結ぶ。"""
    implemented = frozenset(implementations)
    if asset_values != implemented:
        missing = sorted(asset_values - implemented)
        stale = sorted(implemented - asset_values)
        raise MutationContractError(
            f"{label}の実装が資産語彙と不一致: 未実装={missing}, 余剰={stale}"
        )


def _mutant_spec(row: dict[str, object], index: int) -> MutantSpec:
    """資産の mutation 1 行を型付けする。"""
    label = f"mutants[{index}]"
    return MutantSpec(
        mutant_id=_required_string(row.get("mutant_id"), f"{label}.mutant_id"),
        axis=_required_string(row.get("axis"), f"{label}.axis"),
        operator_id=_required_string(row.get("operator_id"), f"{label}.operator_id"),
        decision_form=_required_string(
            row.get("decision_form"), f"{label}.decision_form"
        ),
        claim_ids=_string_tuple(row.get("claim_ids"), f"{label}.claim_ids"),
        target_element_ids=frozenset(
            _string_tuple(
                row.get("target_element_ids"),
                f"{label}.target_element_ids",
            )
        ),
        expected_application_outcome=_required_string(
            row.get("expected_application_outcome"),
            f"{label}.expected_application_outcome",
        ),
        expected_drift_outcome=_required_string(
            row.get("expected_drift_outcome"),
            f"{label}.expected_drift_outcome",
        ),
        expected_runtime_outcome=_required_string(
            row.get("expected_runtime_outcome"),
            f"{label}.expected_runtime_outcome",
        ),
        runtime_kill_required=_required_bool(
            row.get("runtime_kill_required"),
            f"{label}.runtime_kill_required",
        ),
        requires_disposable_cluster=_required_bool(
            row.get("requires_disposable_cluster"),
            f"{label}.requires_disposable_cluster",
        ),
        schema_drift_test_id=_required_string(
            row.get("schema_drift_test_id"),
            f"{label}.schema_drift_test_id",
        ),
        runtime_test_id=_required_string(
            row.get("runtime_test_id"),
            f"{label}.runtime_test_id",
        ),
        runtime_kill_waiver_reason=_optional_string(
            row.get("runtime_kill_waiver_reason"),
            f"{label}.runtime_kill_waiver_reason",
        ),
        expected_positive_outcome=_required_string(
            row.get("expected_positive_outcome"),
            f"{label}.expected_positive_outcome",
        ),
        positive_kill_required=_required_bool(
            row.get("positive_kill_required"),
            f"{label}.positive_kill_required",
        ),
        positive_case_scope_id=_optional_string(
            row.get("positive_case_scope_id"),
            f"{label}.positive_case_scope_id",
        ),
    )


def load_mutation_catalog_data(raw: object) -> MutationCatalog:
    """JSON object から mutation ランナーの契約を構築する。

    Args:
        raw: ``claim-mutant-map.json`` と同じ構造の値。

    Returns:
        型付けし、実装と exact-set 結合した mutation 契約。

    Raises:
        MutationContractError: 資産値が不正または未実装の場合。
    """
    if not isinstance(raw, dict):
        raise MutationContractError("claim-mutant-mapはJSON objectが必要")
    mutant_axes = frozenset(_string_tuple(raw.get("mutant_axes"), "mutant_axes"))
    rows = _object_rows(raw.get("mutants"), "mutants")
    mutants = tuple(_mutant_spec(row, index) for index, row in enumerate(rows))
    mutant_by_id = {mutant.mutant_id: mutant for mutant in mutants}
    if len(mutant_by_id) != len(mutants):
        raise MutationContractError("mutant_idが重複している")
    unknown_axes = sorted({mutant.axis for mutant in mutants} - mutant_axes)
    if unknown_axes:
        raise MutationContractError(f"mutant axisが資産の母集合外: {unknown_axes}")

    kill_contract_raw = raw.get("kill_contract")
    if not isinstance(kill_contract_raw, dict):
        raise MutationContractError("kill_contractはobjectが必要")
    channel_values = kill_contract_raw.get("verdict_channels")
    if not isinstance(channel_values, dict) or not channel_values:
        raise MutationContractError("verdict_channelsは空でないobjectが必要")
    channels = tuple(
        VerdictChannelContract(
            channel_id=_required_string(channel_id, "verdict channel ID"),
            requirement=_required_string(requirement, f"{channel_id}.requirement"),
        )
        for channel_id, requirement in channel_values.items()
    )
    if any(
        channel.requirement != "independent_required_result" for channel in channels
    ):
        raise MutationContractError("全verdict channelに独立結果が必要")
    channel_ids = frozenset(channel.channel_id for channel in channels)
    _bind_exact_implementations(
        channel_ids,
        _CHANNEL_OBSERVATION_ACCESSORS,
        "verdict channel observation",
    )
    _bind_exact_implementations(
        channel_ids,
        _CHANNEL_EXPECTATION_ACCESSORS,
        "verdict channel expectation",
    )
    _bind_exact_implementations(
        channel_ids,
        _CHANNEL_IMPLEMENTATIONS,
        "verdict channel outcome",
    )

    condition_rows = _object_rows(
        kill_contract_raw.get("conditions"),
        "kill_contract.conditions",
    )
    conditions = tuple(
        KillCondition(
            condition_id=_required_string(
                row.get("condition_id"),
                f"kill_contract.conditions[{index}].condition_id",
            ),
            requirement=_required_string(
                row.get("requirement"),
                f"kill_contract.conditions[{index}].requirement",
            ),
        )
        for index, row in enumerate(condition_rows)
    )
    if len({condition.condition_id for condition in conditions}) != len(conditions):
        raise MutationContractError("kill condition IDが重複している")
    if len({condition.requirement for condition in conditions}) != len(conditions):
        raise MutationContractError("kill condition requirementが重複している")
    _bind_exact_implementations(
        frozenset(condition.requirement for condition in conditions),
        _CONDITION_IMPLEMENTATIONS,
        "kill condition",
    )

    positive_case_rule = kill_contract_raw.get("positive_case_rule")
    if not isinstance(positive_case_rule, dict):
        raise MutationContractError("positive_case_ruleはobjectが必要")
    contract_only_runtime_rule = _required_string(
        kill_contract_raw.get("contract_only_runtime_rule"),
        "contract_only_runtime_rule",
    )
    vocabularies = OutcomeVocabularies(
        application=frozenset(
            mutant.expected_application_outcome for mutant in mutants
        ),
        schema_drift=frozenset(mutant.expected_drift_outcome for mutant in mutants),
        runtime_cross_tenant=frozenset(
            mutant.expected_runtime_outcome for mutant in mutants
        ),
        runtime_positive_case=frozenset(
            mutant.expected_positive_outcome for mutant in mutants
        ),
    )
    _bind_exact_implementations(
        vocabularies.application,
        _APPLICATION_IMPLEMENTATIONS,
        "expected_application_outcome",
    )
    _bind_exact_implementations(
        vocabularies.schema_drift,
        _SCHEMA_DRIFT_IMPLEMENTATIONS,
        "expected_drift_outcome",
    )
    _bind_exact_implementations(
        vocabularies.runtime_cross_tenant,
        _RUNTIME_IMPLEMENTATIONS,
        "expected_runtime_outcome",
    )
    _bind_exact_implementations(
        vocabularies.runtime_positive_case,
        _POSITIVE_IMPLEMENTATIONS,
        "expected_positive_outcome",
    )
    for mutant in mutants:
        if mutant.runtime_kill_required is not (
            mutant.expected_runtime_outcome == "kill"
        ):
            raise MutationContractError(
                f"{mutant.mutant_id}: runtime kill flagと期待値が不一致"
            )
        if mutant.positive_kill_required is not (
            mutant.expected_positive_outcome == "kill"
        ):
            raise MutationContractError(
                f"{mutant.mutant_id}: positive kill flagと期待値が不一致"
            )

    return MutationCatalog(
        mutants=mutants,
        mutant_by_id=MappingProxyType(mutant_by_id),
        mutant_axes=mutant_axes,
        kill_contract=KillContract(
            channels=channels,
            conditions=conditions,
            contract_only_runtime_rule=contract_only_runtime_rule,
            positive_case_rule=MappingProxyType(dict(positive_case_rule)),
        ),
        outcome_vocabularies=vocabularies,
    )


def load_mutation_catalog(
    path: Path = CLAIM_MUTANT_MAP_PATH,
) -> MutationCatalog:
    """ファイルから mutation ランナーの契約を構築する。

    Args:
        path: ``claim-mutant-map.json`` のパス。

    Returns:
        資産由来の mutation 契約。
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise MutationContractError(
            f"mutation資産を読めない: {path}: {error}"
        ) from error
    return load_mutation_catalog_data(raw)


def mutation_plan(spec: MutantSpec) -> MutationPlan:
    """全変異を新 DB、指定変異だけを新クラスタへ割り当てる。"""
    return MutationPlan(
        mutant_id=spec.mutant_id,
        fresh_database=True,
        fresh_cluster=spec.requires_disposable_cluster,
    )


def judge_mutation(
    catalog: MutationCatalog,
    spec: MutantSpec,
    observation: MutationObservation,
    plan: MutationPlan,
    isolation: IsolationReceipt,
) -> MutationVerdict:
    """資産の期待値と全 kill 条件で 1 変異を判定する。

    Args:
        catalog: 資産由来の mutation 契約。
        spec: 判定対象の変異。
        observation: 適用と 3 チャネルの実測結果。
        plan: 当該変異の隔離計画。
        isolation: 実際に供給された隔離環境の証跡。

    Returns:
        各チャネルと条件を独立に保持する判定結果。
    """
    application_matched = _APPLICATION_IMPLEMENTATIONS[
        spec.expected_application_outcome
    ](observation.application)
    channel_verdicts = tuple(
        ChannelVerdict(
            channel_id=channel.channel_id,
            expected_outcome=(
                expected_outcome := _CHANNEL_EXPECTATION_ACCESSORS[channel.channel_id](
                    spec
                )
            ),
            matched=_CHANNEL_IMPLEMENTATIONS[channel.channel_id][expected_outcome](
                _CHANNEL_OBSERVATION_ACCESSORS[channel.channel_id](observation)
            ),
        )
        for channel in catalog.kill_contract.channels
    )
    condition_verdicts = tuple(
        ConditionVerdict(
            condition_id=condition.condition_id,
            requirement=condition.requirement,
            passed=_CONDITION_IMPLEMENTATIONS[condition.requirement](
                spec,
                observation,
                plan,
                isolation,
            ),
        )
        for condition in catalog.kill_contract.conditions
    )
    isolation_matched = (
        plan.mutant_id == spec.mutant_id
        and plan.fresh_database
        and isolation.database_is_fresh
        and isolation.cluster_is_fresh is plan.fresh_cluster
    )
    return MutationVerdict(
        mutant_id=spec.mutant_id,
        application_matched=application_matched,
        channel_verdicts=channel_verdicts,
        condition_verdicts=condition_verdicts,
        isolation_matched=isolation_matched,
    )


class PsycopgMutationIsolationProvider:
    """psycopg と既存 Docker fixture で mutation 専用 DB を供給する。"""

    def __init__(
        self,
        shared_cluster: MutationCluster,
        disposable_cluster_factory: Callable[
            [], AbstractContextManager[MutationCluster]
        ],
    ) -> None:
        """共有クラスタと使い捨てクラスタ factory を保持する。"""
        self._shared_cluster = shared_cluster
        self._disposable_cluster_factory = disposable_cluster_factory

    @contextmanager
    def _fresh_database(
        self,
        plan: MutationPlan,
        cluster: MutationCluster,
        *,
        cluster_is_fresh: bool,
    ) -> Iterator[MutationEnvironment]:
        """指定クラスタ内へ一意な mutation 専用 DB を作成して破棄する。"""
        database_name = f"pitchlog_mutant_{secrets.token_hex(8)}"
        with psycopg.connect(cluster.admin_dsn, autocommit=True) as admin:
            with admin.cursor() as cursor:
                cursor.execute(
                    sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name))
                )
        database_dsn = make_conninfo(cluster.admin_dsn, dbname=database_name)
        try:
            yield MutationEnvironment(
                mutant_id=plan.mutant_id,
                database_dsn=database_dsn,
                isolation=IsolationReceipt(
                    database_id=f"{cluster.container_name}:{database_name}",
                    cluster_id=cluster.container_name,
                    database_is_fresh=True,
                    cluster_is_fresh=cluster_is_fresh,
                ),
            )
        finally:
            with psycopg.connect(cluster.admin_dsn, autocommit=True) as admin:
                with admin.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT pg_catalog.pg_terminate_backend(activity.pid)
                        FROM pg_catalog.pg_stat_activity AS activity
                        WHERE activity.datname = %s
                          AND activity.pid <> pg_catalog.pg_backend_pid()
                        """,
                        (database_name,),
                    )
                    cursor.execute(
                        sql.SQL("DROP DATABASE {}").format(
                            sql.Identifier(database_name)
                        )
                    )

    def isolated_database(
        self, plan: MutationPlan
    ) -> AbstractContextManager[MutationEnvironment]:
        """共有クラスタ内の新しい DB を供給する。"""
        return self._fresh_database(
            plan,
            self._shared_cluster,
            cluster_is_fresh=False,
        )

    @contextmanager
    def isolated_cluster_database(
        self, plan: MutationPlan
    ) -> Iterator[MutationEnvironment]:
        """新しいクラスタ内の新しい DB を供給する。"""
        with self._disposable_cluster_factory() as cluster:
            with self._fresh_database(
                plan,
                cluster,
                cluster_is_fresh=True,
            ) as environment:
                yield environment


class MutationRunner:
    """資産から選んだ 1 変異を隔離環境で実行して判定する。"""

    def __init__(
        self,
        catalog: MutationCatalog,
        isolation_provider: MutationIsolationProvider,
    ) -> None:
        """契約と隔離プロバイダを保持する。"""
        self.catalog = catalog
        self._isolation_provider = isolation_provider
        self._used_database_ids: set[str] = set()
        self._used_fresh_cluster_ids: set[str] = set()

    def plan_for(self, mutant_id: str) -> MutationPlan:
        """資産フラグから指定変異の隔離計画を返す。"""
        try:
            spec = self.catalog.mutant_by_id[mutant_id]
        except KeyError as error:
            raise MutationContractError(f"未知のmutant_id: {mutant_id}") from error
        return mutation_plan(spec)

    def _record_isolation(
        self,
        plan: MutationPlan,
        environment: MutationEnvironment,
    ) -> None:
        """DB と使い捨てクラスタが過去の変異と重複しないことを確認する。"""
        receipt = environment.isolation
        if environment.mutant_id != plan.mutant_id:
            raise MutationVerdictError("隔離環境のmutant_idが実行計画と一致しない")
        if receipt.database_id in self._used_database_ids:
            raise MutationVerdictError("新しいDBが変異ごとに供給されていない")
        self._used_database_ids.add(receipt.database_id)
        if plan.fresh_cluster:
            if receipt.cluster_id in self._used_fresh_cluster_ids:
                raise MutationVerdictError(
                    "使い捨てクラスタが対象変異ごとに新設されていない"
                )
            self._used_fresh_cluster_ids.add(receipt.cluster_id)

    def run_one(
        self,
        mutant_id: str,
        executor: MutationExecutor,
    ) -> MutationVerdict:
        """指定した 1 変異だけを実行し、全条件不合格なら例外にする。"""
        spec = self.catalog.mutant_by_id.get(mutant_id)
        if spec is None:
            raise MutationContractError(f"未知のmutant_id: {mutant_id}")
        plan = mutation_plan(spec)
        if plan.fresh_cluster:
            isolation_scope = self._isolation_provider.isolated_cluster_database(plan)
        else:
            isolation_scope = self._isolation_provider.isolated_database(plan)
        with isolation_scope as environment:
            self._record_isolation(plan, environment)
            observation = executor(spec, environment)
            verdict = judge_mutation(
                self.catalog,
                spec,
                observation,
                plan,
                environment.isolation,
            )
            if not verdict.accepted:
                raise MutationVerdictError(
                    f"{mutant_id}: kill判定不合格: {verdict.failure_ids}"
                )
            return verdict
