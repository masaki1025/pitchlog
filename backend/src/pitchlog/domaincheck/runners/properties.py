"""典拠付き不変条件を生成 case へ適用する runner を提供する。

実行済みの判定は `ADR-003 D-11 ③ プロパティ層の証跡スキーマ` を
実装した `collect_layers` の結果だけを使う。等価性は完走証跡の存在だけを
確認し、比較そのものは行わない。
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from pitchlog.domaincheck.collect_layers import CollectionResult, LayerEvidence

_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9._-]*$")
_LINE_REFERENCE = re.compile(r":\d+")


class InvariantRunError(Exception):
    """不変条件層を契約どおり完走できないことを表す。"""


@dataclass(frozen=True, slots=True)
class AuthorityLocation:
    """条項 ID の逐語を正本内で特定する情報。

    Attributes:
        authority_id: 行番号を含まない条項 ID。
        source: リポジトリルートからの正本パス。
        section: 条項を含む Markdown 節見出し。
        verbatim: 指定節に存在すべき逐語。
    """

    authority_id: str
    source: str
    section: str
    verbatim: str


InvariantEvaluator = Callable[[object], bool]


@dataclass(frozen=True, slots=True)
class InvariantPredicate:
    """一つの規範述語とその典拠。

    Attributes:
        property_id: プロパティ証跡と結び付く述語 ID。
        authority_id: 述語を定める正本の条項 ID。
        evaluate: 一つの生成 case を判定する関数。
    """

    property_id: str
    authority_id: str
    evaluate: InvariantEvaluator

    def __post_init__(self) -> None:
        """空または不正な識別子を拒否する。"""
        if _IDENTIFIER.fullmatch(self.property_id) is None:
            raise ValueError(f"不正な property ID: {self.property_id}")
        if not self.authority_id or _LINE_REFERENCE.search(self.authority_id):
            raise ValueError(f"不正な条項 ID: {self.authority_id}")


@dataclass(frozen=True, slots=True)
class InvariantCase:
    """述語へ渡す一つの生成 case。

    Attributes:
        case_id: 生成 case の一意 ID。
        value: 述語が判定する生成値。
    """

    case_id: str
    value: object

    def __post_init__(self) -> None:
        """Case ID の空と不正文字を拒否する。"""
        if _IDENTIFIER.fullmatch(self.case_id) is None:
            raise ValueError(f"不正な case ID: {self.case_id}")


@dataclass(frozen=True, slots=True)
class InvariantEvaluation:
    """一つの述語を一つの case に適用した結果。"""

    property_id: str
    case_id: str
    passed: bool


@dataclass(frozen=True, slots=True)
class InvariantRunReport:
    """対象計算の不変条件層を完走した証跡。

    Attributes:
        calculation: 対象計算 ID。
        generated_case_ids: 実際に述語へ渡した case ID。
        evaluations: 述語と case の直積の評価結果。
        invariant_property_ids: 完走した不変条件テスト ID。
        equivalence_property_ids: 完走した等価性テスト ID。
    """

    calculation: str
    generated_case_ids: tuple[str, ...]
    evaluations: tuple[InvariantEvaluation, ...]
    invariant_property_ids: frozenset[str]
    equivalence_property_ids: frozenset[str]

    @property
    def complete(self) -> bool:
        """Case・両 property kind・全述語評価が揃った場合だけ真を返す。"""
        return (
            bool(self.generated_case_ids)
            and bool(self.evaluations)
            and bool(self.invariant_property_ids)
            and bool(self.equivalence_property_ids)
            and all(evaluation.passed for evaluation in self.evaluations)
        )


def _mapping(value: object, label: str) -> dict[str, object]:
    """文字列キーだけを持つ object を返す。"""
    if not isinstance(value, dict) or not all(
        isinstance(key, str) for key in value
    ):
        raise InvariantRunError(f"{label} が object でない")
    return cast(dict[str, object], value)


def _array(value: object, label: str) -> list[object]:
    """Array を返す。"""
    if not isinstance(value, list):
        raise InvariantRunError(f"{label} が array でない")
    return value


def _string(value: object, label: str) -> str:
    """空でない文字列を返す。"""
    if not isinstance(value, str) or not value:
        raise InvariantRunError(f"{label} が空でない文字列でない")
    return value


def authorities_from_registry(
    registry: Mapping[str, object],
) -> dict[str, AuthorityLocation]:
    """ステップ 3 の条項台帳から逐語位置の索引を作る。

    Args:
        registry: `step-authorities.json` の内容。

    Returns:
        条項 ID をキーとする逐語位置。

    Raises:
        InvariantRunError: 台帳のキー集合、型、ID が不正な場合。
    """
    rows = _array(registry.get("authorityCatalog"), "authorityCatalog")
    authorities: dict[str, AuthorityLocation] = {}
    for index, raw_row in enumerate(rows):
        row = _mapping(raw_row, f"authorityCatalog[{index}]")
        if set(row) != {"id", "source", "section", "verbatim"}:
            raise InvariantRunError("authorityCatalog のキー集合が不正")
        authority_id = _string(row.get("id"), "authority.id")
        if _LINE_REFERENCE.search(authority_id):
            raise InvariantRunError(f"条項 ID に行番号参照がある: {authority_id}")
        if authority_id in authorities:
            raise InvariantRunError(f"条項 ID が重複: {authority_id}")
        authorities[authority_id] = AuthorityLocation(
            authority_id=authority_id,
            source=_string(row.get("source"), "authority.source"),
            section=_string(row.get("section"), "authority.section"),
            verbatim=_string(row.get("verbatim"), "authority.verbatim"),
        )
    if not authorities:
        raise InvariantRunError("authorityCatalog が空")
    return authorities


def _section_text(source_text: str, heading: str) -> str:
    """Markdown 正本から指定見出しに属する本文を取り出す。"""
    lines = source_text.splitlines()
    try:
        start = lines.index(heading)
    except ValueError as error:
        raise InvariantRunError(f"正本に節見出しが無い: {heading}") from error
    level = len(heading) - len(heading.lstrip("#"))
    end = len(lines)
    for index in range(start + 1, len(lines)):
        matched = re.match(r"^(#+)\s", lines[index])
        if matched is not None and len(matched.group(1)) <= level:
            end = index
            break
    return "\n".join(lines[start:end])


def _authority_source(root: Path, location: AuthorityLocation) -> str:
    """リポジトリ内の正本だけを読み、指定節を返す。"""
    resolved_root = root.resolve()
    source_path = (resolved_root / location.source).resolve()
    try:
        source_path.relative_to(resolved_root)
    except ValueError as error:
        raise InvariantRunError(
            f"正本パスがリポジトリ外を指す: {location.source}"
        ) from error
    try:
        source_text = source_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise InvariantRunError(
            f"正本を読めない: {location.source}: {error}"
        ) from error
    return _section_text(source_text, location.section)


def validate_predicate_authorities(
    root: Path,
    predicates: Iterable[InvariantPredicate],
    authorities: Mapping[str, AuthorityLocation],
) -> None:
    """全述語の条項 ID と逐語が正本に存在することを検査する。"""
    predicate_items = tuple(predicates)
    if not predicate_items:
        raise InvariantRunError("不変条件カタログが空")
    for predicate in predicate_items:
        location = authorities.get(predicate.authority_id)
        if location is None:
            raise InvariantRunError(
                f"述語の条項 ID が台帳に無い: {predicate.authority_id}"
            )
        if location.authority_id != predicate.authority_id:
            raise InvariantRunError("条項索引の ID がキーと一致しない")
        section = _authority_source(root, location)
        if location.verbatim not in section:
            raise InvariantRunError(
                f"条項の逐語が正本に無い: {predicate.authority_id}"
            )


def _completed_evidence(
    calculation: str,
    collection: CollectionResult,
) -> tuple[LayerEvidence, ...]:
    """既存収集器が実行済みと認めた対象計算の証跡だけを返す。"""
    if not collection.complete:
        reasons = sorted(item.reason for item in collection.rejected)
        raise InvariantRunError(
            "層別収集器が実行済みと認めない証跡がある: "
            f"{reasons!r}"
        )
    evidence = tuple(
        item for item in collection.evidence if item.calculation == calculation
    )
    if not evidence:
        raise InvariantRunError(f"対象計算の完走証跡が無い: {calculation}")
    return evidence


def _property_kind_sets(
    evidence: Iterable[LayerEvidence],
) -> tuple[frozenset[str], frozenset[str]]:
    """完走証跡を不変条件と等価性の ID 集合へ分ける。"""
    invariant_ids = frozenset(
        item.property_id for item in evidence if item.property_kind == "invariant"
    )
    equivalence_ids = frozenset(
        item.property_id for item in evidence if item.property_kind == "equivalence"
    )
    if not invariant_ids or not equivalence_ids:
        raise InvariantRunError(
            "invariant と equivalence の双方に 1 件以上の完走が必要"
        )
    return invariant_ids, equivalence_ids


def run_invariants(
    *,
    root: Path,
    calculation: str,
    predicates: Iterable[InvariantPredicate],
    cases: Iterable[InvariantCase],
    collection: CollectionResult,
    authorities: Mapping[str, AuthorityLocation],
) -> InvariantRunReport:
    """典拠付き述語を全生成 case に適用し、両 property kind を検査する。

    Args:
        root: 正本を含むリポジトリルート。
        calculation: 対象計算 ID。
        predicates: 独立カタログから得た典拠付き述語。
        cases: ステップ 34・35 が生成した case。
        collection: ステップ 31 の層別収集結果。
        authorities: 条項 ID と正本内の逐語位置。

    Returns:
        述語と case の全評価および両 property kind の完走証跡。

    Raises:
        InvariantRunError: 典拠、証跡、述語評価のいずれかが不適合な場合。
    """
    if _IDENTIFIER.fullmatch(calculation) is None:
        raise InvariantRunError(f"不正な calculation ID: {calculation}")
    predicate_items = tuple(predicates)
    predicate_ids = [item.property_id for item in predicate_items]
    if not predicate_items:
        raise InvariantRunError("不変条件カタログが空")
    if len(predicate_ids) != len(set(predicate_ids)):
        raise InvariantRunError("不変条件カタログの property ID が重複")
    case_items = tuple(cases)
    case_ids = [item.case_id for item in case_items]
    if not case_items:
        raise InvariantRunError("生成 case が 0 件")
    if len(case_ids) != len(set(case_ids)):
        raise InvariantRunError("生成 case ID が重複")

    validate_predicate_authorities(root, predicate_items, authorities)
    evidence = _completed_evidence(calculation, collection)
    invariant_ids, equivalence_ids = _property_kind_sets(evidence)
    missing_predicate_evidence = set(predicate_ids) - invariant_ids
    if missing_predicate_evidence:
        raise InvariantRunError(
            "述語の invariant 完走証跡が無い: "
            f"{sorted(missing_predicate_evidence)!r}"
        )
    for predicate_id in predicate_ids:
        observed_counts = {
            item.generated_cases
            for item in evidence
            if item.property_kind == "invariant"
            and item.property_id == predicate_id
        }
        if observed_counts != {len(case_items)}:
            raise InvariantRunError(
                f"述語 {predicate_id} の生成 case 数が実測と一致しない: "
                f"{sorted(observed_counts)!r}"
            )

    evaluations: list[InvariantEvaluation] = []
    failures: list[str] = []
    for predicate in predicate_items:
        for case in case_items:
            try:
                passed = predicate.evaluate(case.value)
            except Exception as error:
                raise InvariantRunError(
                    f"述語を評価できない: {predicate.property_id}/{case.case_id}"
                ) from error
            if not isinstance(passed, bool):
                raise InvariantRunError(
                    f"述語が boolean を返さない: {predicate.property_id}"
                )
            evaluations.append(
                InvariantEvaluation(
                    property_id=predicate.property_id,
                    case_id=case.case_id,
                    passed=passed,
                )
            )
            if not passed:
                failures.append(f"{predicate.property_id}/{case.case_id}")
    if failures:
        raise InvariantRunError(f"不変条件違反: {sorted(failures)!r}")
    report = InvariantRunReport(
        calculation=calculation,
        generated_case_ids=tuple(case_ids),
        evaluations=tuple(evaluations),
        invariant_property_ids=invariant_ids,
        equivalence_property_ids=equivalence_ids,
    )
    if not report.complete:
        raise InvariantRunError("不変条件 runner が完走しなかった")
    return report


__all__ = [
    "AuthorityLocation",
    "InvariantCase",
    "InvariantEvaluation",
    "InvariantPredicate",
    "InvariantRunError",
    "InvariantRunReport",
    "authorities_from_registry",
    "run_invariants",
    "validate_predicate_authorities",
]
