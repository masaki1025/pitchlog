"""対象計算ごとに非等価変異の生存 0 を判定する変異エンジン。

言語別・表示系の演算子は後続ステップへ委ね、本モジュールは演算子と既存
3 層 runner を呼ぶ実行器の境界だけを定める。`ADR-003 D-11 変異テスト規則`
に従い、`(b)①` の hash 乖離だけによる kill は有効な kill 集合へ入れない。
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9._-]*$")


class MutationEngineError(Exception):
    """変異生成または対象計算単位の判定が不適合であることを表す。"""


class KillLayer(StrEnum):
    """変異を観測できる検査層の閉じた集合。"""

    VECTOR = "vector"
    PROPERTY_INVARIANT = "property-invariant"
    PROPERTY_EQUIVALENCE = "property-equivalence"
    B1_HASH = "b1-hash"


_PROPERTY_LAYERS = frozenset(
    {KillLayer.PROPERTY_INVARIANT, KillLayer.PROPERTY_EQUIVALENCE}
)


def _require_identifier(value: str, label: str) -> None:
    """識別子が空でなく閉じた文字種だけを使うことを検査する。"""
    if _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{label} が不正: {value}")


@dataclass(frozen=True, slots=True)
class SyntheticMutationTarget:
    """製品対象ではない固定の合成変異対象。

    Attributes:
        calculation: 対象計算 ID。
        target_id: 計算内で一意な合成対象 ID。
        source: 演算子へ渡す生成物または宣言の断片。
    """

    calculation: str
    target_id: str
    source: object

    def __post_init__(self) -> None:
        """対象計算と合成対象の ID を検査する。"""
        _require_identifier(self.calculation, "calculation ID")
        _require_identifier(self.target_id, "target ID")


@dataclass(frozen=True, slots=True)
class UnsupportedLocation:
    """演算子が変異できず黙って飛ばしてはならない一箇所。"""

    calculation: str
    target_id: str
    location_id: str
    operator_id: str
    reason: str

    def __post_init__(self) -> None:
        """未対応箇所を一意に報告できる形へ制限する。"""
        for label, value in (
            ("calculation ID", self.calculation),
            ("target ID", self.target_id),
            ("location ID", self.location_id),
            ("operator ID", self.operator_id),
        ):
            _require_identifier(value, label)
        if not self.reason:
            raise ValueError("未対応理由が空")


@dataclass(frozen=True, slots=True)
class Mutant:
    """一つの合成対象から生成された変異。

    Attributes:
        mutant_id: 全対象で一意な変異 ID。
        calculation: 帰属する対象計算 ID。
        target_id: 生成元の合成対象 ID。
        operator_id: 適用した演算子 ID。
        mutated: 演算子が実際に変更した値。
        equivalence_claimed: 演算子側による等価の自己申告。
    """

    mutant_id: str
    calculation: str
    target_id: str
    operator_id: str
    mutated: object
    equivalence_claimed: bool = False

    def __post_init__(self) -> None:
        """変異と帰属を識別できる ID を検査する。"""
        for label, value in (
            ("mutant ID", self.mutant_id),
            ("calculation ID", self.calculation),
            ("target ID", self.target_id),
            ("operator ID", self.operator_id),
        ):
            _require_identifier(value, label)


@dataclass(frozen=True, slots=True)
class MutationGeneration:
    """一演算子が一対象について返す変異と未対応箇所。"""

    mutants: tuple[Mutant, ...]
    unsupported: tuple[UnsupportedLocation, ...]


class MutationOperator(Protocol):
    """後続ステップが実装する変異演算子の境界。"""

    operator_id: str

    def generate(self, target: SyntheticMutationTarget) -> MutationGeneration:
        """一つの合成対象から変異または未対応箇所を返す。"""


@dataclass(frozen=True, slots=True)
class KillEvidence:
    """一 mutant をどの検査が kill したかを示す必須記録。"""

    mutant_id: str
    calculation: str
    layer: KillLayer
    check_id: str

    def __post_init__(self) -> None:
        """Kill 要因を対象計算と検査へ一意に結び付ける。"""
        _require_identifier(self.mutant_id, "mutant ID")
        _require_identifier(self.calculation, "calculation ID")
        _require_identifier(self.check_id, "check ID")
        if not isinstance(self.layer, KillLayer):
            raise ValueError(f"未知の kill layer: {self.layer}")


@dataclass(frozen=True, slots=True)
class MutationExecution:
    """一 mutant の実行結果と収集済み kill 要因。"""

    killed: bool
    evidence: tuple[KillEvidence, ...]


class MutantExecutor(Protocol):
    """既存の3層 runnerを使って mutantを実行する境界。"""

    def execute(self, mutant: Mutant) -> MutationExecution:
        """一 mutant の kill 結果と要因を返す。"""


@dataclass(frozen=True, slots=True)
class MutationBatch:
    """固定した合成対象集合から生成した全 mutant。"""

    target_ids: frozenset[str]
    calculation_ids: frozenset[str]
    mutants: tuple[Mutant, ...]


@dataclass(frozen=True, slots=True)
class CalculationMutationResult:
    """一対象計算の集合等式とプロパティ層 kill 実績。"""

    calculation: str
    generated: frozenset[str]
    approved_equivalents: frozenset[str]
    killed: frozenset[str]
    property_killed: frozenset[str]
    survivors: frozenset[str]

    @property
    def resolution_equation_holds(self) -> bool:
        """`generated - approved - killed` が空なら真を返す。"""
        return not self.survivors and self.survivors == (
            self.generated - self.approved_equivalents - self.killed
        )

    @property
    def complete(self) -> bool:
        """生成非空・集合等式・プロパティ層 kill が揃えば真を返す。"""
        return (
            bool(self.generated)
            and self.resolution_equation_holds
            and bool(self.property_killed)
        )


@dataclass(frozen=True, slots=True)
class MutationReport:
    """全対象計算を個別に判定した変異結果。"""

    target_ids: frozenset[str]
    calculations: tuple[CalculationMutationResult, ...]
    kill_evidence: tuple[KillEvidence, ...]

    @property
    def complete(self) -> bool:
        """合成対象が非空で全対象計算が完了した場合だけ真を返す。"""
        return (
            bool(self.target_ids)
            and bool(self.calculations)
            and all(result.complete for result in self.calculations)
        )


def _target_items(
    targets: Iterable[SyntheticMutationTarget],
) -> tuple[SyntheticMutationTarget, ...]:
    """合成対象を固定し、空と重複を拒否する。"""
    items = tuple(targets)
    if not items:
        raise MutationEngineError("合成変異対象が空")
    keys = [(item.calculation, item.target_id) for item in items]
    if len(keys) != len(set(keys)):
        raise MutationEngineError("合成変異対象 ID が重複")
    return items


def _operator_items(
    operators: Iterable[MutationOperator],
) -> tuple[MutationOperator, ...]:
    """演算子 ID の空と重複を拒否する。"""
    items = tuple(operators)
    operator_ids = [operator.operator_id for operator in items]
    for operator_id in operator_ids:
        try:
            _require_identifier(operator_id, "operator ID")
        except ValueError as error:
            raise MutationEngineError(str(error)) from error
    if len(operator_ids) != len(set(operator_ids)):
        raise MutationEngineError("operator ID が重複")
    return items


def generate_mutants(
    targets: Iterable[SyntheticMutationTarget],
    operators: Iterable[MutationOperator],
) -> MutationBatch:
    """全合成対象へ全演算子を適用し、未対応と生成 0 を fail にする。"""
    target_items = _target_items(targets)
    operator_items = _operator_items(operators)
    mutants: list[Mutant] = []
    unsupported: list[UnsupportedLocation] = []
    for target in target_items:
        for operator in operator_items:
            generation = operator.generate(target)
            if not isinstance(generation, MutationGeneration):
                raise MutationEngineError("演算子の生成結果型が不正")
            for location in generation.unsupported:
                if (
                    location.calculation != target.calculation
                    or location.target_id != target.target_id
                    or location.operator_id != operator.operator_id
                ):
                    raise MutationEngineError("未対応箇所の帰属が不正")
                unsupported.append(location)
            for mutant in generation.mutants:
                if (
                    mutant.calculation != target.calculation
                    or mutant.target_id != target.target_id
                    or mutant.operator_id != operator.operator_id
                ):
                    raise MutationEngineError("mutant の帰属が不正")
                mutants.append(mutant)
    if unsupported:
        locations = sorted(
            f"{item.calculation}/{item.target_id}/{item.location_id}"
            for item in unsupported
        )
        raise MutationEngineError(f"未対応箇所がある: {locations!r}")
    mutant_ids = [mutant.mutant_id for mutant in mutants]
    if len(mutant_ids) != len(set(mutant_ids)):
        raise MutationEngineError("mutant ID が重複")
    calculation_ids = frozenset(target.calculation for target in target_items)
    missing_generation = sorted(
        calculation
        for calculation in calculation_ids
        if not any(mutant.calculation == calculation for mutant in mutants)
    )
    if missing_generation:
        raise MutationEngineError(
            f"生成変異 0 の対象計算がある: {missing_generation!r}"
        )
    return MutationBatch(
        target_ids=frozenset(target.target_id for target in target_items),
        calculation_ids=calculation_ids,
        mutants=tuple(mutants),
    )


def _approved_ids(
    batch: MutationBatch,
    approved_equivalent_ids: Iterable[str],
) -> frozenset[str]:
    """承認済み等価変異 ID の重複・未知・未記録自己申告を拒否する。"""
    approved_items = tuple(approved_equivalent_ids)
    if len(approved_items) != len(set(approved_items)):
        raise MutationEngineError("承認済み等価変異 ID が重複")
    generated = {mutant.mutant_id for mutant in batch.mutants}
    unknown = set(approved_items) - generated
    if unknown:
        raise MutationEngineError(f"未知の等価変異承認: {sorted(unknown)!r}")
    approved = frozenset(approved_items)
    unrecorded_claims = {
        mutant.mutant_id
        for mutant in batch.mutants
        if mutant.equivalence_claimed and mutant.mutant_id not in approved
    }
    if unrecorded_claims:
        raise MutationEngineError(
            f"未記録の等価扱い: {sorted(unrecorded_claims)!r}"
        )
    return approved


def _execute_mutants(
    batch: MutationBatch,
    executor: MutantExecutor,
) -> tuple[tuple[KillEvidence, ...], frozenset[str], frozenset[str]]:
    """全 mutant を実行し、hash 以外の kill と property kill を返す。"""
    evidence: list[KillEvidence] = []
    killed: set[str] = set()
    property_killed: set[str] = set()
    for mutant in batch.mutants:
        execution = executor.execute(mutant)
        if not isinstance(execution, MutationExecution):
            raise MutationEngineError("mutant 実行結果型が不正")
        if execution.killed and not execution.evidence:
            raise MutationEngineError(
                f"kill 要因が未記録: {mutant.mutant_id}"
            )
        if not execution.killed and execution.evidence:
            raise MutationEngineError(
                f"生存 mutant に kill 要因がある: {mutant.mutant_id}"
            )
        for item in execution.evidence:
            if (
                item.mutant_id != mutant.mutant_id
                or item.calculation != mutant.calculation
            ):
                raise MutationEngineError("kill 要因の帰属が不正")
            evidence.append(item)
            if item.layer is KillLayer.B1_HASH:
                continue
            killed.add(mutant.mutant_id)
            if item.layer in _PROPERTY_LAYERS:
                property_killed.add(mutant.mutant_id)
    evidence_keys = [
        (item.mutant_id, item.layer, item.check_id) for item in evidence
    ]
    if len(evidence_keys) != len(set(evidence_keys)):
        raise MutationEngineError("kill 要因が重複")
    return tuple(evidence), frozenset(killed), frozenset(property_killed)


def evaluate_mutations(
    batch: MutationBatch,
    executor: MutantExecutor,
    approved_equivalent_ids: Iterable[str] = (),
) -> MutationReport:
    """全 mutant を実行し、対象計算ごとの集合差を計算する。"""
    approved = _approved_ids(batch, approved_equivalent_ids)
    evidence, killed, property_killed = _execute_mutants(batch, executor)
    if approved & killed:
        raise MutationEngineError(
            f"等価承認と kill が重複: {sorted(approved & killed)!r}"
        )
    results: list[CalculationMutationResult] = []
    for calculation in sorted(batch.calculation_ids):
        generated = frozenset(
            mutant.mutant_id
            for mutant in batch.mutants
            if mutant.calculation == calculation
        )
        calculation_approved = generated & approved
        calculation_killed = generated & killed
        survivors = generated - calculation_approved - calculation_killed
        results.append(
            CalculationMutationResult(
                calculation=calculation,
                generated=generated,
                approved_equivalents=calculation_approved,
                killed=calculation_killed,
                property_killed=generated & property_killed,
                survivors=survivors,
            )
        )
    return MutationReport(batch.target_ids, tuple(results), evidence)


def require_mutation_success(report: MutationReport) -> None:
    """対象計算ごとの生存と property kill 欠落を個別に fail にする。"""
    failures: list[str] = []
    for result in report.calculations:
        if result.survivors:
            failures.append(
                f"{result.calculation}: survivors={sorted(result.survivors)!r}"
            )
        if not result.property_killed:
            failures.append(f"{result.calculation}: property-kill=0")
    if failures or not report.complete:
        raise MutationEngineError(f"変異判定が不合格: {failures!r}")


def run_mutations(
    *,
    targets: Iterable[SyntheticMutationTarget],
    operators: Iterable[MutationOperator],
    executor: MutantExecutor,
    approved_equivalent_ids: Iterable[str] = (),
) -> MutationReport:
    """変異生成から対象計算単位の生存 0 判定までを実行する。"""
    batch = generate_mutants(targets, operators)
    report = evaluate_mutations(batch, executor, approved_equivalent_ids)
    require_mutation_success(report)
    return report


__all__ = [
    "CalculationMutationResult",
    "KillEvidence",
    "KillLayer",
    "Mutant",
    "MutantExecutor",
    "MutationBatch",
    "MutationEngineError",
    "MutationExecution",
    "MutationGeneration",
    "MutationOperator",
    "MutationReport",
    "SyntheticMutationTarget",
    "UnsupportedLocation",
    "evaluate_mutations",
    "generate_mutants",
    "require_mutation_success",
    "run_mutations",
]
