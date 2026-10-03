"""収集済みの生出力から経路一致の 5 判定を計算する。

`ADR-003 D-11 ③ 経路一致検査の理由` が固定する 6 次元要求集合と
5 判定を保つ。比較は `ADR-003 D-11 ③ 動的機構の禁止行` の lossless
規則に閉じ、行の全順序化と情報を落とさない数値表現の統一だけを許す。
表示文字列は文字種・先頭 0・負号・剰余表記を含めて完全一致で比較する。
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import cast

from pitchlog.domaincheck.collect_layers import (
    FiveJudgments,
    LayerEvidence,
)

_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9._-]*$")
_DECIMAL = re.compile(r"^(?P<sign>-?)(?P<whole>0|[1-9][0-9]*)\.(?P<fraction>[0-9]+)$")
_NORMALIZATIONS = frozenset({"total-order", "exact-numeric-representation"})
_VALUE_TYPES = frozenset({"json", "exact-number", "display-string"})
_SURFACES = frozenset({"structured-only", "structured-and-display"})
_RUNNERS = frozenset({"pytest", "vitest"})
_MISSING = object()


@dataclass(frozen=True, order=True, slots=True)
class PathKey:
    """経路一致要求集合の 6 次元キー。

    Attributes:
        calculation: 対象計算 ID。
        vector: ベクタ ID。
        case: Case ID。
        runner: `pytest` または `vitest`。
        entrypoint_id: 製品の実行入口 ID。
        direct_target_id: 正本生成物の直接呼び出し対象 ID。
    """

    calculation: str
    vector: str
    case: str
    runner: str
    entrypoint_id: str
    direct_target_id: str

    def __post_init__(self) -> None:
        """空の次元と未知 runner を拒否する。"""
        identifiers = (
            self.calculation,
            self.vector,
            self.case,
            self.entrypoint_id,
            self.direct_target_id,
        )
        if not all(_IDENTIFIER.fullmatch(value) for value in identifiers):
            raise ValueError("6 次元キーに不正な識別子がある")
        if self.runner not in _RUNNERS:
            raise ValueError(f"未知の runner: {self.runner}")

    def to_document(self) -> dict[str, str]:
        """JSON Schema の 6 次元キー表現を返す。"""
        return {
            "calculation": self.calculation,
            "vector": self.vector,
            "case": self.case,
            "runner": self.runner,
            "entrypointId": self.entrypoint_id,
            "directTargetId": self.direct_target_id,
        }


@dataclass(frozen=True, slots=True)
class FieldContract:
    """行の一フィールドに対する比較契約。

    Attributes:
        field: 行内のフィールド名。
        role: `structured` または `display`。
        value_type: JSON・exact number・表示文字列のいずれか。
        nullable: `null` を値として許すか。
        scale: Exact number が raw 出力で満たす scale。
    """

    field: str
    role: str
    value_type: str
    nullable: bool
    scale: int | None

    def __post_init__(self) -> None:
        """フィールド契約の矛盾を拒否する。"""
        if _IDENTIFIER.fullmatch(self.field) is None:
            raise ValueError(f"不正なフィールド名: {self.field}")
        if self.role not in {"structured", "display"}:
            raise ValueError(f"未知のフィールド role: {self.role}")
        if self.value_type not in _VALUE_TYPES:
            raise ValueError(f"未知の value type: {self.value_type}")
        if (self.role == "display") != (self.value_type == "display-string"):
            raise ValueError("表示 role と表示文字列型が一致しない")
        if self.value_type == "exact-number":
            if (
                not isinstance(self.scale, int)
                or isinstance(self.scale, bool)
                or self.scale < 0
            ):
                raise ValueError("exact number には非負の scale が必要")
        elif self.scale is not None:
            raise ValueError("exact number 以外に scale を指定できない")

    def to_document(self) -> dict[str, object]:
        """JSON Schema のフィールド契約表現を返す。"""
        return {
            "field": self.field,
            "role": self.role,
            "valueType": self.value_type,
            "nullable": self.nullable,
            "scale": self.scale,
        }


@dataclass(frozen=True, slots=True)
class ComparisonContract:
    """一対象計算の lossless 比較面。

    Attributes:
        surface: 構造化値のみ、または構造化値と表示値。
        fields: 比較面の全フィールド。
        normalizations: 許可する二つ以下の lossless 変換。
    """

    surface: str
    fields: tuple[FieldContract, ...]
    normalizations: frozenset[str]

    def __post_init__(self) -> None:
        """比較面の空・重複・表示値の帰属違反を拒否する。"""
        if self.surface not in _SURFACES:
            raise ValueError(f"未知の比較面: {self.surface}")
        if not self.fields:
            raise ValueError("比較フィールドを空にできない")
        names = [field.field for field in self.fields]
        if len(names) != len(set(names)):
            raise ValueError("比較フィールドが重複している")
        unknown = self.normalizations - _NORMALIZATIONS
        if unknown:
            raise ValueError(f"未知の正規化: {sorted(unknown)!r}")
        has_display = any(field.role == "display" for field in self.fields)
        if has_display != (self.surface == "structured-and-display"):
            raise ValueError("比較面と表示フィールドの有無が一致しない")


@dataclass(frozen=True, slots=True)
class PathSubmission:
    """収集器が採取した一経路の生出力。

    Attributes:
        key: 6 次元要求キー。
        expected: 契約が定める期待行。
        entrypoint_output: 製品入口経由の raw 出力。
        direct_target_output: 正本生成物直接呼び出しの raw 出力。
    """

    key: PathKey
    expected: object
    entrypoint_output: object = _MISSING
    direct_target_output: object = _MISSING


@dataclass(frozen=True, slots=True)
class Difference:
    """行×フィールド単位の不一致。

    Attributes:
        route: 比較した二つの経路。
        row: 不一致行。行全体なら `None`。
        field: 不一致フィールド。行全体なら `None`。
        reason: 機械可読な不一致理由。
    """

    route: str
    row: int | None
    field: str | None
    reason: str

    def to_document(self) -> dict[str, object]:
        """証跡 schema の不一致表現を返す。"""
        return {
            "route": self.route,
            "row": self.row,
            "field": self.field,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class PathEvidence:
    """6 次元の一要素に対する 5 判定の証跡。"""

    key: PathKey
    contract: ComparisonContract
    judgments: FiveJudgments
    differences: tuple[Difference, ...]

    @property
    def complete(self) -> bool:
        """5 判定が成立し、不一致が無い場合だけ真を返す。"""
        return self.judgments.complete and not self.differences

    def to_document(self) -> dict[str, object]:
        """証跡 schema に適合する一要素を返す。"""
        document: dict[str, object] = {**self.key.to_document()}
        document.update(
            {
                "comparisonSurface": self.contract.surface,
                "comparedFields": [
                    field.to_document() for field in self.contract.fields
                ],
                "normalizations": sorted(self.contract.normalizations),
                "judgments": {
                    "entrypointExecuted": self.judgments.entrypoint_executed,
                    "directTargetExecuted": (self.judgments.direct_target_executed),
                    "entrypointEqualsExpected": (
                        self.judgments.entrypoint_equals_expected
                    ),
                    "directTargetEqualsExpected": (
                        self.judgments.direct_target_equals_expected
                    ),
                    "pathsEqual": self.judgments.paths_equal,
                },
                "differences": [
                    difference.to_document() for difference in self.differences
                ],
            }
        )
        return document


@dataclass(frozen=True, slots=True)
class PathMatchReport:
    """要求集合と証跡集合を双方向で突合した結果。"""

    requirements: tuple[PathKey, ...]
    evidence: tuple[PathEvidence, ...]
    missing: tuple[PathKey, ...]
    unexpected: tuple[PathKey, ...]

    @property
    def complete(self) -> bool:
        """集合差が無く、全証跡が成立した場合だけ真を返す。"""
        return (
            bool(self.requirements)
            and not self.missing
            and not self.unexpected
            and len(self.evidence) == len(self.requirements)
            and all(item.complete for item in self.evidence)
        )

    def to_document(self) -> dict[str, object]:
        """`path-match.schema.json` に適合する文書を返す。"""
        return {
            "schemaVersion": 1,
            "requirements": [item.to_document() for item in self.requirements],
            "evidence": [item.to_document() for item in self.evidence],
            "setDifference": {
                "missing": [item.to_document() for item in self.missing],
                "unexpected": [item.to_document() for item in self.unexpected],
            },
        }


def _json_object(value: object) -> dict[str, object] | None:
    """文字列キーだけを持つ JSON object を返す。"""
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        return None
    return cast(dict[str, object], value)


def _exact_coefficient(
    value: object,
    scale: int,
) -> tuple[int | None, str | None]:
    """Scale を満たす exact number を整数係数へ情報保存変換する。"""
    item = _json_object(value)
    if item is None:
        return None, "type-mismatch"
    if set(item) == {"kind", "value", "scale"}:
        raw_value = item.get("value")
        raw_scale = item.get("scale")
        if item.get("kind") != "scaled-integer":
            return None, "type-mismatch"
        if (
            not isinstance(raw_value, int)
            or isinstance(raw_value, bool)
            or not isinstance(raw_scale, int)
            or isinstance(raw_scale, bool)
            or raw_scale != scale
        ):
            return None, "scale-mismatch"
        return raw_value, None
    if set(item) != {"kind", "value"}:
        return None, "type-mismatch"
    raw = item.get("value")
    if item.get("kind") == "integer":
        # 型境界検査が移行センチネル変換と誤認しないよう、非負 scale の
        # 真偽値で 0 以外を判定する。意味は `scale != 0` と同じである。
        if scale:
            return None, "scale-mismatch"
        if not isinstance(raw, int) or isinstance(raw, bool):
            return None, "type-mismatch"
        return raw, None
    if item.get("kind") != "exact-decimal" or not isinstance(raw, str):
        return None, "type-mismatch"
    matched = _DECIMAL.fullmatch(raw)
    if matched is None:
        return None, "type-mismatch"
    fraction = matched.group("fraction")
    if len(fraction) != scale:
        return None, "scale-mismatch"
    coefficient = int(matched.group("whole") + fraction)
    if matched.group("sign"):
        coefficient = -coefficient
    return coefficient, None


def _normalize_value(
    value: object,
    field: FieldContract,
    unify_exact_numbers: bool,
) -> tuple[object, str | None]:
    """一フィールドを検証し、許可時だけ数値表現を統一する。"""
    if value is None:
        if field.nullable:
            return None, None
        return None, "null-not-allowed"
    if field.value_type == "display-string":
        if not isinstance(value, str):
            return value, "type-mismatch"
        return value, None
    if field.value_type == "json":
        return value, None
    assert field.scale is not None
    coefficient, issue = _exact_coefficient(value, field.scale)
    if issue is not None:
        return value, issue
    if unify_exact_numbers:
        return {
            "kind": "exact-coefficient",
            "value": coefficient,
            "scale": field.scale,
        }, None
    return value, None


def _canonical_row(row: Mapping[str, object]) -> str:
    """全フィールドを落とさない JSON 全順序キーを返す。"""
    return json.dumps(
        row,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _normalize_rows(
    value: object,
    contract: ComparisonContract,
    route: str,
) -> tuple[tuple[dict[str, object], ...], tuple[Difference, ...]]:
    """行×全フィールドを検証して lossless な表現だけを揃える。"""
    if not isinstance(value, list):
        return (), (Difference(route, None, None, "invalid-output"),)
    field_map = {field.field: field for field in contract.fields}
    expected_fields = set(field_map)
    rows: list[dict[str, object]] = []
    differences: list[Difference] = []
    unify = "exact-numeric-representation" in contract.normalizations
    for row_index, raw_row in enumerate(value):
        row = _json_object(raw_row)
        if row is None:
            differences.append(Difference(route, row_index, None, "invalid-row"))
            continue
        observed_fields = set(row)
        for missing in sorted(expected_fields - observed_fields):
            differences.append(Difference(route, row_index, missing, "missing-field"))
        for unknown in sorted(observed_fields - expected_fields):
            differences.append(Difference(route, row_index, unknown, "unknown-field"))
        normalized: dict[str, object] = {}
        for field_name, field in field_map.items():
            if field_name not in row:
                continue
            normalized_value, issue = _normalize_value(row[field_name], field, unify)
            if issue is not None:
                differences.append(Difference(route, row_index, field_name, issue))
            normalized[field_name] = normalized_value
        rows.append(normalized)
    if "total-order" in contract.normalizations:
        rows.sort(key=_canonical_row)
    return tuple(rows), tuple(differences)


def _compare_outputs(
    left: object,
    right: object,
    contract: ComparisonContract,
    route: str,
) -> tuple[bool, tuple[Difference, ...]]:
    """二つの raw 出力を行×全フィールドで比較する。"""
    left_rows, left_issues = _normalize_rows(left, contract, route)
    right_rows, right_issues = _normalize_rows(right, contract, route)
    differences = [*left_issues, *right_issues]
    if left_issues or right_issues:
        return False, tuple(differences)
    if len(left_rows) != len(right_rows):
        differences.append(Difference(route, None, None, "row-count-mismatch"))
        return False, tuple(differences)
    fields = {field.field: field for field in contract.fields}
    for row_index, (left_row, right_row) in enumerate(
        zip(left_rows, right_rows, strict=True)
    ):
        for field_name, field in fields.items():
            if left_row[field_name] == right_row[field_name]:
                continue
            reason = "display-mismatch" if field.role == "display" else "value-mismatch"
            differences.append(Difference(route, row_index, field_name, reason))
    return not differences, tuple(differences)


def _compare_submission(
    submission: PathSubmission,
    contract: ComparisonContract,
) -> PathEvidence:
    """一提出の 5 判定を raw 出力から計算する。"""
    entrypoint_executed = submission.entrypoint_output is not _MISSING
    direct_target_executed = submission.direct_target_output is not _MISSING
    differences: list[Difference] = []

    if entrypoint_executed:
        entrypoint_equals, found = _compare_outputs(
            submission.entrypoint_output,
            submission.expected,
            contract,
            "entrypoint-expected",
        )
        differences.extend(found)
    else:
        entrypoint_equals = False
        differences.append(
            Difference("entrypoint-expected", None, None, "missing-execution")
        )

    if direct_target_executed:
        direct_target_equals, found = _compare_outputs(
            submission.direct_target_output,
            submission.expected,
            contract,
            "direct-target-expected",
        )
        differences.extend(found)
    else:
        direct_target_equals = False
        differences.append(
            Difference("direct-target-expected", None, None, "missing-execution")
        )

    if entrypoint_executed and direct_target_executed:
        paths_equal, found = _compare_outputs(
            submission.entrypoint_output,
            submission.direct_target_output,
            contract,
            "entrypoint-direct-target",
        )
        differences.extend(found)
    else:
        paths_equal = False
        differences.append(
            Difference(
                "entrypoint-direct-target",
                None,
                None,
                "missing-execution",
            )
        )
    return PathEvidence(
        key=submission.key,
        contract=contract,
        judgments=FiveJudgments(
            entrypoint_executed=entrypoint_executed,
            direct_target_executed=direct_target_executed,
            entrypoint_equals_expected=entrypoint_equals,
            direct_target_equals_expected=direct_target_equals,
            paths_equal=paths_equal,
        ),
        differences=tuple(differences),
    )


def compare_path_set(
    requirements: Iterable[PathKey],
    submissions: Iterable[PathSubmission],
    contracts: Mapping[str, ComparisonContract],
) -> PathMatchReport:
    """要求集合と採取済み提出を突合し、経路一致証跡を生成する。

    Args:
        requirements: 6 次元直積から導いた期待集合。
        submissions: ステップ 31 の収集経路が渡す raw 出力。
        contracts: 対象計算ごとの全比較面。

    Returns:
        集合差と 5 判定を保持する証跡。

    Raises:
        ValueError: 要求・提出が重複するか、比較契約が無い場合。
    """
    required = tuple(sorted(requirements))
    if len(required) != len(set(required)):
        raise ValueError("要求集合に重複がある")
    submitted_items = tuple(submissions)
    submitted_keys = [item.key for item in submitted_items]
    if len(submitted_keys) != len(set(submitted_keys)):
        raise ValueError("証跡集合に重複がある")
    required_set = set(required)
    submitted_set = set(submitted_keys)
    missing = tuple(sorted(required_set - submitted_set))
    unexpected = tuple(sorted(submitted_set - required_set))
    evidence: list[PathEvidence] = []
    for submission in sorted(submitted_items, key=lambda item: item.key):
        contract = contracts.get(submission.key.calculation)
        if contract is None:
            raise ValueError(f"比較契約が無い: {submission.key.calculation}")
        evidence.append(_compare_submission(submission, contract))
    return PathMatchReport(
        requirements=required,
        evidence=tuple(evidence),
        missing=missing,
        unexpected=unexpected,
    )


def submission_from_collected(
    evidence: LayerEvidence,
    *,
    expected: object,
    entrypoint_output: object,
    direct_target_output: object,
) -> PathSubmission:
    """ステップ 31 の収集証跡を再収集せず比較器の提出へ接続する。"""
    entrypoint = (
        entrypoint_output if evidence.judgments.entrypoint_executed else _MISSING
    )
    direct_target = (
        direct_target_output if evidence.judgments.direct_target_executed else _MISSING
    )
    return PathSubmission(
        key=PathKey(
            calculation=evidence.calculation,
            vector=evidence.vector,
            case=evidence.case,
            runner=evidence.provenance.runner.value,
            entrypoint_id=evidence.entrypoint_id,
            direct_target_id=evidence.direct_target_id,
        ),
        expected=expected,
        entrypoint_output=entrypoint,
        direct_target_output=direct_target,
    )


__all__ = [
    "ComparisonContract",
    "Difference",
    "FieldContract",
    "PathEvidence",
    "PathKey",
    "PathMatchReport",
    "PathSubmission",
    "compare_path_set",
    "submission_from_collected",
]
