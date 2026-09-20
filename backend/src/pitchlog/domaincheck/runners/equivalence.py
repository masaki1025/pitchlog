"""要求 case 全件について target matrix 別の等価性を検査する。

`backend/domain/required-cases.json` は正本と schema から独立導出された有限の
決定的 case 集合なので、本ステップの比較には追加ライブラリを必要としない。
将来ステップ 54 で依存追加を判断する場合の候補は Hypothesis とするが、ここでは
依存を増やさず、同じ case 集合を四つの比較面へ適用する。

表示を含む lossless 比較は `path_match`、要求 case の網羅性は
`required_cases`、参照実装の生成由来は `domaingen.formatter` に委ねる。
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from pitchlog.domaincheck.path_match import (
    ComparisonContract,
    PathKey,
    PathMatchReport,
    PathSubmission,
    compare_path_set,
)
from pitchlog.domaincheck.runners.required_cases import (
    CoverageError,
    CoverageProof,
    require_complete_coverage,
)
from pitchlog.domaingen.backends import TARGET_CLASSES
from pitchlog.domaingen.formatter import (
    DisplayPurpose,
    GeneratedDisplayArtifact,
    verify_generated_provenance,
)

_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9._-]*$")
_REFERENCE_DELIVERY = "test-only-property-layer"
_COMPARISON_PAIRS = {
    "alpha": ("generated-python", "generated-typescript"),
    "beta-1-5": ("composite-target", "generated-reference"),
    "beta-7": ("enum-map-receiver", "generated-reference"),
    "beta-6-8": ("generated-python", "generated-reference"),
}
_REQUIRED_ROLES = {
    "alpha": frozenset({"structured", "display"}),
    "beta-1-5": frozenset({"structured", "display"}),
    "beta-7": frozenset({"display"}),
    "beta-6-8": frozenset({"structured"}),
}


class EquivalenceRunError(Exception):
    """等価性 runner が契約どおり完走できないことを表す。"""


@dataclass(frozen=True, slots=True)
class EquivalenceTarget:
    """一つの target matrix 区分に対する比較契約。

    Attributes:
        target_class: `alpha` または三つの `beta` 区分。
        calculation: 合成対象計算 ID。
        vector: 要求 case を供給する vector ID。
        runner: 証跡上の runner ID。
        entrypoint_id: 左辺実装を呼ぶ入口 ID。
        direct_target_id: 右辺の直接呼び出し対象 ID。
        left_implementation: 比較表が定める左辺実装種別。
        right_implementation: 比較表が定める右辺実装種別。
        comparison: 行と全フィールドの lossless 比較契約。
        reference_artifact: 生成器が作ったテスト専用参照実装。
    """

    target_class: str
    calculation: str
    vector: str
    runner: str
    entrypoint_id: str
    direct_target_id: str
    left_implementation: str
    right_implementation: str
    comparison: ComparisonContract
    reference_artifact: GeneratedDisplayArtifact


@dataclass(frozen=True, slots=True)
class EquivalenceCase:
    """一 case に対する二つの実装の生出力。

    Attributes:
        case_id: `required-cases.json` に由来する case ID。
        left_output: 比較表の左辺実装が返した raw 出力。
        right_output: 比較表の右辺実装が返した raw 出力。
    """

    case_id: str
    left_output: object
    right_output: object

    def __post_init__(self) -> None:
        """空または不正な case ID を拒否する。"""
        if _IDENTIFIER.fullmatch(self.case_id) is None:
            raise ValueError(f"不正な case ID: {self.case_id}")


@dataclass(frozen=True, slots=True)
class EquivalenceRunReport:
    """一比較面の網羅性証明と lossless 比較結果。"""

    target_class: str
    coverage: CoverageProof
    comparison: PathMatchReport

    @property
    def complete(self) -> bool:
        """要求 case が網羅され全比較が成立した場合だけ真を返す。"""
        return self.coverage.complete and self.comparison.complete


def comparison_pair(target_class: str) -> tuple[str, str]:
    """Target matrix 区分に対応する左右の実装種別を返す。

    Args:
        target_class: Target matrix の区分。

    Returns:
        左辺と右辺の実装種別。

    Raises:
        EquivalenceRunError: 未知区分または比較表の内部不整合がある場合。
    """
    if set(_COMPARISON_PAIRS) != set(TARGET_CLASSES):
        raise EquivalenceRunError("target matrix と等価性比較表が一致しない")
    try:
        return _COMPARISON_PAIRS[target_class]
    except KeyError as error:
        raise EquivalenceRunError(
            f"未知の target matrix 区分: {target_class}"
        ) from error


def _validate_identifier(value: str, label: str) -> None:
    """証跡の識別子が空でなく閉じた文字種であることを検査する。"""
    if _IDENTIFIER.fullmatch(value) is None:
        raise EquivalenceRunError(f"{label} が不正: {value}")


def _validate_target(
    target: EquivalenceTarget,
    intermediate: Mapping[str, object],
) -> None:
    """比較面と参照実装が対象区分の契約に一致することを検査する。"""
    expected_pair = comparison_pair(target.target_class)
    if (target.left_implementation, target.right_implementation) != expected_pair:
        raise EquivalenceRunError(
            f"{target.target_class} の比較実装種別が不正"
        )
    for label, value in (
        ("calculation", target.calculation),
        ("vector", target.vector),
        ("entrypointId", target.entrypoint_id),
        ("directTargetId", target.direct_target_id),
    ):
        _validate_identifier(value, label)
    observed_roles = frozenset(field.role for field in target.comparison.fields)
    required_roles = _REQUIRED_ROLES[target.target_class]
    if observed_roles != required_roles:
        raise EquivalenceRunError(
            f"{target.target_class} の比較面が不正: "
            f"required={sorted(required_roles)!r}, "
            f"observed={sorted(observed_roles)!r}"
        )

    reference = target.reference_artifact
    if reference.calculation_id != target.calculation:
        raise EquivalenceRunError("参照実装の calculation が一致しない")
    if reference.direct_target_id != target.direct_target_id:
        raise EquivalenceRunError("参照実装の direct target が一致しない")
    if reference.target_class != target.target_class:
        raise EquivalenceRunError("参照実装の target class が一致しない")
    if reference.purpose is not DisplayPurpose.REFERENCE:
        raise EquivalenceRunError("参照実装の purpose が不正")
    if reference.delivery != _REFERENCE_DELIVERY:
        raise EquivalenceRunError("参照実装がテスト専用経路に分離されていない")
    if not verify_generated_provenance(reference, intermediate):
        raise EquivalenceRunError("参照実装の生成由来を再現できない")


def _case_items(cases: Iterable[EquivalenceCase]) -> tuple[EquivalenceCase, ...]:
    """空と重複を拒否して case 列を固定する。"""
    items = tuple(cases)
    if not items:
        raise EquivalenceRunError("等価性 case が 0 件")
    case_ids = [item.case_id for item in items]
    if len(case_ids) != len(set(case_ids)):
        raise EquivalenceRunError("等価性 case ID が重複")
    return items


def run_equivalence(
    *,
    target: EquivalenceTarget,
    cases: Iterable[EquivalenceCase],
    required_case_asset: Mapping[str, object],
    intermediate: Mapping[str, object],
) -> EquivalenceRunReport:
    """一 target matrix 区分の要求 case 全件を lossless に比較する。

    Args:
        target: 区分・実装種別・比較面・生成参照実装の契約。
        cases: 左右の実装を実行して得た case 別 raw 出力。
        required_case_asset: ステップ 35 の要求 case 集合。
        intermediate: 参照実装を再生成する中間表現。

    Returns:
        要求 case の網羅性証明と行・全フィールドの比較結果。

    Raises:
        EquivalenceRunError: 網羅性、生成由来、比較のいずれかが不適合な場合。
    """
    _validate_target(target, intermediate)
    items = _case_items(cases)
    try:
        coverage = require_complete_coverage(
            required_case_asset,
            (item.case_id for item in items),
        )
    except CoverageError as error:
        raise EquivalenceRunError(f"要求 case を網羅しない: {error}") from error

    requirements: list[PathKey] = []
    submissions: list[PathSubmission] = []
    for item in items:
        key = PathKey(
            calculation=target.calculation,
            vector=target.vector,
            case=item.case_id,
            runner=target.runner,
            entrypoint_id=target.entrypoint_id,
            direct_target_id=target.direct_target_id,
        )
        requirements.append(key)
        submissions.append(
            PathSubmission(
                key=key,
                expected=item.right_output,
                entrypoint_output=item.left_output,
                direct_target_output=item.right_output,
            )
        )
    try:
        comparison = compare_path_set(
            requirements,
            submissions,
            {target.calculation: target.comparison},
        )
    except ValueError as error:
        raise EquivalenceRunError(f"等価性を比較できない: {error}") from error
    if not comparison.complete:
        differences = sorted(
            {
                difference.reason
                for evidence in comparison.evidence
                for difference in evidence.differences
            }
        )
        raise EquivalenceRunError(
            f"{target.target_class} の等価性違反: {differences!r}"
        )
    report = EquivalenceRunReport(target.target_class, coverage, comparison)
    if not report.complete:
        raise EquivalenceRunError("等価性 runner が完走しなかった")
    return report


__all__ = [
    "EquivalenceCase",
    "EquivalenceRunError",
    "EquivalenceRunReport",
    "EquivalenceTarget",
    "comparison_pair",
    "run_equivalence",
]
