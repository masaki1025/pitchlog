"""合成契約を使う網羅ベクタ runner の基盤を提供する。

`ADR-003 D-11 ② 3 層表` が定める順序どおり、生値へ生成済み正規化を
適用し、正規化後期待値を照合してから、その実値を計算入力へ渡す。
Lossless 比較は `path_match` の比較器へ委ね、この runner では再実装しない。
"""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, cast

from pitchlog.domaincheck.cli import (
    CheckerExecutionError,
    CheckerViolation,
    validate_asset,
)
from pitchlog.domaincheck.path_match import (
    ComparisonContract,
    PathKey,
    PathSubmission,
    compare_path_set,
)

_HASH = re.compile(r"^sha256:[0-9a-f]{64}$")


class VectorRunError(Exception):
    """ベクタを契約どおり実行できないことを表す。"""


class UnsupportedVectorCase(Exception):
    """計算 adapter が宣言済み case に未対応であることを表す。"""


class GeneratedNormalizer(Protocol):
    """生成済み正規化を呼び出すための境界。"""

    generated_id: str
    source_hash: str

    def normalize(self, raw: object) -> object:
        """生値へ生成済み正規化を適用する。"""


class CalculationAdapter(Protocol):
    """正規化済み値を対象計算へ渡すための境界。"""

    def execute(self, case_id: str, normalized: object) -> object:
        """一つの case を正規化済み入力で実行する。"""


@dataclass(frozen=True, slots=True)
class VectorContract:
    """合成ベクタ runner が読む契約。

    Attributes:
        calculation: 合成対象計算 ID。
        vector: 合成ベクタ ID。
        runner: 証跡上の runner ID。
        entrypoint_id: 計算 adapter の入口 ID。
        direct_target_id: 生成済み正規化の直接対象 ID。
        case_schema: 一 case の厳密 JSON Schema。
        normalization_comparison: 正規化後値の比較面。
        output_comparison: 計算結果の比較面。
    """

    calculation: str
    vector: str
    runner: str
    entrypoint_id: str
    direct_target_id: str
    case_schema: Mapping[str, object]
    normalization_comparison: ComparisonContract
    output_comparison: ComparisonContract


@dataclass(frozen=True, slots=True)
class VectorCaseExecution:
    """一 case が順序どおり完走した証跡。

    Attributes:
        case_id: 消費した case ID。
        generated_id: 呼び出した正規化生成物 ID。
        source_hash: 正規化生成物の宣言 hash。
        normalization_matched: 正規化後期待値との一致。
        output_matched: 計算結果期待値との一致。
    """

    case_id: str
    generated_id: str
    source_hash: str
    normalization_matched: bool
    output_matched: bool


@dataclass(frozen=True, slots=True)
class VectorRunReport:
    """宣言された全 case の消費結果。

    Attributes:
        declared_case_ids: Vector が宣言した case ID。
        consumed_case_ids: 正規化・照合・計算を完走した case ID。
        executions: Case ごとの実行証跡。
    """

    declared_case_ids: tuple[str, ...]
    consumed_case_ids: tuple[str, ...]
    executions: tuple[VectorCaseExecution, ...]

    @property
    def complete(self) -> bool:
        """全 case が一度ずつ完走した場合だけ真を返す。"""
        return (
            bool(self.declared_case_ids)
            and self.consumed_case_ids == self.declared_case_ids
            and len(self.executions) == len(self.declared_case_ids)
            and all(
                item.normalization_matched and item.output_matched
                for item in self.executions
            )
        )


def _object(value: object, label: str) -> dict[str, object]:
    """文字列キーだけを持つ object を返す。"""
    if not isinstance(value, dict) or not all(
        isinstance(key, str) for key in value
    ):
        raise VectorRunError(f"{label} が object でない")
    return cast(dict[str, object], value)


def _string(value: object, label: str) -> str:
    """空でない文字列を返す。"""
    if not isinstance(value, str) or not value:
        raise VectorRunError(f"{label} が空でない文字列でない")
    return value


def _validate_generated_normalizer(normalizer: GeneratedNormalizer) -> None:
    """正規化生成物の一意 ID と内容 hash を検査する。"""
    if not normalizer.generated_id:
        raise VectorRunError("正規化生成物 ID が空")
    if _HASH.fullmatch(normalizer.source_hash) is None:
        raise VectorRunError("正規化生成物 hash が不正")


def _validate_cases(
    cases: object,
    schema: Mapping[str, object],
) -> tuple[dict[str, object], ...]:
    """全 case を既存 schema 検査器で検証し、重複 ID を拒否する。"""
    if not isinstance(cases, list) or not cases:
        raise VectorRunError("cases が空でない array でない")
    validated: list[dict[str, object]] = []
    case_ids: list[str] = []
    for index, raw_case in enumerate(cases):
        try:
            validate_asset(raw_case, schema)
        except (CheckerViolation, CheckerExecutionError) as error:
            raise VectorRunError(
                f"case schema 不一致: cases[{index}]: {error}"
            ) from error
        case = _object(raw_case, f"cases[{index}]")
        case_id = _string(case.get("caseId"), f"cases[{index}].caseId")
        validated.append(case)
        case_ids.append(case_id)
    duplicates = sorted(
        case_id for case_id in set(case_ids) if case_ids.count(case_id) > 1
    )
    if duplicates:
        raise VectorRunError(f"case ID が重複: {duplicates!r}")
    return tuple(validated)


def _comparison_key(contract: VectorContract, case_id: str) -> PathKey:
    """既存比較器へ渡す合成 6 次元キーを返す。"""
    return PathKey(
        calculation=contract.calculation,
        vector=contract.vector,
        case=case_id,
        runner=contract.runner,
        entrypoint_id=contract.entrypoint_id,
        direct_target_id=contract.direct_target_id,
    )


def _matches(
    key: PathKey,
    expected: object,
    actual: object,
    comparison: ComparisonContract,
) -> bool:
    """既存の lossless 比較器で期待値と実値を照合する。"""
    report = compare_path_set(
        [key],
        [PathSubmission(key, expected, actual, actual)],
        {key.calculation: comparison},
    )
    return report.complete


def run_vectors(
    cases: object,
    contract: VectorContract,
    normalizer: GeneratedNormalizer,
    calculation: CalculationAdapter,
) -> VectorRunReport:
    """合成 vector の全 case を正規化から計算まで順に実行する。

    Args:
        cases: 合成契約が宣言する case の配列。
        contract: Case schema と二つの lossless 比較面。
        normalizer: 宣言モデルから生成済みの正規化実装。
        calculation: 正規化済み入力だけを受ける計算 adapter。

    Returns:
        宣言 case と消費 case を持つ完走証跡。

    Raises:
        VectorRunError: Schema・ID・正規化・計算結果のいずれかが不適合な場合。
    """
    _validate_generated_normalizer(normalizer)
    validated = _validate_cases(cases, contract.case_schema)
    declared = tuple(_string(case["caseId"], "caseId") for case in validated)
    consumed: list[str] = []
    executions: list[VectorCaseExecution] = []
    for case in validated:
        case_id = _string(case["caseId"], "caseId")
        key = _comparison_key(contract, case_id)
        normalized = normalizer.normalize(copy.deepcopy(case["raw"]))
        normalization_matched = _matches(
            key,
            case["normalized"],
            normalized,
            contract.normalization_comparison,
        )
        if not normalization_matched:
            raise VectorRunError(
                f"生成済み正規化の出力が不一致: {case_id}"
            )
        try:
            actual = calculation.execute(case_id, normalized)
        except UnsupportedVectorCase as error:
            raise VectorRunError(f"未対応 case: {case_id}") from error
        output_matched = _matches(
            key,
            case["expected"],
            actual,
            contract.output_comparison,
        )
        if not output_matched:
            raise VectorRunError(f"計算結果が不一致: {case_id}")
        consumed.append(case_id)
        executions.append(
            VectorCaseExecution(
                case_id=case_id,
                generated_id=normalizer.generated_id,
                source_hash=normalizer.source_hash,
                normalization_matched=normalization_matched,
                output_matched=output_matched,
            )
        )
    report = VectorRunReport(declared, tuple(consumed), tuple(executions))
    if not report.complete:
        raise VectorRunError("全 case を消費していない")
    return report


__all__ = [
    "CalculationAdapter",
    "GeneratedNormalizer",
    "UnsupportedVectorCase",
    "VectorCaseExecution",
    "VectorContract",
    "VectorRunError",
    "VectorRunReport",
    "run_vectors",
]
