"""NFR-018 とマニフェスト schema から封印集合を導出する。

対象 ID は改名で別要素にならないよう列挙位置から作る。並べ替えによる ID と
対象名の再束縛は `derivedInputs.targets` の対応を資産に残し、後続の固定 SHA
封印が資産内容の変化として検出できるようにする。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path

from pitchlog.domaincheck.cli import (
    EXIT_CONFORMING,
    EXIT_INDETERMINATE,
    EXIT_NONCONFORMING,
    CheckerExecutionError,
    canonical_json,
    read_json,
)

_REQUIREMENTS_PATH = Path("docs/requirements/requirements-pitchlog-2026-07-22.md")
_CHECK_SETS_PATH = Path("backend/domain/check-sets.json")
_MANIFEST_SCHEMA_PATH = Path("backend/domain/manifest.schema.json")
_BOOT_SEAL_PATH = Path("backend/domain/boot-seal.json")
_CIRCLED_NUMBER = re.compile(r"[①-⑳]")


class SealConstructor(StrEnum):
    """封印要素の代数的型を構成する構成子。"""

    DECLARATION_ABSENCE = "declaration_absence"
    MECHANISM_ABSENCE = "mechanism_absence"


_CONSTRUCTOR_ARGUMENTS = {
    SealConstructor.DECLARATION_ABSENCE: ["target", "field"],
    SealConstructor.MECHANISM_ABSENCE: ["bClause"],
}


def _mapping(value: object, label: str) -> dict[str, object]:
    """文字列キーの object を返す。"""
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise CheckerExecutionError(f"{label} は object でなければならない")
    return value


def _list(value: object, label: str) -> list[object]:
    """Array を返す。"""
    if not isinstance(value, list):
        raise CheckerExecutionError(f"{label} は array でなければならない")
    return value


def _string(value: object, label: str) -> str:
    """空でない文字列を返す。"""
    if not isinstance(value, str) or not value:
        raise CheckerExecutionError(f"{label} は空でない文字列でなければならない")
    return value


def _string_list(value: object, label: str) -> list[str]:
    """空でない文字列だけからなる array を返す。"""
    values = _list(value, label)
    if not values or not all(isinstance(item, str) and item for item in values):
        raise CheckerExecutionError(
            f"{label} は空でない文字列だけからなる array でなければならない"
        )
    return [_string(item, label) for item in values]


def _section_text(source_text: str, heading: str) -> str:
    """指定した Markdown 節を見出し階層に従って取り出す。"""
    lines = source_text.splitlines()
    try:
        start = lines.index(heading)
    except ValueError as error:
        raise CheckerExecutionError(f"正本に節見出しがない: {heading}") from error
    level = len(heading) - len(heading.lstrip("#"))
    end = len(lines)
    for index in range(start + 1, len(lines)):
        match = re.match(r"^(#+)\s", lines[index])
        if match is not None and len(match.group(1)) <= level:
            end = index
            break
    return "\n".join(lines[start:end])


def _split_top_level(value: str, separators: list[str]) -> list[str]:
    """括弧の外側にある区切りだけで日本語の列挙を分解する。"""
    opening = {"(": ")", "（": "）"}
    closing = set(opening.values())
    stack: list[str] = []
    parts: list[str] = []
    start = 0
    index = 0
    ordered = sorted(separators, key=len, reverse=True)
    while index < len(value):
        character = value[index]
        if character in opening:
            stack.append(opening[character])
            index += 1
            continue
        if character in closing:
            if stack and character == stack[-1]:
                stack.pop()
            index += 1
            continue
        if not stack:
            separator = next(
                (item for item in ordered if value.startswith(item, index)), None
            )
            if separator is not None:
                parts.append(value[start:index])
                index += len(separator)
                start = index
                continue
        index += 1
    parts.append(value[start:])
    return [part.strip() for part in parts if part.strip()]


def _without_detail(value: str) -> str:
    """列挙要素から Markdown 装飾と括弧内の説明を除く。"""
    plain = value.replace("**", "").strip()
    positions = [
        position for mark in ("（", "(") if (position := plain.find(mark)) >= 0
    ]
    if positions:
        plain = plain[: min(positions)]
    return plain.strip(" 。")


def _top_level_circled_segments(value: str) -> list[tuple[str, str]]:
    """括弧外の丸数字と後続文を順に抽出する。"""
    opening = {"(": ")", "（": "）"}
    closing = set(opening.values())
    stack: list[str] = []
    markers: list[tuple[int, str]] = []
    for index, character in enumerate(value):
        if character in opening:
            stack.append(opening[character])
        elif character in closing:
            if stack and character == stack[-1]:
                stack.pop()
        elif not stack and _CIRCLED_NUMBER.fullmatch(character):
            markers.append((index, character))
    result: list[tuple[str, str]] = []
    for marker_index, (start, marker) in enumerate(markers):
        if marker_index + 1 < len(markers):
            end = markers[marker_index + 1][0]
        else:
            end = len(value)
        result.append((marker, value[start + 1 : end]))
    return result


def _ordinal(marker: str) -> int:
    """丸数字を正の整数へ変換する。"""
    try:
        ordinal = int(unicodedata.numeric(marker))
    except (TypeError, ValueError) as error:
        raise CheckerExecutionError(f"丸数字を解釈できない: {marker}") from error
    if ordinal < 1:
        raise CheckerExecutionError(f"丸数字が正でない: {marker}")
    return ordinal


def _target_rules(check_sets: Mapping[str, object]) -> dict[str, dict[str, object]]:
    """対象導出規則を group ID ごとの対応にする。"""
    derivation = _mapping(check_sets.get("targetDerivation"), "targetDerivation")
    if derivation.get("combination") != "set-union":
        raise CheckerExecutionError("対象集合の結合規則が set-union でない")
    rows = _list(derivation.get("groups"), "targetDerivation.groups")
    rules: dict[str, dict[str, object]] = {}
    for index, row in enumerate(rows):
        rule = _mapping(row, f"targetDerivation.groups[{index}]")
        rule_id = _string(rule.get("id"), f"targetDerivation.groups[{index}].id")
        if rule_id in rules:
            raise CheckerExecutionError(f"対象導出規則が重複している: {rule_id}")
        rules[rule_id] = rule
    if set(rules) != {"alpha", "beta"}:
        raise CheckerExecutionError("対象導出規則は alpha と beta でなければならない")
    return rules


def derive_targets(
    requirements_text: str, check_sets: Mapping[str, object]
) -> list[dict[str, object]]:
    """NFR-018 対象欄を規則どおりに読み、位置由来の安定 ID を付ける。

    Args:
        requirements_text: 要件書の全文。
        check_sets: 検査集合資産。

    Returns:
        対象名と位置に基づく安定 ID の組。対応自体を返すことで、並べ替え時の
        再束縛を生成資産の差分として残す。
    """
    derivation = _mapping(check_sets.get("targetDerivation"), "targetDerivation")
    section = _section_text(
        requirements_text,
        _string(derivation.get("section"), "targetDerivation.section"),
    )
    rules = _target_rules(check_sets)
    alpha_rule = rules["alpha"]
    alpha_marker = _string(alpha_rule.get("marker"), "alpha.marker")
    alpha_line = next(
        (
            line
            for line in section.splitlines()
            if line.lstrip().startswith(f"- **{alpha_marker}") and ":" in line
        ),
        None,
    )
    if alpha_line is None:
        raise CheckerExecutionError("NFR-018 対象欄の alpha 列挙がない")
    alpha_body = alpha_line.split(":", maxsplit=1)[1]
    alpha_body = alpha_body.split("。**NFR-019(a)", maxsplit=1)[0]
    separators = _string_list(alpha_rule.get("separators"), "alpha.separators")
    alpha_names = [
        _without_detail(value) for value in _split_top_level(alpha_body, separators)
    ]

    beta_rule = rules["beta"]
    beta_marker = _string(beta_rule.get("marker"), "beta.marker")
    beta_line = next(
        (
            line
            for line in section.splitlines()
            if line.lstrip().startswith(f"- **{beta_marker}") and "①" in line
        ),
        None,
    )
    if beta_line is None:
        raise CheckerExecutionError("NFR-018 対象欄の beta 列挙がない")
    beta_body = beta_line[beta_line.index("①") :]
    beta_body = beta_body.split("。**いずれも", maxsplit=1)[0]
    beta_segments = _top_level_circled_segments(beta_body)

    candidates: list[dict[str, object]] = [
        {
            "id": f"nfr018-alpha-{str(index).zfill(2)}",
            "group": "alpha",
            "ordinal": index,
            "name": name,
        }
        for index, name in enumerate(alpha_names, start=1)
    ]
    for marker, value in beta_segments:
        ordinal = _ordinal(marker)
        candidates.append(
            {
                "id": f"nfr018-beta-{str(ordinal).zfill(2)}",
                "group": "beta",
                "ordinal": ordinal,
                "name": _without_detail(value),
            }
        )

    targets: list[dict[str, object]] = []
    seen_names: set[str] = set()
    for candidate in candidates:
        name = _string(candidate.get("name"), "target.name")
        if name in seen_names:
            continue
        seen_names.add(name)
        targets.append(candidate)
    ids = [_string(row["id"], "target.id") for row in targets]
    if len(ids) != len(set(ids)):
        raise CheckerExecutionError("対象 ID または対象名が一対一でない")
    return targets


def derive_manifest_fields(
    manifest_schema: Mapping[str, object],
) -> dict[str, list[str]]:
    """マニフェスト schema から 2 層の宣言名を導出する。

    Args:
        manifest_schema: マニフェストの JSON Schema。

    Returns:
        対象計算層とトップレベル層の宣言名。
    """
    top_required = _string_list(manifest_schema.get("required"), "required")
    top_properties = _mapping(manifest_schema.get("properties"), "properties")
    definitions = _mapping(manifest_schema.get("$defs"), "$defs")
    calculation = _mapping(definitions.get("Calculation"), "$defs.Calculation")
    calculation_required = _string_list(
        calculation.get("required"), "$defs.Calculation.required"
    )
    calculation_properties = _mapping(
        calculation.get("properties"), "$defs.Calculation.properties"
    )
    if set(top_required) != set(top_properties):
        message = "トップレベル宣言の required と properties が不一致"
        raise CheckerExecutionError(message)
    if set(calculation_required) != set(calculation_properties):
        raise CheckerExecutionError("対象計算宣言の required と properties が不一致")
    return {
        "perCalculation": calculation_required,
        "topLevel": top_required,
    }


def derive_b_clauses(
    requirements_text: str, section_heading: str
) -> list[dict[str, object]]:
    """NFR-018 (b) の丸数字小項目を一対一で導出する。

    Args:
        requirements_text: 要件書の全文。
        section_heading: NFR-018 の節見出し。

    Returns:
        (b) 小項目の安定 ID、丸数字、名称。
    """
    section = _section_text(requirements_text, section_heading)
    lines = section.splitlines()
    start = next(
        (index for index, line in enumerate(lines) if line.startswith("  - **(b) ")),
        None,
    )
    if start is None:
        raise CheckerExecutionError("NFR-018 (b) がない")
    end = next(
        (
            index
            for index in range(start + 1, len(lines))
            if re.match(r"^  - \*\*\([a-z]\) ", lines[index])
        ),
        len(lines),
    )
    clauses: list[dict[str, object]] = []
    for line in lines[start + 1 : end]:
        match = re.match(r"^    - \*\*([①-⑳])\s+(.+?)\*\*", line)
        if match is None:
            continue
        marker, name = match.groups()
        ordinal = _ordinal(marker)
        clauses.append(
            {
                "id": f"nfr018-b-{ordinal}",
                "marker": marker,
                "ordinal": ordinal,
                "name": name,
            }
        )
    ids = [_string(row["id"], "bClause.id") for row in clauses]
    if not ids or len(ids) != len(set(ids)):
        raise CheckerExecutionError("NFR-018 (b) の小項目が空または重複している")
    return clauses


def declaration_absence_key(target: str, field: str) -> str:
    """宣言不在要素の正規キーを返す。"""
    return f"{SealConstructor.DECLARATION_ABSENCE}({target},{field})"


def mechanism_absence_key(b_clause: str) -> str:
    """判定機構不在要素の正規キーを返す。"""
    return f"{SealConstructor.MECHANISM_ABSENCE}({b_clause})"


def _declaration_element(target: str, field: str, scope: str) -> dict[str, object]:
    """D-11 由来の宣言不在要素を作る。"""
    return {
        "id": f"{target}/{field}",
        "origin": "d11",
        "constructor": SealConstructor.DECLARATION_ABSENCE,
        "arguments": {"target": target, "field": field},
        "canonicalKey": declaration_absence_key(target, field),
        "resolutionPredicate": {
            "operator": "raw-check-conforms",
            "check": "manifest-declaration",
            "scope": scope,
            "target": target,
            "field": field,
        },
    }


def _mechanism_element(clause: Mapping[str, object]) -> dict[str, object]:
    """NFR-018 (b) 由来の判定機構不在要素を作る。"""
    clause_id = _string(clause.get("id"), "bClause.id")
    return {
        "id": f"{clause_id}/mechanism",
        "origin": "nfr018-b",
        "constructor": SealConstructor.MECHANISM_ABSENCE,
        "arguments": {"bClause": clause_id},
        "canonicalKey": mechanism_absence_key(clause_id),
        "resolutionPredicate": {
            "operator": "raw-check-conforms",
            "check": "nfr018-b-mechanism",
            "bClause": clause_id,
        },
    }


def derive_boot_seal(root: Path) -> dict[str, object]:
    """正本と schema の実測から封印集合全体を導出する。

    Args:
        root: リポジトリルート。

    Returns:
        Canonical JSON に書き出せる封印集合資産。

    Raises:
        CheckerExecutionError: 入力資産が読めないか導出規則に適合しない場合。
    """
    requirements_file = root / _REQUIREMENTS_PATH
    try:
        requirements_text = requirements_file.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise CheckerExecutionError(
            f"要件書を読めない: {requirements_file}: {error}"
        ) from error
    check_sets = _mapping(read_json(root / _CHECK_SETS_PATH), "check-sets")
    manifest_schema = _mapping(
        read_json(root / _MANIFEST_SCHEMA_PATH), "manifest.schema"
    )
    derivation = _mapping(check_sets.get("targetDerivation"), "targetDerivation")
    section_heading = _string(derivation.get("section"), "targetDerivation.section")
    targets = derive_targets(requirements_text, check_sets)
    fields = derive_manifest_fields(manifest_schema)
    clauses = derive_b_clauses(requirements_text, section_heading)

    d11_elements = [
        _declaration_element(
            _string(target.get("id"), "target.id"), field, "per-calculation"
        )
        for target in targets
        for field in fields["perCalculation"]
    ]
    d11_elements.extend(
        _declaration_element("manifest", field, "top-level")
        for field in fields["topLevel"]
    )
    b_elements = [_mechanism_element(clause) for clause in clauses]
    elements = [*d11_elements, *b_elements]
    ids = [_string(element.get("id"), "element.id") for element in elements]
    keys = [
        _string(element.get("canonicalKey"), "element.canonicalKey")
        for element in elements
    ]
    if len(ids) != len(set(ids)):
        raise CheckerExecutionError("封印要素 ID が一意でない")
    if len(keys) != len(set(keys)):
        raise CheckerExecutionError("封印要素の正規キーが一意でない")

    constructors = [
        {
            "name": constructor.value,
            "arguments": _CONSTRUCTOR_ARGUMENTS[constructor],
        }
        for constructor in SealConstructor
    ]
    return {
        "schemaVersion": 1,
        "generatedBy": "pitchlog.domaincheck.boot_seal_derive",
        "sources": {
            "requirements": {
                "path": _REQUIREMENTS_PATH.as_posix(),
                "section": section_heading,
                "authorities": [
                    "NFR-018 対象欄",
                    *[
                        f"NFR-018 (b){_string(clause.get('marker'), 'bClause.marker')}"
                        for clause in clauses
                    ],
                ],
            },
            "targetRule": {
                "path": _CHECK_SETS_PATH.as_posix(),
                "selector": "targetDerivation",
            },
            "declarationNames": {
                "path": _MANIFEST_SCHEMA_PATH.as_posix(),
                "selectors": ["properties", "$defs.Calculation.properties"],
                "authority": "ADR-003 D-11 ③ 構成の完全性",
            },
        },
        "algebraicType": {"constructors": constructors},
        "derivedInputs": {
            "targets": targets,
            "declarationFields": fields,
            "bClauses": clauses,
        },
        "counts": {
            "total": len(elements),
            "d11": len(d11_elements),
            "b": len(b_elements),
        },
        "elements": elements,
    }


def _default_root() -> Path:
    """モジュール位置からリポジトリルートを返す。"""
    return Path(__file__).resolve().parents[4]


def _parser() -> argparse.ArgumentParser:
    """封印集合導出器の引数パーサを返す。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=_default_root())
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--write", action="store_true")
    modes.add_argument("--check", action="store_true")
    return parser


def _write_asset(path: Path, value: object) -> None:
    """人間が逐行確認できる 2 空白インデントの JSON 資産を書く。"""
    try:
        serialized = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
        path.write_text(serialized, encoding="utf-8")
    except (OSError, TypeError, ValueError) as error:
        message = f"封印集合資産を書けない: {path}: {error}"
        raise CheckerExecutionError(message) from error


def main(argv: list[str] | None = None) -> int:
    """封印集合を表示、生成、または既存資産と照合する。"""
    try:
        args = _parser().parse_args(argv)
        root = args.root.resolve()
        derived = derive_boot_seal(root)
        output = root / _BOOT_SEAL_PATH
        if args.write:
            _write_asset(output, derived)
        elif args.check:
            if read_json(output) != derived:
                print("封印集合が導出結果と一致しない", file=sys.stderr)
                return EXIT_NONCONFORMING
        else:
            sys.stdout.write(canonical_json(derived))
    except CheckerExecutionError as error:
        print(str(error), file=sys.stderr)
        return EXIT_INDETERMINATE
    return EXIT_CONFORMING


if __name__ == "__main__":
    raise SystemExit(main())
