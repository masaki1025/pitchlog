"""NFR-018 (e) の逐語から BOOT 条項 ID の母集合を逆引きする。"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from pitchlog.domaincheck.cli import (
    CheckerExecutionError,
    CheckerViolation,
    exact_set_difference,
    read_json,
)

BOOT_CLAUSES_ASSET = Path("backend/domain/boot-clauses.json")
EXPECTED_CLAUSE_COUNT = 12

_ROOT_KEYS = frozenset(
    {"schemaVersion", "generatedBy", "derivation", "clauses"}
)
_DERIVATION_KEYS = frozenset(
    {
        "source",
        "section",
        "startMarker",
        "endMarker",
        "clauseDeclarationPattern",
        "clauseRangeRule",
    }
)
_CLAUSE_KEYS = frozenset(
    {
        "id",
        "authorityId",
        "verbatim",
        "violationDetection",
        "negativeCaseIds",
        "positiveCaseIds",
    }
)
_DETECTION_KEYS = frozenset({"kind", "criterionAuthority"})
_CLAUSE_RANGE_RULE = "from-declaration-to-next-declaration-or-subsection-end"


@dataclass(frozen=True, slots=True)
class DerivedClause:
    """正本の逐語から逆引きした 1 条項。

    Attributes:
        identifier: `BOOT-` から始まる条項 ID。
        verbatim: ID を囲む正本上の逐語。
        normative_text: 当該宣言から次の条項宣言直前までの規範本文。
    """

    identifier: str
    verbatim: str
    normative_text: str


def _object(value: object, label: str) -> dict[str, object]:
    """文字列キーだけを持つ JSON object を返す。"""
    if not isinstance(value, dict) or not all(
        isinstance(key, str) for key in value
    ):
        raise CheckerExecutionError(f"{label}が JSON object でない")
    return cast(dict[str, object], value)


def _array(value: object, label: str) -> list[object]:
    """JSON array を返す。"""
    if not isinstance(value, list):
        raise CheckerExecutionError(f"{label}が JSON array でない")
    return cast(list[object], value)


def _string(value: object, label: str) -> str:
    """空でない文字列を返す。"""
    if not isinstance(value, str) or not value:
        raise CheckerExecutionError(f"{label}が空でない文字列でない")
    return value


def _exact_keys(
    value: Mapping[str, object],
    expected: frozenset[str],
    label: str,
) -> None:
    """JSON object のキー集合が期待集合と等しいことを要求する。"""
    observed = frozenset(value)
    difference = exact_set_difference(expected, observed)
    if not difference.matches:
        raise CheckerViolation(
            f"{label}のキー集合が不一致: "
            f"不足={sorted(difference.missing)!r}, "
            f"未登録={sorted(difference.unexpected)!r}"
        )


def _section_text(source_text: str, heading: str) -> str:
    """指定した Markdown 見出しの節だけを切り出す。"""
    lines = source_text.splitlines()
    try:
        start = lines.index(heading)
    except ValueError as error:
        raise CheckerExecutionError(f"正本に節見出しがない: {heading}") from error
    level = len(heading) - len(heading.lstrip("#"))
    end = len(lines)
    for index in range(start + 1, len(lines)):
        match = re.match(r"^(#{1,6})\s", lines[index])
        if match is not None and len(match.group(1)) <= level:
            end = index
            break
    return "\n".join(lines[start:end])


def _subsection_text(
    section: str,
    start_marker: str,
    end_marker: str,
) -> str:
    """開始を含み終了を含まない規則で NFR-018 (e) だけを切り出す。"""
    start_count = section.count(start_marker)
    end_count = section.count(end_marker)
    if start_count != 1 or end_count != 1:
        raise CheckerExecutionError(
            "NFR-018 (e) の範囲マーカーが一意でない: "
            f"開始={start_count}, 終了={end_count}"
        )
    start = section.index(start_marker)
    end = section.index(end_marker, start + len(start_marker))
    if start >= end:
        raise CheckerExecutionError("NFR-018 (e) の範囲マーカー順が不正")
    return section[start:end]


def _derivation(asset: object) -> dict[str, object]:
    """対応表から厳密な逆引き規則を返す。"""
    root = _object(asset, "boot-clauses")
    _exact_keys(root, _ROOT_KEYS, "boot-clauses")
    if root.get("schemaVersion") != 1:
        raise CheckerViolation("boot-clauses.schemaVersionが 1 でない")
    if root.get("generatedBy") != "pitchlog.domaincheck.boot.clauses":
        raise CheckerViolation("boot-clauses.generatedByが逆引き器を指していない")
    derivation = _object(root.get("derivation"), "boot-clauses.derivation")
    _exact_keys(derivation, _DERIVATION_KEYS, "boot-clauses.derivation")
    if derivation.get("clauseRangeRule") != _CLAUSE_RANGE_RULE:
        raise CheckerViolation("条項範囲の切り出し規則が不正")
    return derivation


def derive_clauses(source_text: str, asset: object) -> tuple[DerivedClause, ...]:
    """資産の非列挙規則に従い正本から条項 ID と本文を逆引きする。

    Args:
        source_text: 要件書の UTF-8 本文。
        asset: 抽出範囲と一般化パターンを宣言した対応表。

    Returns:
        正本に現れる順序の条項 ID、逐語、規範本文。

    Raises:
        CheckerExecutionError: 節、範囲、正規表現を解釈できない場合。
        CheckerViolation: ID が重複する場合。
    """
    derivation = _derivation(asset)
    section = _section_text(
        source_text,
        _string(derivation.get("section"), "derivation.section"),
    )
    subsection = _subsection_text(
        section,
        _string(derivation.get("startMarker"), "derivation.startMarker"),
        _string(derivation.get("endMarker"), "derivation.endMarker"),
    )
    pattern_text = _string(
        derivation.get("clauseDeclarationPattern"),
        "derivation.clauseDeclarationPattern",
    )
    try:
        pattern = re.compile(pattern_text)
    except re.error as error:
        raise CheckerExecutionError(f"条項 ID 抽出 regex が不正: {error}") from error
    if "id" not in pattern.groupindex:
        raise CheckerExecutionError("条項 ID 抽出 regex に名前付き id 群がない")
    matches = list(pattern.finditer(subsection))
    clauses: list[DerivedClause] = []
    for index, match in enumerate(matches):
        identifier = match.group("id")
        end = (
            matches[index + 1].start()
            if index + 1 < len(matches)
            else len(subsection)
        )
        normative_text = subsection[match.start() : end].strip()
        clauses.append(
            DerivedClause(
                identifier=identifier,
                verbatim=f"`{identifier}`",
                normative_text=normative_text,
            )
        )
    identifiers = [clause.identifier for clause in clauses]
    if len(identifiers) != len(set(identifiers)):
        raise CheckerViolation("NFR-018 (e) の条項 ID が重複している")
    return tuple(clauses)


def _case_ids(value: object, label: str) -> tuple[str, ...]:
    """将来追記できる負例・正例 ID の型と一意性を検査する。"""
    raw_values = _array(value, label)
    values = tuple(_string(item, f"{label}[]") for item in raw_values)
    if len(values) != len(set(values)):
        raise CheckerViolation(f"{label}に重複がある")
    return values


def validate_registry(source_text: str, asset: object) -> tuple[DerivedClause, ...]:
    """逆引き母集合と条項対応表が全件一致することを検査する。

    負例・正例 ID は後続ステップで増える可変欄なので、現在値ではなく欄の存在、
    型、一意性だけを検査する。

    Args:
        source_text: 要件書の UTF-8 本文。
        asset: 検査する条項対応表。

    Returns:
        正本から独立導出した条項列。

    Raises:
        CheckerExecutionError: 資産または正本を解釈できない場合。
        CheckerViolation: 母集合、逐語、または表の形が不一致の場合。
    """
    derived = derive_clauses(source_text, asset)
    if len(derived) != EXPECTED_CLAUSE_COUNT:
        raise CheckerViolation(
            "NFR-018 (e) の BOOT 条項数が契約値と異なる: "
            f"実測={len(derived)}, 期待={EXPECTED_CLAUSE_COUNT}"
        )
    root = _object(asset, "boot-clauses")
    raw_entries = _array(root.get("clauses"), "boot-clauses.clauses")
    entries = [
        _object(raw_entry, f"boot-clauses.clauses[{index}]")
        for index, raw_entry in enumerate(raw_entries)
    ]
    for index, entry in enumerate(entries):
        label = f"boot-clauses.clauses[{index}]"
        _exact_keys(entry, _CLAUSE_KEYS, label)
        identifier = _string(entry.get("id"), f"{label}.id")
        authority = f"NFR-018 (e) {identifier}"
        if entry.get("authorityId") != authority:
            raise CheckerViolation(f"{label}.authorityIdが条項 ID と一致しない")
        if entry.get("verbatim") != f"`{identifier}`":
            raise CheckerViolation(f"{label}.verbatimが条項 ID と一致しない")
        detection = _object(
            entry.get("violationDetection"),
            f"{label}.violationDetection",
        )
        _exact_keys(detection, _DETECTION_KEYS, f"{label}.violationDetection")
        if detection.get("kind") != "clause-violation":
            raise CheckerViolation(f"{label}.violationDetection.kindが不正")
        if detection.get("criterionAuthority") != authority:
            raise CheckerViolation(
                f"{label}.violationDetection.criterionAuthorityが不正"
            )
        _case_ids(entry.get("negativeCaseIds"), f"{label}.negativeCaseIds")
        _case_ids(entry.get("positiveCaseIds"), f"{label}.positiveCaseIds")

    derived_ids = tuple(clause.identifier for clause in derived)
    observed_ids = tuple(
        _string(entry.get("id"), f"clauses[{index}].id")
        for index, entry in enumerate(entries)
    )
    if derived_ids != observed_ids:
        difference = exact_set_difference(
            frozenset(derived_ids),
            frozenset(observed_ids),
        )
        raise CheckerViolation(
            "正本からの逆引きと条項対応表が不一致: "
            f"不足={sorted(difference.missing)!r}, "
            f"未登録={sorted(difference.unexpected)!r}, "
            f"順序一致={derived_ids == observed_ids}"
        )
    for index, (clause, entry) in enumerate(
        zip(derived, entries, strict=True)
    ):
        verbatim = _string(entry.get("verbatim"), f"clauses[{index}].verbatim")
        if verbatim not in clause.normative_text:
            raise CheckerViolation(
                f"正本の条項範囲に逐語がない: {clause.identifier}"
            )
    return derived


def load_and_validate_registry(root: Path) -> tuple[DerivedClause, ...]:
    """リポジトリの正本と固定資産を読み、逆引き結果を検証する。"""
    resolved_root = root.resolve()
    asset = read_json(resolved_root / BOOT_CLAUSES_ASSET)
    derivation = _derivation(asset)
    source_path = Path(
        _string(derivation.get("source"), "derivation.source")
    )
    if source_path.is_absolute() or ".." in source_path.parts:
        raise CheckerExecutionError("derivation.sourceが安全な相対パスでない")
    try:
        source_text = (resolved_root / source_path).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        message = f"正本を読めない: {source_path}: {error}"
        raise CheckerExecutionError(message) from error
    return validate_registry(source_text, asset)
