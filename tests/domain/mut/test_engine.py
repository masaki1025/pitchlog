"""変異エンジンが対象計算単位で生存 0 を判定することを検査する。"""

from __future__ import annotations

import dataclasses
import importlib
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
BACKEND_SRC = ROOT / "backend/src"

sys.path.insert(0, str(BACKEND_SRC))
ENGINE = importlib.import_module("pitchlog.domainmut.engine")


@dataclasses.dataclass(frozen=True, slots=True)
class _IncrementOperator:
    """整数だけを実際に増加させる合成演算子。"""

    operator_id: str = "synthetic-increment"
    claim_equivalent: bool = False

    def generate(self, target: Any) -> Any:
        """整数なら mutant、整数以外なら未対応箇所を返す。"""
        if not isinstance(target.source, int) or isinstance(target.source, bool):
            return ENGINE.MutationGeneration(
                mutants=(),
                unsupported=(
                    ENGINE.UnsupportedLocation(
                        calculation=target.calculation,
                        target_id=target.target_id,
                        location_id="source-root",
                        operator_id=self.operator_id,
                        reason="整数リテラル以外は後続演算子の担当",
                    ),
                ),
            )
        mutant = ENGINE.Mutant(
            mutant_id=f"{target.calculation}.{target.target_id}.increment",
            calculation=target.calculation,
            target_id=target.target_id,
            operator_id=self.operator_id,
            mutated=target.source + 1,
            equivalence_claimed=self.claim_equivalent,
        )
        return ENGINE.MutationGeneration(mutants=(mutant,), unsupported=())


@dataclasses.dataclass(frozen=True, slots=True)
class _ZeroOperator:
    """未対応報告も mutant 生成もしない欠陥演算子。"""

    operator_id: str = "synthetic-zero"

    def generate(self, target: Any) -> Any:
        """常に空の生成結果を返す。"""
        return ENGINE.MutationGeneration(mutants=(), unsupported=())


@dataclasses.dataclass(frozen=True, slots=True)
class _Executor:
    """Mutant ID ごとに指定した kill layer を返す合成実行器。"""

    layers: dict[str, tuple[Any, ...]]
    killed_without_evidence: frozenset[str] = frozenset()

    def execute(self, mutant: Any) -> Any:
        """指定された3層 runner相当のkill証跡を返す。"""
        if mutant.mutant_id in self.killed_without_evidence:
            return ENGINE.MutationExecution(killed=True, evidence=())
        layers = self.layers.get(mutant.mutant_id, ())
        evidence = tuple(
            ENGINE.KillEvidence(
                mutant_id=mutant.mutant_id,
                calculation=mutant.calculation,
                layer=layer,
                check_id=f"{mutant.target_id}.{layer.value}",
            )
            for layer in layers
        )
        return ENGINE.MutationExecution(
            killed=bool(evidence),
            evidence=evidence,
        )


def _target(
    calculation: str = "syntheticCalculation",
    target_id: str = "syntheticTarget",
    source: object = 1,
) -> Any:
    """固定された一つの合成変異対象を返す。"""
    return ENGINE.SyntheticMutationTarget(calculation, target_id, source)


def _mutant_id(target: Any) -> str:
    """合成増加演算子が作る mutant ID を返す。"""
    return f"{target.calculation}.{target.target_id}.increment"


def _property_executor(*targets: Any) -> _Executor:
    """指定対象の mutant をプロパティ層で kill する実行器を返す。"""
    return _Executor(
        {
            _mutant_id(target): (ENGINE.KillLayer.PROPERTY_INVARIANT,)
            for target in targets
        }
    )


def test_one_unsupported_location_fails() -> None:
    """演算子が列挙した未対応箇所を一件でも黙って飛ばさない。"""
    target = _target(source="unsupported")

    with pytest.raises(ENGINE.MutationEngineError, match="未対応箇所"):
        ENGINE.run_mutations(
            targets=(target,),
            operators=(_IncrementOperator(),),
            executor=_Executor({}),
        )


def test_zero_generated_mutants_fails() -> None:
    """未対応報告が無くても対象計算の生成変異 0 を拒否する。"""
    target = _target()

    with pytest.raises(ENGINE.MutationEngineError, match="生成変異 0"):
        ENGINE.run_mutations(
            targets=(target,),
            operators=(_ZeroOperator(),),
            executor=_Executor({}),
        )


def test_one_surviving_mutant_fails() -> None:
    """非等価 mutant が一件生存すると集合等式が不成立になる。"""
    target = _target()

    with pytest.raises(ENGINE.MutationEngineError, match="survivors"):
        ENGINE.run_mutations(
            targets=(target,),
            operators=(_IncrementOperator(),),
            executor=_Executor({}),
        )


def test_success_in_another_calculation_cannot_dilute_survivor() -> None:
    """別対象計算のkill数で欠落対象の生存を希釈できない。"""
    killed_target = _target("syntheticKilled", "killedTarget")
    surviving_target = _target("syntheticSurvivor", "survivingTarget")
    executor = _property_executor(killed_target)

    with pytest.raises(
        ENGINE.MutationEngineError,
        match="syntheticSurvivor.*survivors",
    ):
        ENGINE.run_mutations(
            targets=(killed_target, surviving_target),
            operators=(_IncrementOperator(),),
            executor=executor,
        )


def test_unrecorded_equivalence_claim_fails() -> None:
    """演算子の自己申告だけで未記録 mutant を等価扱いにしない。"""
    target = _target()

    with pytest.raises(ENGINE.MutationEngineError, match="未記録の等価扱い"):
        ENGINE.run_mutations(
            targets=(target,),
            operators=(_IncrementOperator(claim_equivalent=True),),
            executor=_Executor({}),
            approved_equivalent_ids=(),
        )


def test_kill_without_recorded_cause_fails() -> None:
    """Killedという結果だけでkill要因が無いmutantを拒否する。"""
    target = _target()
    mutant_id = _mutant_id(target)

    with pytest.raises(ENGINE.MutationEngineError, match="kill 要因が未記録"):
        ENGINE.run_mutations(
            targets=(target,),
            operators=(_IncrementOperator(),),
            executor=_Executor({}, frozenset({mutant_id})),
        )


def test_property_layer_kill_is_required_even_when_vector_kills_all() -> None:
    """生存0でもプロパティ層killが0なら対象計算を合格にしない。"""
    target = _target()
    executor = _Executor({_mutant_id(target): (ENGINE.KillLayer.VECTOR,)})

    with pytest.raises(ENGINE.MutationEngineError, match="property-kill=0"):
        ENGINE.run_mutations(
            targets=(target,),
            operators=(_IncrementOperator(),),
            executor=executor,
        )


def test_hash_only_kill_is_excluded_and_remains_surviving() -> None:
    """(b)①のhash検査だけによるkillを分子へ入れず生存扱いにする。"""
    target = _target()
    mutant_id = _mutant_id(target)
    batch = ENGINE.generate_mutants((target,), (_IncrementOperator(),))
    executor = _Executor({mutant_id: (ENGINE.KillLayer.B1_HASH,)})

    report = ENGINE.evaluate_mutations(batch, executor)
    result = report.calculations[0]

    assert result.generated == {mutant_id}
    assert result.killed == set()
    assert result.survivors == {mutant_id}
    assert not result.resolution_equation_holds
    assert not report.complete
    with pytest.raises(ENGINE.MutationEngineError, match="survivors"):
        ENGINE.require_mutation_success(report)


def test_synthetic_target_set_is_nonempty_and_fixed() -> None:
    """空対象を拒否し、生成後も合成対象ID集合を証跡へ固定する。"""
    with pytest.raises(ENGINE.MutationEngineError, match="合成変異対象が空"):
        ENGINE.generate_mutants((), (_IncrementOperator(),))

    target = _target()
    batch = ENGINE.generate_mutants((target,), (_IncrementOperator(),))

    assert batch.target_ids == {target.target_id}
    assert batch.calculation_ids == {target.calculation}


def test_real_mutant_is_generated_and_killed_by_property_layer() -> None:
    """合成対象の値を実際に変えたmutantがプロパティ層でkillされる。"""
    target = _target(source=1)
    report = ENGINE.run_mutations(
        targets=(target,),
        operators=(_IncrementOperator(),),
        executor=_property_executor(target),
    )
    result = report.calculations[0]
    mutant = ENGINE.generate_mutants(
        (target,),
        (_IncrementOperator(),),
    ).mutants[0]

    assert mutant.mutated == 2
    assert mutant.mutated != target.source
    assert report.complete
    assert result.generated - result.approved_equivalents - result.killed == set()
    assert result.resolution_equation_holds
    assert result.property_killed == result.killed
