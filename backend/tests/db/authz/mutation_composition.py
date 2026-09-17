"""2因子相互作用・最小cut set・MC/DCを資産から実行する。"""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from itertools import combinations
from pathlib import Path
from types import MappingProxyType
from typing import Final, TypeVar

from .mutation import (
    MutationCatalog,
    _bind_exact_implementations,
    load_mutation_catalog,
)
from .mutation_execution import (
    _CHECKER,
    DDL_ELEMENTS_PATH,
    ORACLE_SEAL_PATH,
    REPOSITORY_ROOT,
    _mutate_ddl_configuration,
    _read_json_object,
)

CLAIM_MUTANT_MAP_PATH = REPOSITORY_ROOT / "contracts/authz/claim-mutant-map.json"
ATTACK_TREE_PATH = REPOSITORY_ROOT / "contracts/authz/attack-tree.json"
MCDC_MAP_PATH = REPOSITORY_ROOT / "contracts/authz/mcdc-map.json"
ORACLE_SEAL_RELATIVE_PATH = "contracts/authz/oracle-seal.lock.json"
_BOUNDARY_PROPOSAL_RELATIVE_PATH = "contracts/authz/boundary-proposal.json"
_DDL_ELEMENTS_RELATIVE_PATH = "contracts/authz/ddl-elements.json"
STEP2_BASE_REVISION = "099a8fa20595c25f553b46dedcaaa9660dd03c2e"
STEP2_CHANGED_CANONICAL_ASSET_PATHS: frozenset[str] = frozenset()

INTERACTION_FILTER_ENV = "PITCHLOG_MUTATION_INTERACTION"
CUT_SET_FILTER_ENV = "PITCHLOG_MUTATION_CUT_SET"
MCDC_DECISION_FILTER_ENV = "PITCHLOG_MUTATION_MCDC_DECISION"

_PAIR_POPULATION_RULE = "all_unordered_pairs_of_configuration_axis_mutants"
_CONFIGURATION_AXIS = "configuration"
_ATOMIC_FORM = "ATOMIC"
_T = TypeVar("_T")


class MutationCompositionError(ValueError):
    """ステップ20資産または実行結果の契約違反を表す。"""


@dataclass(frozen=True, slots=True)
class TwoFactorInteraction:
    """構成変異2件の非順序相互作用を表す。"""

    interaction_id: str
    factor_mutant_ids: tuple[str, str]
    expected_drift_outcome: str
    runtime_test_owner_id: str
    activated_cut_set_ids: tuple[str, ...]
    expected_attack_established: bool


@dataclass(frozen=True, slots=True)
class MinimalCutSet:
    """一つの攻撃目標を成立させる最小変異集合を表す。"""

    cut_set_id: str
    attack_goal_id: str
    mutant_ids: frozenset[str]
    single_mutation_sufficient: bool


@dataclass(frozen=True, slots=True)
class McdcPair:
    """一条件だけを反転するMC/DC入力対を表す。"""

    decision_id: str
    decision_form: str
    condition_ids: tuple[str, ...]
    condition_id: str
    test_ids: tuple[str, str]
    input_a: tuple[bool, ...]
    input_b: tuple[bool, ...]
    observed_results: tuple[bool, bool]


@dataclass(frozen=True, slots=True)
class Step20Catalog:
    """相互作用・cut set・MC/DCの閉じた実行母集合を保持する。"""

    mutation_catalog: MutationCatalog
    interactions: tuple[TwoFactorInteraction, ...]
    interaction_by_id: Mapping[str, TwoFactorInteraction]
    cut_sets: tuple[MinimalCutSet, ...]
    cut_set_by_id: Mapping[str, MinimalCutSet]
    mcdc_pairs: tuple[McdcPair, ...]
    mcdc_decision_ids: frozenset[str]


@dataclass(frozen=True, slots=True)
class Step20Selection:
    """実機の個別実行で選択する資産IDを保持する。"""

    interaction_id: str | None
    cut_set_id: str | None
    mcdc_decision_id: str | None

    @property
    def filtered(self) -> bool:
        """いずれかの個別IDが指定されたかを返す。"""
        return any(
            value is not None
            for value in (
                self.interaction_id,
                self.cut_set_id,
                self.mcdc_decision_id,
            )
        )


@dataclass(frozen=True, slots=True)
class InteractionExecution:
    """2因子の静的driftと攻撃成立の実行結果を保持する。"""

    interaction_id: str
    applied_factor_mutant_ids: tuple[str, str]
    drift_outcome: str
    attack_established: bool


@dataclass(frozen=True, slots=True)
class CutSetExecution:
    """cut set全体と各1要素除去の攻撃成立結果を保持する。"""

    cut_set_id: str
    full_set_established: bool
    removal_results: Mapping[str, bool]


@dataclass(frozen=True, slots=True)
class McdcPairExecution:
    """MC/DCテストID対を実行した判定結果を保持する。"""

    decision_id: str
    condition_id: str
    test_ids: tuple[str, str]
    actual_results: tuple[bool, bool]


@dataclass(frozen=True, slots=True)
class Step20ExecutionResult:
    """選択範囲の三種の実行結果を独立に保持する。"""

    interactions: tuple[InteractionExecution, ...]
    cut_sets: tuple[CutSetExecution, ...]
    mcdc_pairs: tuple[McdcPairExecution, ...]


@dataclass(frozen=True, slots=True)
class Step20Failure:
    """実機で原因を一意に特定する機械可読な失敗を表す。"""

    execution_kind: str
    execution_id: str
    error: str

    def to_json(self) -> str:
        """安定キー順のJSON Lines 1行を返す。"""
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)


class Step20BatchError(AssertionError):
    """全件継続後に残ったステップ20の失敗を表す。"""

    def __init__(self, failures: tuple[Step20Failure, ...]) -> None:
        """失敗を保持して例外本文にもJSON Linesを載せる。"""
        self.failures = failures
        lines = "\n".join(failure.to_json() for failure in failures)
        super().__init__(f"mutation-step20-failures-jsonl:\n{lines}")


McdcExecutor = Callable[[Sequence[bool]], bool]


def _mcdc_atomic(values: Sequence[bool]) -> bool:
    """単一条件をそのまま判定する。"""
    if len(values) != 1:
        raise MutationCompositionError("ATOMIC判定の入力数が1でない")
    return values[0]


def _mcdc_and(values: Sequence[bool]) -> bool:
    """全条件の論理積を判定する。"""
    if len(values) < 2:
        raise MutationCompositionError("AND判定の入力数が2未満")
    return all(values)


def _mcdc_or(values: Sequence[bool]) -> bool:
    """全条件の論理和を判定する。"""
    if len(values) < 2:
        raise MutationCompositionError("OR判定の入力数が2未満")
    return any(values)


def _mcdc_not(values: Sequence[bool]) -> bool:
    """単一条件の否定を判定する。"""
    if len(values) != 1:
        raise MutationCompositionError("NOT判定の入力数が1でない")
    return not values[0]


def _mcdc_case(values: Sequence[bool]) -> bool:
    """表駆動CASE相当の管理者要求分岐を判定する。"""
    if len(values) != 2:
        raise MutationCompositionError("CASE判定の入力数が2でない")
    requirement_applies, required_branch_allows = values
    return not requirement_applies or required_branch_allows


_MCDC_EXECUTORS: Final[Mapping[str, McdcExecutor]] = {
    _ATOMIC_FORM: _mcdc_atomic,
    "AND": _mcdc_and,
    "OR": _mcdc_or,
    "NOT": _mcdc_not,
    "CASE": _mcdc_case,
}


def _expect_object(value: object, label: str) -> dict[str, object]:
    """JSON objectを型確認して返す。"""
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise MutationCompositionError(f"{label}がobjectでない")
    return value


def _expect_rows(value: object, label: str) -> tuple[dict[str, object], ...]:
    """JSON object配列を型確認して返す。"""
    if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
        raise MutationCompositionError(f"{label}がobject配列でない")
    return tuple(row for row in value if isinstance(row, dict))


def _expect_keys(row: dict[str, object], keys: set[str], label: str) -> None:
    """JSON行のキーをexact-set照合する。"""
    if set(row) != keys:
        raise MutationCompositionError(f"{label}のkey集合が不正")


def _text(value: object, label: str) -> str:
    """空でない文字列を返す。"""
    if not isinstance(value, str) or not value:
        raise MutationCompositionError(f"{label}が空でない文字列でない")
    return value


def _string_tuple(value: object, label: str) -> tuple[str, ...]:
    """重複のない文字列配列を返す。"""
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item for item in value
    ):
        raise MutationCompositionError(f"{label}が文字列配列でない")
    result = tuple(value)
    if len(result) != len(set(result)):
        raise MutationCompositionError(f"{label}に重複がある")
    return result


def _bool_tuple(value: object, label: str) -> tuple[bool, ...]:
    """真偽値配列を返す。"""
    if not isinstance(value, list) or not all(type(item) is bool for item in value):
        raise MutationCompositionError(f"{label}がboolean配列でない")
    return tuple(value)


def _only(rows: Iterable[_T], label: str) -> _T:
    """一意な行を返す。"""
    values = tuple(rows)
    if len(values) != 1:
        raise MutationCompositionError(f"{label}を一意に導出できない")
    return values[0]


def _derived_configuration_pairs(
    mutation_catalog: MutationCatalog,
    factor_count: int,
) -> tuple[tuple[str, str], ...]:
    """configuration軸から非順序の2因子母集合を生成する。"""
    if factor_count != 2:
        raise MutationCompositionError("2因子scopeのfactor_countが2でない")
    config_ids = sorted(
        spec.mutant_id
        for spec in mutation_catalog.mutants
        if spec.axis == _CONFIGURATION_AXIS
    )
    if len(config_ids) < factor_count:
        raise MutationCompositionError("configuration変異が2因子を作れない")
    return tuple(combinations(config_ids, factor_count))


def _parse_cut_sets(
    attack_tree: dict[str, object],
    mutation_catalog: MutationCatalog,
) -> tuple[tuple[MinimalCutSet, ...], Mapping[str, MinimalCutSet]]:
    """攻撃目標と最小cut setを閉じた集合として読む。"""
    goal_rows = _expect_rows(attack_tree.get("attack_goals"), "attack_goals")
    goal_ids: set[str] = set()
    for index, row in enumerate(goal_rows):
        label = f"attack_goals[{index}]"
        _expect_keys(row, {"attack_goal_id", "logic"}, label)
        goal_id = _text(row.get("attack_goal_id"), f"{label}.attack_goal_id")
        if row.get("logic") != "OR_OF_MINIMAL_CUT_SETS" or goal_id in goal_ids:
            raise MutationCompositionError(f"{label}が一意なOR攻撃目標でない")
        goal_ids.add(goal_id)

    cut_sets: list[MinimalCutSet] = []
    for index, row in enumerate(
        _expect_rows(attack_tree.get("minimal_cut_sets"), "minimal_cut_sets")
    ):
        label = f"minimal_cut_sets[{index}]"
        _expect_keys(
            row,
            {
                "cut_set_id",
                "attack_goal_id",
                "mutant_ids",
                "minimal",
                "single_mutation_sufficient",
            },
            label,
        )
        cut_set_id = _text(row.get("cut_set_id"), f"{label}.cut_set_id")
        goal_id = _text(row.get("attack_goal_id"), f"{label}.attack_goal_id")
        mutant_ids = frozenset(_string_tuple(row.get("mutant_ids"), f"{label}.mutants"))
        if not mutant_ids:
            raise MutationCompositionError(f"{cut_set_id}: cut setが空")
        unknown = mutant_ids - set(mutation_catalog.mutant_by_id)
        if unknown:
            raise MutationCompositionError(
                f"{cut_set_id}: 未知mutant参照: {sorted(unknown)}"
            )
        if goal_id not in goal_ids:
            raise MutationCompositionError(f"{cut_set_id}: 未知attack goal")
        if row.get("minimal") is not True:
            raise MutationCompositionError(f"{cut_set_id}: minimalでない")
        singleton = len(mutant_ids) == 1
        if row.get("single_mutation_sufficient") is not singleton:
            raise MutationCompositionError(
                f"{cut_set_id}: single_mutation_sufficientが集合サイズと不一致"
            )
        cut_sets.append(
            MinimalCutSet(
                cut_set_id=cut_set_id,
                attack_goal_id=goal_id,
                mutant_ids=mutant_ids,
                single_mutation_sufficient=singleton,
            )
        )
    cut_by_id = {cut.cut_set_id: cut for cut in cut_sets}
    if len(cut_by_id) != len(cut_sets):
        raise MutationCompositionError("cut_set_idが重複している")
    if {cut.attack_goal_id for cut in cut_sets} != goal_ids:
        raise MutationCompositionError("attack goalとcut setがexact-set不一致")
    by_goal: defaultdict[str, list[frozenset[str]]] = defaultdict(list)
    for cut in cut_sets:
        by_goal[cut.attack_goal_id].append(cut.mutant_ids)
    if any(
        left < right
        for goal_sets in by_goal.values()
        for left in goal_sets
        for right in goal_sets
    ):
        raise MutationCompositionError("真部分集合を持つcut setがminimalを名乗っている")
    return tuple(cut_sets), MappingProxyType(cut_by_id)


def _parse_interactions(
    claim_map: dict[str, object],
    attack_tree: dict[str, object],
    mutation_catalog: MutationCatalog,
    cut_by_id: Mapping[str, MinimalCutSet],
) -> tuple[tuple[TwoFactorInteraction, ...], Mapping[str, TwoFactorInteraction]]:
    """構成軸由来の全非順序対と二つの資産をexact-set照合する。"""
    scope = _expect_object(attack_tree.get("two_factor_scope"), "two_factor_scope")
    _expect_keys(scope, {"population_rule", "factor_count"}, "two_factor_scope")
    if scope.get("population_rule") != _PAIR_POPULATION_RULE:
        raise MutationCompositionError("2因子母集合の導出規則が未実装")
    factor_count = scope.get("factor_count")
    if type(factor_count) is not int:
        raise MutationCompositionError("factor_countが整数でない")
    expected_pairs = frozenset(
        _derived_configuration_pairs(mutation_catalog, factor_count)
    )
    config_ids = {
        spec.mutant_id
        for spec in mutation_catalog.mutants
        if spec.axis == _CONFIGURATION_AXIS
    }

    claim_rows = _expect_rows(
        claim_map.get("two_factor_interactions"), "claim two_factor_interactions"
    )
    provisional: dict[str, tuple[tuple[str, str], str, str]] = {}
    actual_pairs: list[tuple[str, str]] = []
    runtime_owner_ids: list[str] = []
    for index, row in enumerate(claim_rows):
        label = f"claim two_factor_interactions[{index}]"
        _expect_keys(
            row,
            {
                "interaction_id",
                "factor_mutant_ids",
                "expected_drift_outcome",
                "runtime_test_owner",
            },
            label,
        )
        factors = _string_tuple(row.get("factor_mutant_ids"), f"{label}.factors")
        if len(factors) != factor_count or factors != tuple(sorted(factors)):
            raise MutationCompositionError(f"{label}: 因子が正規化された2件でない")
        pair = (factors[0], factors[1])
        if set(pair) - config_ids:
            raise MutationCompositionError(f"{label}: configuration軸外の因子がある")
        interaction_id = _text(row.get("interaction_id"), f"{label}.interaction_id")
        if interaction_id != f"PAIR:{pair[0]}+{pair[1]}":
            raise MutationCompositionError(f"{label}: interaction_idが因子から導出不能")
        if row.get("expected_drift_outcome") != "red":
            raise MutationCompositionError(f"{interaction_id}: drift期待値がredでない")
        owner = _expect_object(row.get("runtime_test_owner"), f"{label}.runtime owner")
        _expect_keys(owner, {"id", "status"}, f"{label}.runtime owner")
        owner_id = _text(owner.get("id"), f"{label}.runtime owner.id")
        _text(owner.get("status"), f"{label}.runtime owner.status")
        if interaction_id in provisional:
            raise MutationCompositionError(f"interaction_idが重複: {interaction_id}")
        provisional[interaction_id] = (pair, "red", owner_id)
        actual_pairs.append(pair)
        runtime_owner_ids.append(owner_id)
    if frozenset(actual_pairs) != expected_pairs or len(actual_pairs) != len(
        expected_pairs
    ):
        raise MutationCompositionError("claim mapの2因子が導出母集合とexact-set不一致")
    if len(runtime_owner_ids) != len(set(runtime_owner_ids)):
        raise MutationCompositionError("interaction runtime test ownerが一意でない")

    attack_rows = _expect_rows(
        attack_tree.get("two_factor_interactions"), "attack two_factor_interactions"
    )
    attack_by_id: dict[str, tuple[tuple[str, ...], bool]] = {}
    attack_pairs: list[tuple[str, str]] = []
    for index, row in enumerate(attack_rows):
        label = f"attack two_factor_interactions[{index}]"
        _expect_keys(
            row,
            {
                "interaction_id",
                "factor_mutant_ids",
                "activated_cut_set_ids",
                "expected_attack_established",
            },
            label,
        )
        factors = _string_tuple(row.get("factor_mutant_ids"), f"{label}.factors")
        if len(factors) != factor_count or factors != tuple(sorted(factors)):
            raise MutationCompositionError(f"{label}: 因子が正規化された2件でない")
        pair = (factors[0], factors[1])
        interaction_id = _text(row.get("interaction_id"), f"{label}.interaction_id")
        if provisional.get(interaction_id, (None,))[0] != pair:
            raise MutationCompositionError(f"{interaction_id}: 二資産の因子が不一致")
        factor_set = frozenset(pair)
        derived_activated = tuple(
            sorted(
                cut.cut_set_id
                for cut in cut_by_id.values()
                if cut.mutant_ids <= factor_set
            )
        )
        declared_activated = _string_tuple(
            row.get("activated_cut_set_ids"), f"{label}.activated"
        )
        if declared_activated != derived_activated:
            raise MutationCompositionError(f"{interaction_id}: cut set活性化が不一致")
        established = row.get("expected_attack_established")
        if type(established) is not bool or established is not bool(derived_activated):
            raise MutationCompositionError(f"{interaction_id}: attack成立期待が不一致")
        if interaction_id in attack_by_id:
            raise MutationCompositionError(
                f"attack interactionが重複: {interaction_id}"
            )
        attack_by_id[interaction_id] = (derived_activated, established)
        attack_pairs.append(pair)
    if (
        frozenset(attack_pairs) != expected_pairs
        or len(attack_pairs) != len(expected_pairs)
        or set(attack_by_id) != set(provisional)
    ):
        raise MutationCompositionError("attack treeの2因子がexact-set不一致")

    interactions = tuple(
        TwoFactorInteraction(
            interaction_id=interaction_id,
            factor_mutant_ids=pair,
            expected_drift_outcome=drift,
            runtime_test_owner_id=owner_id,
            activated_cut_set_ids=attack_by_id[interaction_id][0],
            expected_attack_established=attack_by_id[interaction_id][1],
        )
        for interaction_id, (pair, drift, owner_id) in provisional.items()
    )
    return tuple(interactions), MappingProxyType(
        {row.interaction_id: row for row in interactions}
    )


def _parse_mcdc_pairs(
    mcdc_map: dict[str, object], claim_map: dict[str, object]
) -> tuple[tuple[McdcPair, ...], frozenset[str]]:
    """写像から条件ごとの実行可能なMC/DCテスト対を読む。"""
    _expect_keys(
        mcdc_map,
        {"schema_version", "asset_kind", "sources", "decisions"},
        "mcdc-map",
    )
    pairs: list[McdcPair] = []
    decision_ids: list[str] = []
    all_test_ids: list[str] = []
    declared_forms: set[str] = set()
    for decision_index, decision in enumerate(
        _expect_rows(mcdc_map.get("decisions"), "mcdc-map.decisions")
    ):
        label = f"mcdc-map.decisions[{decision_index}]"
        _expect_keys(
            decision,
            {
                "decision_id",
                "source",
                "decision_form",
                "conditions",
                "independence_pairs",
            },
            label,
        )
        decision_id = _text(decision.get("decision_id"), f"{label}.decision_id")
        decision_form = _text(decision.get("decision_form"), f"{label}.decision_form")
        condition_rows = _expect_rows(decision.get("conditions"), f"{label}.conditions")
        condition_ids = tuple(
            _text(row.get("condition_id"), f"{label}.conditions[].condition_id")
            for row in condition_rows
        )
        if not condition_ids or len(condition_ids) != len(set(condition_ids)):
            raise MutationCompositionError(f"{decision_id}: conditionが空または重複")
        pair_rows = _expect_rows(
            decision.get("independence_pairs"), f"{label}.independence_pairs"
        )
        pair_condition_ids: list[str] = []
        for pair_index, pair in enumerate(pair_rows):
            pair_label = f"{label}.independence_pairs[{pair_index}]"
            _expect_keys(
                pair,
                {
                    "condition_id",
                    "test_ids",
                    "input_a",
                    "input_b",
                    "observed_results",
                },
                pair_label,
            )
            condition_id = _text(pair.get("condition_id"), f"{pair_label}.condition")
            test_ids = _string_tuple(pair.get("test_ids"), f"{pair_label}.test_ids")
            if len(test_ids) != 2:
                raise MutationCompositionError(f"{pair_label}: test IDが2件でない")
            input_a = _bool_tuple(pair.get("input_a"), f"{pair_label}.input_a")
            input_b = _bool_tuple(pair.get("input_b"), f"{pair_label}.input_b")
            observed = _bool_tuple(
                pair.get("observed_results"), f"{pair_label}.observed_results"
            )
            if len(observed) != 2:
                raise MutationCompositionError(f"{pair_label}: 観測結果が2件でない")
            pairs.append(
                McdcPair(
                    decision_id=decision_id,
                    decision_form=decision_form,
                    condition_ids=condition_ids,
                    condition_id=condition_id,
                    test_ids=(test_ids[0], test_ids[1]),
                    input_a=input_a,
                    input_b=input_b,
                    observed_results=(observed[0], observed[1]),
                )
            )
            pair_condition_ids.append(condition_id)
            all_test_ids.extend(test_ids)
        if Counter(pair_condition_ids) != Counter(condition_ids):
            raise MutationCompositionError(
                f"{decision_id}: conditionとpairがexact-set不一致"
            )
        decision_ids.append(decision_id)
        declared_forms.add(decision_form)
    if len(decision_ids) != len(set(decision_ids)):
        raise MutationCompositionError("MC/DC decision IDが重複している")
    if len(all_test_ids) != len(set(all_test_ids)):
        raise MutationCompositionError("MC/DC test IDが写像全体で重複している")
    required_forms = frozenset(
        _string_tuple(claim_map.get("mcdc_decision_forms"), "mcdc_decision_forms")
    ) | {_ATOMIC_FORM}
    if declared_forms != required_forms:
        raise MutationCompositionError("MC/DC判定形が資産語彙とexact-set不一致")
    _bind_exact_implementations(
        frozenset(declared_forms), _MCDC_EXECUTORS, "MC/DC execution form"
    )
    return tuple(pairs), frozenset(decision_ids)


def load_step20_catalog_data(
    claim_map_raw: object,
    attack_tree_raw: object,
    mcdc_map_raw: object,
    mutation_catalog: MutationCatalog,
) -> Step20Catalog:
    """三資産と構成軸からステップ20の実行母集合を構築する。"""
    claim_map = _expect_object(claim_map_raw, "claim-mutant-map")
    attack_tree = _expect_object(attack_tree_raw, "attack-tree")
    mcdc_map = _expect_object(mcdc_map_raw, "mcdc-map")
    cut_sets, cut_by_id = _parse_cut_sets(attack_tree, mutation_catalog)
    interactions, interaction_by_id = _parse_interactions(
        claim_map, attack_tree, mutation_catalog, cut_by_id
    )
    mcdc_pairs, decision_ids = _parse_mcdc_pairs(mcdc_map, claim_map)
    return Step20Catalog(
        mutation_catalog=mutation_catalog,
        interactions=interactions,
        interaction_by_id=interaction_by_id,
        cut_sets=cut_sets,
        cut_set_by_id=cut_by_id,
        mcdc_pairs=mcdc_pairs,
        mcdc_decision_ids=decision_ids,
    )


def load_step20_catalog(root: Path = REPOSITORY_ROOT) -> Step20Catalog:
    """リポジトリ資産からステップ20の実行母集合を読む。"""
    resolved = root.resolve()
    return load_step20_catalog_data(
        _read_json_object(resolved / "contracts/authz/claim-mutant-map.json"),
        _read_json_object(resolved / "contracts/authz/attack-tree.json"),
        _read_json_object(resolved / "contracts/authz/mcdc-map.json"),
        load_mutation_catalog(resolved / "contracts/authz/claim-mutant-map.json"),
    )


def step20_selection_from_environment(
    environment: Mapping[str, str],
) -> Step20Selection:
    """実機の三種の個別実行IDを環境変数から読む。"""
    return Step20Selection(
        interaction_id=environment.get(INTERACTION_FILTER_ENV) or None,
        cut_set_id=environment.get(CUT_SET_FILTER_ENV) or None,
        mcdc_decision_id=environment.get(MCDC_DECISION_FILTER_ENV) or None,
    )


def _selected_rows(
    rows: tuple[_T, ...],
    row_by_id: Mapping[str, _T],
    selected_id: str | None,
    *,
    run_unfiltered: bool,
    label: str,
) -> tuple[_T, ...]:
    """閉じたID語彙で全件または1件を選択する。"""
    if selected_id is None:
        return rows if run_unfiltered else ()
    try:
        return (row_by_id[selected_id],)
    except KeyError as error:
        raise MutationCompositionError(f"未知の{label}: {selected_id}") from error


def select_step20_work(
    catalog: Step20Catalog,
    selection: Step20Selection,
) -> tuple[
    tuple[TwoFactorInteraction, ...], tuple[MinimalCutSet, ...], tuple[McdcPair, ...]
]:
    """三種の実行対象を個別IDまたは全件として選択する。"""
    run_all = not selection.filtered
    interactions = _selected_rows(
        catalog.interactions,
        catalog.interaction_by_id,
        selection.interaction_id,
        run_unfiltered=run_all,
        label="interaction_id",
    )
    cut_sets = _selected_rows(
        catalog.cut_sets,
        catalog.cut_set_by_id,
        selection.cut_set_id,
        run_unfiltered=run_all,
        label="cut_set_id",
    )
    if selection.mcdc_decision_id is None:
        mcdc_pairs = catalog.mcdc_pairs if run_all else ()
    else:
        if selection.mcdc_decision_id not in catalog.mcdc_decision_ids:
            raise MutationCompositionError(
                f"未知のMC/DC decision_id: {selection.mcdc_decision_id}"
            )
        mcdc_pairs = tuple(
            pair
            for pair in catalog.mcdc_pairs
            if pair.decision_id == selection.mcdc_decision_id
        )
    return interactions, cut_sets, mcdc_pairs


def _canonical_json(value: object) -> str:
    """一時資産の変化確認用にJSONを正規化する。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def execute_interaction(
    catalog: Step20Catalog,
    interaction: TwoFactorInteraction,
) -> InteractionExecution:
    """2構成変異を同じ事前構成へ合成してschema driftを実行する。"""
    mutated = _read_json_object(DDL_ELEMENTS_PATH)
    for mutant_id in interaction.factor_mutant_ids:
        spec = catalog.mutation_catalog.mutant_by_id[mutant_id]
        if spec.axis != _CONFIGURATION_AXIS:
            raise MutationCompositionError(
                f"{interaction.interaction_id}: 構成軸外因子"
            )
        before = _canonical_json(mutated)
        mutated = _mutate_ddl_configuration(spec, mutated)
        if _canonical_json(mutated) == before:
            raise MutationCompositionError(f"{mutant_id}: 構成変異が適用されていない")
    try:
        _CHECKER.validate_oracle_asset_seal(
            mutated,
            "contracts/authz/ddl-elements.json",
            _read_json_object(ORACLE_SEAL_PATH),
        )
    except _CHECKER.CatalogError:
        drift_outcome = "red"
    else:
        drift_outcome = "green"
    if drift_outcome != interaction.expected_drift_outcome:
        raise MutationCompositionError(
            f"{interaction.interaction_id}: schema driftが{drift_outcome}"
        )
    attack_established = bool(interaction.activated_cut_set_ids)
    if attack_established is not interaction.expected_attack_established:
        raise MutationCompositionError(
            f"{interaction.interaction_id}: attack成立結果が期待と不一致"
        )
    return InteractionExecution(
        interaction_id=interaction.interaction_id,
        applied_factor_mutant_ids=interaction.factor_mutant_ids,
        drift_outcome=drift_outcome,
        attack_established=attack_established,
    )


def _attack_goal_established(
    catalog: Step20Catalog,
    attack_goal_id: str,
    active_mutant_ids: frozenset[str],
) -> bool:
    """同じ攻撃目標のいずれかのcut setが全て活性なら成立とする。"""
    return any(
        cut.attack_goal_id == attack_goal_id and cut.mutant_ids <= active_mutant_ids
        for cut in catalog.cut_sets
    )


def execute_cut_set(
    catalog: Step20Catalog,
    cut_set: MinimalCutSet,
) -> CutSetExecution:
    """Cut set全体の成立と全1要素除去後の不成立を実行する。"""
    full = _attack_goal_established(catalog, cut_set.attack_goal_id, cut_set.mutant_ids)
    removal_results = {
        mutant_id: _attack_goal_established(
            catalog,
            cut_set.attack_goal_id,
            cut_set.mutant_ids - {mutant_id},
        )
        for mutant_id in sorted(cut_set.mutant_ids)
    }
    if not full:
        raise MutationCompositionError(f"{cut_set.cut_set_id}: 完全集合で攻撃不成立")
    established_after_removal = [
        mutant_id for mutant_id, established in removal_results.items() if established
    ]
    if established_after_removal:
        raise MutationCompositionError(
            f"{cut_set.cut_set_id}: 1要素除去後も成立: {established_after_removal}"
        )
    return CutSetExecution(
        cut_set_id=cut_set.cut_set_id,
        full_set_established=full,
        removal_results=MappingProxyType(removal_results),
    )


def execute_mcdc_pair(pair: McdcPair) -> McdcPairExecution:
    """写像の二つのtest IDを判定実装へ投入して独立影響を観測する。"""
    if len(pair.input_a) != len(pair.condition_ids) or len(pair.input_b) != len(
        pair.condition_ids
    ):
        raise MutationCompositionError(
            f"{pair.decision_id}/{pair.condition_id}: 入力長が条件数と不一致"
        )
    try:
        target_index = pair.condition_ids.index(pair.condition_id)
    except ValueError as error:
        raise MutationCompositionError(
            f"{pair.decision_id}/{pair.condition_id}: 対象条件が存在しない"
        ) from error
    changed = {
        index
        for index, (left, right) in enumerate(
            zip(pair.input_a, pair.input_b, strict=True)
        )
        if left is not right
    }
    if changed != {target_index}:
        raise MutationCompositionError(
            f"{pair.decision_id}/{pair.condition_id}: 対象条件だけの反転でない"
        )
    executor = _MCDC_EXECUTORS[pair.decision_form]
    actual = (executor(pair.input_a), executor(pair.input_b))
    if actual != pair.observed_results:
        raise MutationCompositionError(
            f"{pair.decision_id}/{pair.condition_id}: 実行結果が写像の観測値と不一致"
        )
    if actual[0] is actual[1]:
        raise MutationCompositionError(
            f"{pair.decision_id}/{pair.condition_id}: 判定結果が反転しない"
        )
    return McdcPairExecution(
        decision_id=pair.decision_id,
        condition_id=pair.condition_id,
        test_ids=pair.test_ids,
        actual_results=actual,
    )


def run_step20(
    catalog: Step20Catalog,
    selection: Step20Selection,
) -> Step20ExecutionResult:
    """選択した三種を全件継続し、失敗をJSON Linesでまとめる。"""
    interactions, cut_sets, mcdc_pairs = select_step20_work(catalog, selection)
    interaction_results: list[InteractionExecution] = []
    cut_results: list[CutSetExecution] = []
    mcdc_results: list[McdcPairExecution] = []
    failures: list[Step20Failure] = []
    for interaction in interactions:
        try:
            interaction_results.append(execute_interaction(catalog, interaction))
        except Exception as error:
            failures.append(
                Step20Failure(
                    execution_kind="interaction",
                    execution_id=interaction.interaction_id,
                    error=f"{type(error).__name__}: {error}",
                )
            )
    for cut_set in cut_sets:
        try:
            cut_results.append(execute_cut_set(catalog, cut_set))
        except Exception as error:
            failures.append(
                Step20Failure(
                    execution_kind="cut_set",
                    execution_id=cut_set.cut_set_id,
                    error=f"{type(error).__name__}: {error}",
                )
            )
    for pair in mcdc_pairs:
        try:
            mcdc_results.append(execute_mcdc_pair(pair))
        except Exception as error:
            failures.append(
                Step20Failure(
                    execution_kind="mcdc_pair",
                    execution_id=f"{pair.decision_id}/{pair.condition_id}",
                    error=f"{type(error).__name__}: {error}",
                )
            )
    if failures:
        raise Step20BatchError(tuple(failures))
    return Step20ExecutionResult(
        interactions=tuple(interaction_results),
        cut_sets=tuple(cut_results),
        mcdc_pairs=tuple(mcdc_results),
    )


def _frozen_oracle_paths_from_seal(seal: dict[str, object]) -> tuple[str, ...]:
    """sealの入力・封印行とseal自身から凍結パスを導出する。"""
    paths = [
        _text(row.get("path"), "frozen asset path")
        for key in ("input_assets", "sealed_assets")
        for row in _expect_rows(seal.get(key), f"oracle seal.{key}")
    ]
    paths.append(ORACLE_SEAL_RELATIVE_PATH)
    if len(paths) != len(set(paths)):
        raise MutationCompositionError("凍結パスが重複している")
    return tuple(paths)


def _oracle_seal_at_revision(root: Path, revision: str) -> dict[str, object]:
    """固定revisionにあるoracle sealを読み取る。"""
    result = subprocess.run(
        ["git", "show", f"{revision}:{ORACLE_SEAL_RELATIVE_PATH}"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise MutationCompositionError(
            f"基準版のoracle sealを取得できない: {result.stderr.strip()}"
        )
    try:
        seal = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise MutationCompositionError("基準版のoracle sealが不正なJSON") from error
    if not isinstance(seal, dict):
        raise MutationCompositionError("基準版のoracle sealがオブジェクトでない")
    return seal


def _json_object_at_revision(
    root: Path,
    revision: str,
    relative_path: str,
) -> dict[str, object]:
    """指定revisionにあるJSONオブジェクトを読み取る。"""
    result = subprocess.run(
        ["git", "show", f"{revision}:{relative_path}"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise MutationCompositionError(
            f"基準版のJSONを取得できない: {relative_path}: {result.stderr.strip()}"
        )
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise MutationCompositionError(
            f"基準版のJSONが不正: {relative_path}"
        ) from error
    return _expect_object(value, f"base asset {relative_path}")


def frozen_oracle_paths(
    root: Path = REPOSITORY_ROOT,
    base_ref: str | None = None,
) -> tuple[str, ...]:
    """現在または固定revisionのsealから凍結パスを導出する。"""
    resolved = root.resolve()
    seal = (
        _read_json_object(resolved / ORACLE_SEAL_RELATIVE_PATH)
        if base_ref is None
        else _oracle_seal_at_revision(resolved, base_ref)
    )
    return _frozen_oracle_paths_from_seal(seal)


def _json_copy(value: dict[str, object], label: str) -> dict[str, object]:
    """JSONオブジェクトを参照共有なしで複製する。"""
    return _expect_object(json.loads(json.dumps(value)), label)


def _oracle_meaning_body(
    asset: dict[str, object],
    label: str,
) -> dict[str, object]:
    """oracle資産から可動ポインタだけを除いた意味本文を返す。"""
    body = _json_copy(asset, label)
    context = _expect_object(body.get("oracle_context"), f"{label}.oracle_context")
    _text(context.pop("oracle_commit", None), f"{label}.oracle_context.oracle_commit")
    return body


def _expected_step2_meaning_body(
    relative_path: str,
    base: dict[str, object],
) -> dict[str, object]:
    """固定基準へ承認済みの2資産の意味変更だけを適用する。"""
    expected = _oracle_meaning_body(base, f"base asset {relative_path}")
    if relative_path == _BOUNDARY_PROPOSAL_RELATIVE_PATH:
        expected["proposal_status"] = "tsk_235_confirmed"
        boundaries = _expect_rows(expected.get("boundaries"), "base boundaries")
        boundaries[0]["aggregation_owner_task_id"] = (
            "3d993b75-e687-818d-8cb8-ec57508e73e0"
        )
        boundaries[1].pop("aggregation_owner_task_id", None)
        deferred = _expect_object(
            expected.get("deferred_equivalence_contract"),
            "base deferred_equivalence_contract",
        )
        deferred["owner_task_id"] = "3d993b75-e687-818d-8cb8-ec57508e73e0"
        reviews = _expect_rows(
            expected.get("pending_human_reviews"),
            "base pending_human_reviews",
        )
        reviews[0]["status"] = "human_decided"
        reviews[1]["status"] = "human_decided"
    elif relative_path == _DDL_ELEMENTS_RELATIVE_PATH:
        scope = _expect_object(expected.get("scope"), "base DDL scope")
        scope["status"] = "verified_probe_configuration"
        scope["second_group_approval_required"] = False
    return expected


def _sealed_rows_by_path(
    seal: dict[str, object],
    label: str,
) -> dict[str, dict[str, object]]:
    """sealed_assetsを重複を許さないpath写像へ変換する。"""
    result: dict[str, dict[str, object]] = {}
    for row in _expect_rows(seal.get("sealed_assets"), f"{label}.sealed_assets"):
        path = _text(row.get("path"), f"{label}.sealed_assets.path")
        if path in result:
            raise MutationCompositionError(f"{label}.sealed_assets.pathが重複")
        result[path] = row
    return result


def _input_rows_by_path(
    seal: dict[str, object],
    label: str,
) -> dict[str, dict[str, object]]:
    """input_assetsを重複を許さないpath写像へ変換する。"""
    result: dict[str, dict[str, object]] = {}
    for row in _expect_rows(seal.get("input_assets"), f"{label}.input_assets"):
        path = _text(row.get("path"), f"{label}.input_assets.path")
        if path in result:
            raise MutationCompositionError(f"{label}.input_assets.pathが重複")
        result[path] = row
    return result


def _oracle_seal_meaning_body(
    seal: dict[str, object],
    label: str,
) -> dict[str, object]:
    """sealから入力ポインタとポインタ由来digestだけを除いて返す。"""
    body = _json_copy(seal, label)
    _text(body.pop("oracle_commit", None), f"{label}.oracle_commit")
    for row in _expect_rows(body.get("input_assets"), f"{label}.input_assets"):
        _text(
            row.pop("git_blob_digest", None),
            f"{label}.input_assets.git_blob_digest",
        )
    for row in _expect_rows(body.get("sealed_assets"), f"{label}.sealed_assets"):
        _text(
            row.pop("canonical_sha256", None),
            f"{label}.sealed_assets.canonical_sha256",
        )
    return body


def _git_object_id(root: Path, arguments: list[str], label: str) -> str:
    """Gitコマンドが返した単一object IDを取得する。"""
    result = subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise MutationCompositionError(
            f"{label}を取得できない: {result.stderr.strip()}"
        )
    return _text(result.stdout.strip(), label)


def _verify_oracle_input_assets(
    root: Path,
    seal: dict[str, object],
) -> None:
    """入力資産の作業ツリー・基準commit・sealのblobを三者照合する。"""
    oracle_commit = _text(seal.get("oracle_commit"), "oracle seal.oracle_commit")
    for path, row in _input_rows_by_path(seal, "current oracle seal").items():
        recorded = _text(
            row.get("git_blob_digest"),
            f"current oracle seal.input_assets[{path}].git_blob_digest",
        )
        worktree = _git_object_id(
            root,
            ["hash-object", "--", path],
            f"作業ツリーのblob {path}",
        )
        baseline = _git_object_id(
            root,
            ["rev-parse", f"{oracle_commit}:{path}"],
            f"oracle commit上のblob {path}",
        )
        if worktree != baseline or baseline != recorded:
            raise MutationCompositionError(
                f"oracle入力blobが三者不一致: {path}: "
                f"worktree={worktree}, baseline={baseline}, seal={recorded}"
            )


def _canonical_sha256(value: object) -> str:
    """checkerと同じcanonical JSONのSHA-256を返す。"""
    return hashlib.sha256(_canonical_json(value).encode()).hexdigest()


def _verify_current_sealed_assets(
    root: Path,
    seal: dict[str, object],
) -> None:
    """封印6資産のポインタとraw canonical digestを現sealへ照合する。"""
    oracle_commit = _text(seal.get("oracle_commit"), "oracle seal.oracle_commit")
    for path, row in _sealed_rows_by_path(seal, "current oracle seal").items():
        asset = _read_json_object(root / path)
        context = _expect_object(asset.get("oracle_context"), f"{path}.oracle_context")
        if context.get("oracle_commit") != oracle_commit:
            raise MutationCompositionError(f"{path}: oracle_commitがsealと不一致")
        recorded = _text(
            row.get("canonical_sha256"),
            f"current oracle seal.sealed_assets[{path}].canonical_sha256",
        )
        if recorded != _canonical_sha256(asset):
            raise MutationCompositionError(f"{path}: canonical digestがsealと不一致")


def _changed_oracle_meaning_paths(
    root: Path,
    base_ref: str,
    current_seal: dict[str, object],
) -> frozenset[str]:
    """可動ポインタを除いて固定基準から意味が変わった資産を返す。"""
    current_paths = set(_sealed_rows_by_path(current_seal, "current oracle seal"))
    base_seal = _oracle_seal_at_revision(root, base_ref)
    base_paths = set(_sealed_rows_by_path(base_seal, "base oracle seal"))
    if current_paths != base_paths:
        raise MutationCompositionError("sealed_assets.path集合が基準版と不一致")
    changed: set[str] = set()
    for path in sorted(base_paths):
        base = _json_object_at_revision(root, base_ref, path)
        current = _read_json_object(root / path)
        current_body = _oracle_meaning_body(current, f"current asset {path}")
        if current_body != _oracle_meaning_body(base, f"base asset {path}"):
            changed.add(path)
        expected = _expected_step2_meaning_body(path, base)
        if current_body != expected:
            raise MutationCompositionError(f"{path}: 承認済みのoracle意味本文と不一致")
    return frozenset(changed)


def intentionally_changed_frozen_oracle_paths(
    root: Path = REPOSITORY_ROOT,
    base_ref: str = STEP2_BASE_REVISION,
) -> frozenset[str]:
    """可動ポインタを除いて基準版から意味が変わった資産を導出する。"""
    resolved = root.resolve()
    current_seal = _read_json_object(resolved / ORACLE_SEAL_RELATIVE_PATH)
    changed = _changed_oracle_meaning_paths(resolved, base_ref, current_seal)
    if changed != STEP2_CHANGED_CANONICAL_ASSET_PATHS:
        raise MutationCompositionError(
            "意味本文が変わった資産がステップ2の確定集合と不一致: "
            f"{tuple(sorted(changed))}"
        )
    return changed


def verify_frozen_oracle_unchanged(
    root: Path = REPOSITORY_ROOT,
    base_ref: str = STEP2_BASE_REVISION,
) -> None:
    """入力baselineの三者一致とoracle意味本文の固定を検査する。"""
    resolved = root.resolve()
    base_seal = _oracle_seal_at_revision(resolved, base_ref)
    current_seal = _read_json_object(resolved / ORACLE_SEAL_RELATIVE_PATH)
    if _oracle_seal_meaning_body(
        current_seal, "current oracle seal"
    ) != _oracle_seal_meaning_body(base_seal, "base oracle seal"):
        raise MutationCompositionError("oracle sealの意味本文が基準版と不一致")
    _verify_oracle_input_assets(resolved, current_seal)
    _verify_current_sealed_assets(resolved, current_seal)
    changed = _changed_oracle_meaning_paths(resolved, base_ref, current_seal)
    if changed != STEP2_CHANGED_CANONICAL_ASSET_PATHS:
        raise MutationCompositionError(
            "意味本文が変わった資産がステップ2の確定集合と不一致: "
            f"{tuple(sorted(changed))}"
        )
