"""同期プロトコル設計の表間伝播、参照、残存欠陥を検査する。"""

from __future__ import annotations

import argparse
import contextlib
import fnmatch
import importlib.util
import io
import json
import re
import sys
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


def _load_profile_module() -> Any:
    """隣接する共通プロファイルローダーをファイルパスから読む。"""
    path = Path(__file__).resolve().parent / "doc_check_profile.py"
    spec = importlib.util.spec_from_file_location(
        "check_design_propagation_doc_check_profile",
        path,
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"プロファイルローダーを読み込めない: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_invariant_module() -> Any:
    """隣接する宣言評価器をファイルパスから読む。"""
    path = Path(__file__).resolve().parent / "doc_check_invariants.py"
    spec = importlib.util.spec_from_file_location(
        "check_design_propagation_doc_check_invariants",
        path,
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"宣言評価器を読み込めない: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


doc_check_profile = _load_profile_module()
doc_check_invariants = _load_invariant_module()

CHECK_IDS = (
    "manifest-consistency",
    "element-coverage",
    "enum-propagation",
    "condition-key",
    "route-matrix",
    "scope-declaration",
    "order-use",
    "citation-format",
    "noncanonical-reference",
    "link-target",
    "emphasis",
    "draft-metadata",
    "collection-consistency",
    "forbidden-structure",
    "cross-consistency",
    "baseline-digest",
    "unique-owner",
    "reference-class",
)
CHECK_ID_SET = frozenset(CHECK_IDS)
LEGACY_PROP_CHECK_IDS = frozenset(CHECK_IDS[:12])
PROFILE_ASSET_CHECK_IDS = frozenset(
    {
        "collection-consistency",
        "forbidden-structure",
        "cross-consistency",
        "baseline-digest",
        "unique-owner",
    }
)
GLOBAL_CHECK_IDS = frozenset(
    {
        "manifest-consistency",
        "citation-format",
        "noncanonical-reference",
        "link-target",
    }
)
DEFAULT_DOCUMENT = Path("docs/design/sync-protocol.md")
DEFAULT_DEFECTS = Path("scripts/design_relations/defects.json")
DEFAULT_MANIFEST = Path("scripts/design_relations/sync-protocol.json")

HEADING_RE = re.compile(r"^(?P<marks>#{2,6})\s+(?P<title>.+)$")
MARKDOWN_LINK_RE = re.compile(
    r"\[[^\]]+\]\((?P<target><[^>]+>|[^)\s]+)(?:\s+[^)]*)?\)"
)
REQ_LINE_CITATION_RE = re.compile(r"\bREQ:\d+\b")
PATH_LINE_CITATION_RE = re.compile(r"[^\s`\[\]()]+\.md:\d+\b")
BARE_LINE_CITATION_RE = re.compile(r"(?<![A-Za-z0-9_]):\d+\b")
NONCANONICAL_PATH_RE = re.compile(r"(?:docs/features/|\.\./features/)")
DEFAULT_SECTION_ID_GRAMMAR = r"\d+(?:-\d+(?:-[A-Z])?)?"
DEFAULT_PREAMBLE = "first-h2"
DEFAULT_EXCLUSION_VOCABULARY = ("対象外", "対象にならない", "含めない")
DEFAULT_LEGACY_PREFIXES = ("docs/legacy/", "../legacy/")
DEFAULT_LEGACY_INFIX = "/docs/legacy/"
DEFAULT_NONCANONICAL_SCAN_START = r"^##\s+2(?:[.\s]|$)"
DEFAULT_DECLARATION_SECTION = "2-5"
DEFAULT_DECLARATION_ROW_PREFIX = "| **R-"
DEFAULT_DECLARATION_COLUMN_COUNT = 6
LEGACY_STRUCTURAL_BRANCH_IDS: frozenset[str] = frozenset()


class CheckError(Exception):
    """入力・セレクタ・oracle の不正を表す。"""


@dataclass(frozen=True)
class ManifestRelation:
    """関係マニフェストの1関係を表す。

    Attributes:
        id: 関係ID。
        source_table: 正本となる表の識別子。
        targets: 伝播先となる表の完全集合。
        compare_key: 表間で比較する構造。
        source_elements: 正本の表に存在する要素IDの全集合。
        expected_elements: 伝播先ごとの要素IDの期待部分集合。
    """

    id: str
    source_table: str
    targets: tuple[str, ...]
    compare_key: str
    source_elements: tuple[str, ...]
    expected_elements: tuple[tuple[str, tuple[str, ...]], ...]


@dataclass(frozen=True)
class Invariant:
    """機械欠陥に固定された不変条件を表す。

    Attributes:
        positive: 検査ロジックが満たす肯定条件の仕様。
        forbidden: スコープ内で禁止するliteral部分文字列。
        scope: 評価対象の節。
        mapping: 表間対応の仕様。対応なしなら ``None``。
    """

    positive: str
    forbidden: tuple[str, ...]
    scope: str
    mapping: str | None


@dataclass(frozen=True)
class Defect:
    """欠陥oracleの1件を表す。

    Attributes:
        id: 欠陥ID。
        detection: ``machine`` または ``human``。
        check: 対応する検査ID。人間照合では ``None``。
        invariant: 機械不変条件。人間照合では ``None``。
    """

    id: str
    detection: str
    check: str | None
    invariant: Invariant | None


@dataclass(frozen=True)
class Finding:
    """1件の検査違反を表す。

    Attributes:
        identifier: 欠陥ID、または欠陥IDを持たない検査ID。
        check: 検出した検査ID。
        reason: 違反理由。
    """

    identifier: str
    check: str
    reason: str


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise CheckError(f"JSONを読めない: {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise CheckError(f"JSONが不正: {path}: {error}") from error


def _as_string(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise CheckError(f"{field} は文字列でなければならない")
    return value


def _as_string_tuple(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise CheckError(f"{field} は文字列配列でなければならない")
    return tuple(value)


def _as_expected_elements(
    value: object,
    targets: tuple[str, ...],
    source_elements: tuple[str, ...],
    field: str,
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """伝播先ごとの期待部分集合を検証する。

    Args:
        value: JSONから読んだ値。
        targets: 宣言済みの伝播先。
        source_elements: 正本の要素全集合。
        field: エラー表示用のフィールド名。

    Returns:
        ``targets`` と同じ順序に正規化した期待部分集合。

    Raises:
        CheckError: 伝播先、要素、または孤立要素が不正な場合。
    """
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise CheckError(f"{field} は伝播先をキーとするオブジェクトでなければならない")
    missing_targets = sorted(set(targets) - set(value))
    unknown_targets = sorted(set(value) - set(targets))
    if missing_targets or unknown_targets:
        raise CheckError(
            f"{field} の伝播先がtargetsと一致しない"
            f" (不足={missing_targets}, 未知={unknown_targets})"
        )
    source_set = set(source_elements)
    expected: list[tuple[str, tuple[str, ...]]] = []
    propagated: set[str] = set()
    for target in targets:
        elements = _as_string_tuple(value[target], f"{field}.{target}")
        if len(elements) != len(set(elements)):
            raise CheckError(f"{field}.{target} に要素IDの重複がある")
        unknown_elements = sorted(set(elements) - source_set)
        if unknown_elements:
            raise CheckError(
                f"{field}.{target} に正本外の要素IDがある: {','.join(unknown_elements)}"
            )
        expected.append((target, elements))
        propagated.update(elements)
    orphaned = sorted(source_set - propagated)
    if orphaned:
        raise CheckError(f"{field} にどこへも伝播しない要素IDがある: {','.join(orphaned)}")
    return tuple(expected)


def load_manifest(path: Path) -> dict[str, ManifestRelation]:
    """関係マニフェストを読み、6フィールドを検証する。

    Args:
        path: ``sync-protocol.json`` のパス。

    Returns:
        関係IDをキーとする検証済み関係。

    Raises:
        CheckError: JSONまたは関係の形が不正な場合。
    """
    raw = _read_json(path)
    if not isinstance(raw, dict):
        raise CheckError("関係マニフェストのルートはオブジェクトでなければならない")
    raw_relations: object
    if set(raw) == {"schema_version", "relations"} and isinstance(
        raw.get("relations"), list
    ):
        raw_relations = {
            value.get("id"): value
            for value in raw["relations"]
            if isinstance(value, dict) and isinstance(value.get("id"), str)
        }
        if len(raw_relations) != len(raw["relations"]):
            raise CheckError("関係マニフェストのrelationsに不正または重複IDがあります")
    else:
        raw_relations = raw
    assert isinstance(raw_relations, dict)
    relations: dict[str, ManifestRelation] = {}
    for key, value in raw_relations.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            raise CheckError("関係マニフェストの各関係が不正")
        relation_id = _as_string(value.get("id"), f"{key}.id")
        if relation_id != key:
            raise CheckError(f"関係キーとidが一致しない: {key}")
        targets = _as_string_tuple(value.get("targets"), f"{key}.targets")
        source_elements = _as_string_tuple(
            value.get("source_elements"), f"{key}.source_elements"
        )
        if len(source_elements) != len(set(source_elements)):
            raise CheckError(f"{key}.source_elements に要素IDの重複がある")
        relations[key] = ManifestRelation(
            id=relation_id,
            source_table=_as_string(value.get("source_table"), f"{key}.source_table"),
            targets=targets,
            compare_key=_as_string(value.get("compare_key"), f"{key}.compare_key"),
            source_elements=source_elements,
            expected_elements=_as_expected_elements(
                value.get("expected_elements"),
                targets,
                source_elements,
                f"{key}.expected_elements",
            ),
        )
    return relations


def load_defects(path: Path) -> dict[str, Defect]:
    """欠陥oracleを読み、機械欠陥と人間照合欠陥を検証する。

    Args:
        path: ``defects.json`` のパス。

    Returns:
        欠陥IDをキーとする検証済み欠陥。

    Raises:
        CheckError: JSONまたは欠陥の形が不正な場合。
    """
    raw = _read_json(path)
    if not isinstance(raw, dict):
        raise CheckError("欠陥oracleのルートはオブジェクトでなければならない")
    defects: dict[str, Defect] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or key.startswith("_"):
            continue
        if not isinstance(value, dict):
            raise CheckError(f"欠陥がオブジェクトでない: {key}")
        defect_id = _as_string(value.get("id"), f"{key}.id")
        if defect_id != key:
            raise CheckError(f"欠陥キーとidが一致しない: {key}")
        detection = _as_string(value.get("detection"), f"{key}.detection")
        if detection == "machine":
            check_id = _as_string(value.get("check"), f"{key}.check")
            if check_id not in CHECK_ID_SET or check_id in GLOBAL_CHECK_IDS:
                raise CheckError(f"機械欠陥の検査IDが不正: {key}: {check_id}")
            raw_invariant = value.get("invariant")
            if not isinstance(raw_invariant, dict):
                raise CheckError(f"機械欠陥にinvariantがない: {key}")
            mapping = raw_invariant.get("mapping")
            if mapping is not None and not isinstance(mapping, str):
                raise CheckError(f"{key}.invariant.mapping が不正")
            invariant = Invariant(
                positive=_as_string(
                    raw_invariant.get("positive"), f"{key}.invariant.positive"
                ),
                forbidden=_as_string_tuple(
                    raw_invariant.get("forbidden"), f"{key}.invariant.forbidden"
                ),
                scope=_as_string(raw_invariant.get("scope"), f"{key}.invariant.scope"),
                mapping=mapping,
            )
        elif detection == "human":
            check_id = None
            invariant = None
        else:
            raise CheckError(f"欠陥のdetectionが不正: {key}: {detection}")
        defects[key] = Defect(
            id=defect_id,
            detection=detection,
            check=check_id,
            invariant=invariant,
        )
    return defects


def _heading_section(text: str, label: str) -> str:
    lines = text.splitlines()
    start: int | None = None
    level = 0
    label_re = re.compile(rf"^{re.escape(label)}(?:[.\s(]|$)")
    for index, line in enumerate(lines):
        match = HEADING_RE.match(line)
        if match is None or label_re.match(match.group("title")) is None:
            continue
        start = index
        level = len(match.group("marks"))
        break
    if start is None:
        return ""
    end = len(lines)
    for index in range(start + 1, len(lines)):
        match = HEADING_RE.match(lines[index])
        if match is not None and len(match.group("marks")) <= level:
            end = index
            break
    return "\n".join(lines[start:end])


def extract_scope(
    text: str,
    scope: str,
    *,
    section_id_grammar: str = DEFAULT_SECTION_ID_GRAMMAR,
    preamble: str = DEFAULT_PREAMBLE,
) -> str:
    """不変条件のscopeに列挙された節だけを本文から切り出す。

    Args:
        text: 検査対象のMarkdown本文。
        scope: ``2-1、4-2`` や ``冒頭、1節`` 形式の節指定。
        section_id_grammar: 節IDを判定する正規表現。
        preamble: 冒頭スコープの切り出し方式。

    Returns:
        指定された節を出現順に連結した文字列。

    Raises:
        CheckError: scopeトークンが不正か、対象の節が文書に無い場合。
        ProfileError: 冒頭の切り出し方式が未対応の場合。
    """
    if preamble != DEFAULT_PREAMBLE:
        raise doc_check_profile.ProfileError(
            f"preamble は {DEFAULT_PREAMBLE!r} でなければならない: {preamble!r}"
        )
    try:
        section_id_re = re.compile(section_id_grammar)
    except re.error as error:
        raise CheckError(f"section_id_grammar が不正: {error}") from error
    sections: list[str] = []
    for raw_token in scope.split("、"):
        token = raw_token.strip()
        if token == "冒頭":
            sections.append(text.split("\n## ", 1)[0])
            continue
        token = token.split(" の", 1)[0].removesuffix("節").strip()
        if section_id_re.fullmatch(token) is None:
            raise CheckError(
                f"scope のトークン『{token}』が節 ID の文法に一致しない"
            )
        section = _heading_section(text, token)
        if not section:
            raise CheckError(f"scope の節『{token}』が文書に無い")
        sections.append(section)
    return "\n".join(sections)


def defect_violation_reason(
    defect: Defect,
    text: str,
    manifest: dict[str, ManifestRelation],
    *,
    section_id_grammar: str = DEFAULT_SECTION_ID_GRAMMAR,
    preamble: str = DEFAULT_PREAMBLE,
    invariants: Any | None = None,
    profile: Any | None = None,
) -> str | None:
    """1件の機械欠陥についてliteralと構造的不変条件を評価する。

    forbidden literalを先に確認し、続いて宣言列をfirst-failureで評価する。

    Args:
        defect: 評価する機械欠陥。
        text: 検査対象のMarkdown本文。
        manifest: 関係マニフェスト。
        section_id_grammar: scopeの節IDを判定する正規表現。
        preamble: 冒頭スコープの切り出し方式。
        invariants: 検証済みの不変条件宣言資産。
        profile: 宣言評価に使う検証済みプロファイル。

    Returns:
        違反理由。適合していれば ``None``。

    Raises:
        CheckError: 人間照合欠陥を渡した場合。
    """
    if defect.detection != "machine" or defect.invariant is None:
        raise CheckError(f"人間照合欠陥は機械評価できない: {defect.id}")
    scoped = extract_scope(
        text,
        defect.invariant.scope,
        section_id_grammar=section_id_grammar,
        preamble=preamble,
    )
    for forbidden in defect.invariant.forbidden:
        if forbidden in scoped:
            return f"禁止literalが残存: {forbidden}"
    if invariants is None:
        return None
    context = doc_check_invariants.EvaluationContext()
    declarations = (
        declaration
        for declaration in invariants.declarations
        if declaration["defect_id"] == defect.id
    )
    for declaration in declarations:
        sections = _resolve_declaration_sections(text, declaration)
        reason = doc_check_invariants.evaluate_declaration(
            declaration,
            text=text,
            manifest=manifest,
            profile=profile,
            sections=sections,
            context=context,
        )
        if reason is not None:
            return reason.actual or f"{reason.kind} に違反"
    return None


def _resolve_declaration_sections(
    text: str,
    declaration: dict[str, Any],
) -> dict[str, str]:
    """宣言の節指定を解決し、節不在を入力不正にする。"""
    if declaration.get("kind") == "absent-section":
        return {}
    section_ids: list[str] = []
    section = declaration.get("section")
    if isinstance(section, str):
        section_ids.append(section)
    sections = declaration.get("sections")
    if isinstance(sections, list):
        section_ids.extend(item for item in sections if isinstance(item, str))
    if declaration.get("kind") == "well-formedness":
        scope = declaration.get("scope")
        if isinstance(scope, str):
            section_ids.append(scope)
    resolved: dict[str, str] = {}
    for section_id in section_ids:
        section_text = _heading_section(text, section_id)
        if not section_text:
            raise CheckError(f"宣言の節『{section_id}』が文書に無い")
        resolved[section_id] = section_text
    return resolved


def _strip_code_span(value: str) -> str:
    if len(value) >= 2 and value.startswith("`") and value.endswith("`"):
        return value[1:-1]
    return value


def parse_manifest_declaration(
    text: str,
    *,
    section_id: str = DEFAULT_DECLARATION_SECTION,
    row_prefix: str = DEFAULT_DECLARATION_ROW_PREFIX,
    column_count: int = DEFAULT_DECLARATION_COLUMN_COUNT,
) -> tuple[dict[str, ManifestRelation], tuple[str, ...]]:
    """表間参照宣言表を指定された構造で解析する。

    Args:
        text: 検査対象のMarkdown本文。
        section_id: 宣言表を置く節ID。
        row_prefix: 関係行を識別する接頭辞。
        column_count: 関係行に必要な列数。

    Returns:
        ``(関係ID別の宣言, 解析違反)``。
    """
    section = _heading_section(text, section_id)
    if not section:
        return {}, (f"{section_id}の表間参照宣言表がない",)
    relations: dict[str, ManifestRelation] = {}
    errors: list[str] = []
    for line in section.splitlines():
        if not line.startswith(row_prefix):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != column_count:
            errors.append(f"宣言表の列数が{column_count}でない")
            continue
        relation_id = cells[0].removeprefix("**").removesuffix("**")
        if relation_id in relations:
            errors.append(f"関係IDが重複: {relation_id}")
            continue
        try:
            targets_raw = json.loads(_strip_code_span(cells[2]))
            source_elements_raw = json.loads(_strip_code_span(cells[4]))
            expected_elements_raw = json.loads(_strip_code_span(cells[5]))
            targets = _as_string_tuple(targets_raw, f"{relation_id}.targets")
            source_elements = _as_string_tuple(
                source_elements_raw, f"{relation_id}.source_elements"
            )
            expected_elements = _as_expected_elements(
                expected_elements_raw,
                targets,
                source_elements,
                f"{relation_id}.expected_elements",
            )
        except (json.JSONDecodeError, CheckError) as error:
            errors.append(f"{relation_id}のJSONセルが不正: {error}")
            continue
        relations[relation_id] = ManifestRelation(
            id=relation_id,
            source_table=_strip_code_span(cells[1]),
            targets=targets,
            compare_key=_strip_code_span(cells[3]),
            source_elements=source_elements,
            expected_elements=expected_elements,
        )
    if not relations and not errors:
        errors.append("表間参照宣言表に関係行がない")
    return relations, tuple(errors)


def check_manifest_consistency(
    text: str,
    manifest: dict[str, ManifestRelation],
    *,
    declaration_section: str = DEFAULT_DECLARATION_SECTION,
    declaration_row_prefix: str = DEFAULT_DECLARATION_ROW_PREFIX,
    declaration_column_count: int = DEFAULT_DECLARATION_COLUMN_COUNT,
) -> tuple[str, ...]:
    """本文宣言表とJSONを6フィールドすべてで双方向突合する。

    Args:
        text: 検査対象のMarkdown本文。
        manifest: JSONから読んだ関係マニフェスト。
        declaration_section: 宣言表を置く節ID。
        declaration_row_prefix: 関係行を識別する接頭辞。
        declaration_column_count: 関係行に必要な列数。

    Returns:
        不一致理由。完全一致なら空タプル。
    """
    declared, errors = parse_manifest_declaration(
        text,
        section_id=declaration_section,
        row_prefix=declaration_row_prefix,
        column_count=declaration_column_count,
    )
    reasons = list(errors)
    missing = sorted(set(manifest) - set(declared))
    unknown = sorted(set(declared) - set(manifest))
    if missing:
        reasons.append(f"本文にない関係ID: {','.join(missing)}")
    if unknown:
        reasons.append(f"JSONにない関係ID: {','.join(unknown)}")
    for relation_id in sorted(set(manifest) & set(declared)):
        if manifest[relation_id] != declared[relation_id]:
            reasons.append(f"6フィールドが不一致: {relation_id}")
    return tuple(reasons)


def _reference_section(text: str, reference: str) -> str:
    """表参照の先頭にある節IDから本文を切り出す。

    Args:
        text: 検査対象のMarkdown本文。
        reference: ``6-3 の境界結果表`` のような表参照。

    Returns:
        対応する節。節IDを読めない場合は空文字列。
    """
    match = re.match(r"(?P<label>\d+(?:-\d+(?:-[A-Z])?)?)(?:\s|$)", reference)
    return _heading_section(text, match.group("label")) if match is not None else ""


_element_markers = doc_check_invariants.element_markers
_semantic_text = doc_check_invariants.semantic_text
_semantic_part_occurs = doc_check_invariants.semantic_part_occurs
_identifier_set = doc_check_invariants.identifier_set
_data_table_rows = doc_check_invariants.data_table_rows
_element_table_row_occurs = doc_check_invariants.element_table_row_occurs
_identifier_occurs = doc_check_invariants.identifier_occurs
_element_occurs = doc_check_invariants.element_occurs


def check_element_coverage(
    text: str,
    manifest: dict[str, ManifestRelation],
) -> tuple[str, ...]:
    """全関係の正本要素と伝播先ごとの期待部分集合を照合する。

    関係IDには依存せず、マニフェストへ関係を追加すれば自動的に検査する。

    Args:
        text: 検査対象のMarkdown本文。
        manifest: 関係マニフェスト。

    Returns:
        欠落した正本要素または伝播要素の理由。適合時は空タプル。
    """
    reasons: list[str] = []
    for relation in manifest.values():
        source = _reference_section(text, relation.source_table)
        if not source:
            reasons.append(f"{relation.id}: 正本の節を解決できない: {relation.source_table}")
        else:
            missing_source = [
                element
                for element in relation.source_elements
                if not _element_occurs(source, element)
            ]
            if missing_source:
                reasons.append(
                    f"{relation.id}: 正本にない要素: {','.join(missing_source)}"
                )
        for target, elements in relation.expected_elements:
            target_section = _reference_section(text, target)
            if not target_section:
                reasons.append(f"{relation.id}: 伝播先の節を解決できない: {target}")
                continue
            missing_target = [
                element
                for element in elements
                if not _element_occurs(target_section, element)
            ]
            if missing_target:
                reasons.append(
                    f"{relation.id}: {target} にない要素: {','.join(missing_target)}"
                )
    return tuple(reasons)


def check_citation_format(
    text: str,
    *,
    legacy_prefixes: Sequence[str] = DEFAULT_LEGACY_PREFIXES,
    legacy_infix: str = DEFAULT_LEGACY_INFIX,
) -> tuple[str, ...]:
    """可変文書で禁止する3形式の行番号引用を検出する。

    版固定アーカイブ ``docs/legacy/`` への行番号引用は逐語証拠として許容する。
    裸の行番号は同じ主張行で直前に現れた参照先を引き継ぎ、参照先が
    不明な場合は違反として扱う。

    Args:
        text: 検査対象のMarkdown本文。
        legacy_prefixes: legacy引用と認識するパス接頭辞。
        legacy_infix: legacy引用と認識するパス中間文字列。

    Returns:
        残存した引用形式の識別子。
    """
    found: set[str] = set()
    for line in text.splitlines():
        events: list[tuple[int, int, int, str, re.Match[str]]] = []
        patterns = (
            (0, "markdown", MARKDOWN_LINK_RE),
            (1, "requirement-line", REQ_LINE_CITATION_RE),
            (2, "path-line", PATH_LINE_CITATION_RE),
            (3, "bare-line", BARE_LINE_CITATION_RE),
        )
        for priority, event_kind, pattern in patterns:
            events.extend(
                (match.start(), match.end(), priority, event_kind, match)
                for match in pattern.finditer(line)
            )
        events.sort(key=lambda event: (event[0], event[2], -(event[1] - event[0])))

        occupied: list[tuple[int, int]] = []
        last_path: str | None = None
        for start, end, _, event_kind, match in events:
            if any(start < right and left < end for left, right in occupied):
                continue
            occupied.append((start, end))
            if event_kind == "markdown":
                last_path = match.group("target").strip("<>").split("#", 1)[0]
                continue
            if event_kind == "requirement-line":
                found.add("REQ:<行番号>")
                last_path = "docs/requirements/requirements-pitchlog-2026-07-22.md"
                continue
            if event_kind == "path-line":
                last_path = match.group(0).rsplit(":", 1)[0]
                if not _is_legacy_citation_path(
                    last_path,
                    legacy_prefixes=legacy_prefixes,
                    legacy_infix=legacy_infix,
                ):
                    found.add("<パス>.md:<行番号>")
                continue
            if last_path is None or not _is_legacy_citation_path(
                last_path,
                legacy_prefixes=legacy_prefixes,
                legacy_infix=legacy_infix,
            ):
                found.add("裸の行番号")
    return tuple(
        identifier
        for identifier in ("REQ:<行番号>", "<パス>.md:<行番号>", "裸の行番号")
        if identifier in found
    )


def _is_legacy_citation_path(
    path: str,
    *,
    legacy_prefixes: Sequence[str] = DEFAULT_LEGACY_PREFIXES,
    legacy_infix: str = DEFAULT_LEGACY_INFIX,
) -> bool:
    """引用先が版固定のlegacyアーカイブかを返す。

    Args:
        path: リポジトリ相対または文書相対のMarkdownパス。
        legacy_prefixes: legacy引用と認識するパス接頭辞。
        legacy_infix: legacy引用と認識するパス中間文字列。

    Returns:
        ``docs/legacy/`` 配下を指す場合は ``True``。
    """
    normalized = path.replace("\\", "/")
    return normalized.startswith(tuple(legacy_prefixes)) or legacy_infix in normalized


def check_noncanonical_reference(
    text: str,
    *,
    scan_start: str = DEFAULT_NONCANONICAL_SCAN_START,
    path_pattern: str = NONCANONICAL_PATH_RE.pattern,
) -> tuple[int, ...]:
    """本文中のdocs/features配下への規範参照を検出する。

    変更履歴は経緯の記録なので対象外とし、2章以降を規範本文として走査する。

    Args:
        text: 検査対象のMarkdown本文。
        scan_start: 規範本文の走査を開始する見出しの正規表現。
        path_pattern: 非正本参照を表すパスの正規表現。

    Returns:
        非正本参照がある1始まり行番号。
    """
    try:
        scan_start_re = re.compile(scan_start)
        path_re = re.compile(path_pattern)
    except re.error as error:
        raise CheckError(f"非正本参照の正規表現が不正: {error}") from error
    lines = text.splitlines()
    start = next(
        (index for index, line in enumerate(lines) if scan_start_re.match(line)),
        len(lines),
    )
    return tuple(
        index + 1
        for index, line in enumerate(lines)
        if index >= start and path_re.search(line) is not None
    )


def check_link_targets(
    text: str,
    root: Path,
    base_dir: Path | None = None,
) -> tuple[str, ...]:
    """本文の相対Markdownリンクがリポジトリ内に実在するか検査する。

    ``base_dir`` が無い場合は、fixtureも正本文書のコピーとして扱う
    従来どおり ``docs/design`` を解決基準とする。

    Args:
        text: 検査対象のMarkdown本文。
        root: リポジトリルート。
        base_dir: 相対リンクの解決基準。省略時は ``root/docs/design``。

    Returns:
        不正または実在しないリンク先。
    """
    root = root.resolve()
    if base_dir is None:
        base = (root / "docs" / "design").resolve()
    else:
        base = base_dir if base_dir.is_absolute() else root / base_dir
        base = base.resolve()
    missing: list[str] = []
    for match in MARKDOWN_LINK_RE.finditer(text):
        target = match.group("target").strip("<>")
        if target.startswith(("#", "http://", "https://", "mailto:")):
            continue
        path_part = target.split("#", 1)[0]
        candidate = (root / path_part.lstrip("/")) if target.startswith("/") else (base / path_part)
        resolved = candidate.resolve()
        if not resolved.is_relative_to(root) or not resolved.exists():
            missing.append(target)
    return tuple(dict.fromkeys(missing))


def _reference_target(
    target: str,
    *,
    document_path: Path,
    root: Path,
) -> tuple[str, str | None, Path | None]:
    """Markdownリンクを規則照合用の正規化パスへ変換する。"""
    raw_target = target.strip("<>")
    path_text, separator, fragment = raw_target.partition("#")
    fragment_value = fragment if separator else None
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", path_text) or path_text.startswith("//"):
        return path_text, fragment_value, None
    if not path_text:
        resolved = document_path.resolve()
    elif path_text.startswith("/"):
        resolved = (root / path_text.lstrip("/")).resolve()
    else:
        resolved = (document_path.parent / path_text).resolve()
    root_path = root.resolve()
    if not resolved.is_relative_to(root_path):
        raise CheckError(f"参照先がリポジトリ外です: {raw_target}")
    return resolved.relative_to(root_path).as_posix(), fragment_value, resolved


def _frontmatter_status(path: Path) -> str | None:
    """Markdown先頭のfrontmatterからstatusを取得する。"""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return None
    if not lines or lines[0] != "---":
        return None
    statuses: list[str] = []
    for line in lines[1:]:
        if line == "---":
            return statuses[0] if len(statuses) == 1 else None
        match = re.match(r"^status:\s*(.*?)\s*$", line)
        if match is not None:
            statuses.append(match.group(1).strip("\"'"))
    return None


def check_reference_classes(
    text: str,
    *,
    profile: Any,
    document_path: Path,
    root: Path,
) -> tuple[Finding, ...]:
    """順序付き規則で参照を分類し、normative先の承認状態を検査する。"""
    rules = profile.raw["reference_policy"]["rules"]
    section_pattern = re.compile(
        rf"^(?P<section>{profile.raw['section_id_grammar']})(?:[.\s(]|$)"
    )
    current_section: str | None = None
    findings: list[Finding] = []
    fence: str | None = None
    for line_number, line in enumerate(text.splitlines(), start=1):
        fence_match = re.match(r"^\s*(`{3,}|~{3,})", line)
        if fence_match is not None:
            marker = fence_match.group(1)[0]
            if fence is None:
                fence = marker
            elif fence == marker:
                fence = None
            continue
        if fence is not None:
            continue
        heading = HEADING_RE.match(line)
        if heading is not None:
            title = heading.group("title")
            section_match = section_pattern.match(title)
            current_section = (
                section_match.group("section")
                if section_match is not None
                else None
            )
        for link in MARKDOWN_LINK_RE.finditer(line):
            target = link.group("target")
            normalized, fragment, resolved = _reference_target(
                target,
                document_path=document_path,
                root=root,
            )
            matched_rule: Mapping[str, Any] | None = None
            for rule in rules:
                if (
                    "source_section" in rule
                    and rule["source_section"] != current_section
                ):
                    continue
                if not fnmatch.fnmatchcase(normalized, rule["target_pattern"]):
                    continue
                if "fragment" in rule and (
                    fragment is None
                    or not fnmatch.fnmatchcase(fragment, rule["fragment"])
                ):
                    continue
                matched_rule = rule
                break
            if matched_rule is None:
                raise CheckError(
                    "reference_policyに一致する規則がありません: "
                    f"行{line_number}: {target}"
                )
            if matched_rule["role"] != "normative":
                continue
            actual_status = _frontmatter_status(resolved) if resolved is not None else None
            if actual_status != "approved":
                findings.append(
                    Finding(
                        "reference-class",
                        "reference-class",
                        f"normative参照先がapprovedでない: {normalized}"
                        f"(status={actual_status})",
                    )
                )
    return tuple(findings)


def check_collection_consistency(
    profile: Any,
    assets: Any,
    raw_manifest: Mapping[str, Any],
) -> tuple[Finding, ...]:
    """collection_setsの集合関係違反をFindingにする。"""
    results = doc_check_profile.evaluate_collection_sets(
        profile,
        assets,
        manifest=raw_manifest,
    )
    return tuple(
        Finding("collection-consistency", "collection-consistency", result.reason)
        for result in results
        if result.reason is not None
    )


def _structure_matches(left: Any, right: Any) -> bool:
    """構造の全項目を照合し、bothだけを両方向として扱う。"""
    return (
        left.kind == right.kind
        and left.source == right.source
        and left.target == right.target
        and left.participants == right.participants
        and (
            left.direction == right.direction
            or left.direction == "both"
            or right.direction == "both"
        )
    )


def check_forbidden_structures(
    profile: Any,
    assets: Any,
    *,
    text: str,
    raw_manifest: Mapping[str, Any],
) -> tuple[Finding, ...]:
    """抽出済み構造と禁止構造を名前空間付きで照合する。"""
    extracted = doc_check_profile.extract_structures(
        profile,
        assets,
        text=text,
        manifest=raw_manifest,
    )
    observed = tuple(
        structure
        for structures in extracted.values()
        for structure in structures
    )
    forbidden = doc_check_profile.asset_structures(assets, "forbidden")
    findings: list[Finding] = []
    for structure in forbidden:
        if any(_structure_matches(structure, candidate) for candidate in observed):
            findings.append(
                Finding(
                    "forbidden-structure",
                    "forbidden-structure",
                    "禁止構造が実在: " + _format_structure(structure),
                )
            )
    return tuple(findings)


def _format_structure(structure: Any) -> str:
    """構造タプルを診断用の安定文字列にする。"""
    participants = ",".join(
        f"{participant.namespace}:{participant.id}"
        for participant in structure.participants
    )
    return (
        f"kind={structure.kind},"
        f"source={structure.source.namespace}:{structure.source.id},"
        f"target={structure.target.namespace}:{structure.target.id},"
        f"direction={structure.direction},participants=[{participants}]"
    )


def _asset_records(assets: Any, name: str) -> tuple[Any, ...]:
    """指定資産の全collection項目を返す。"""
    asset = assets.assets.get(name)
    if asset is None:
        raise doc_check_profile.ProfileError(f"資産がありません: {name}")
    return tuple(
        record
        for collection in asset.collections
        for record in collection.records
    )


def _project_structure(structure: Any, project: Any) -> Any:
    """構造の全端点を製品IDに射影する。"""

    def endpoint(value: Any) -> Any:
        return doc_check_profile.NamespacedId(value.namespace, project(value.id))

    return doc_check_profile.StructureTuple(
        kind=structure.kind,
        source=endpoint(structure.source),
        target=endpoint(structure.target),
        direction=structure.direction,
        participants=tuple(endpoint(value) for value in structure.participants),
    )


def _product_projector(assets: Any, referenced_ids: set[str]) -> Any:
    """product_schemaの有無に応じたDDL ID射影関数を返す。"""
    ddl_asset = assets.assets["ddl_elements"]
    raw_ddl = ddl_asset.raw
    product_schema = (
        isinstance(raw_ddl, Mapping)
        and isinstance(raw_ddl.get("scope"), Mapping)
        and raw_ddl["scope"].get("product_schema") is True
    )
    if product_schema:
        return lambda value: value

    records = _asset_records(assets, "product_ddl_map")
    mappings: dict[str, set[str]] = {}
    for record in records:
        raw_id = record.raw.get("ddl_id")
        product_id = record.raw.get("product_id")
        if not isinstance(raw_id, str) or not isinstance(product_id, str):
            raise doc_check_profile.ProfileError(
                "product_ddl_map のddl_id/product_idが不正です"
            )
        normalized_raw = doc_check_profile.normalize_identifier(
            raw_id,
            "ddl",
            assets.normalize,
        ).id
        normalized_product = doc_check_profile.normalize_identifier(
            product_id,
            "product",
            assets.normalize,
        ).id
        mappings.setdefault(normalized_raw, set()).add(normalized_product)
    ambiguous = {key: values for key, values in mappings.items() if len(values) != 1}
    if ambiguous:
        raise doc_check_profile.ProfileError(
            f"product_ddl_map に曖昧な写像があります: {ambiguous}"
        )
    domain = set(mappings)
    if domain != referenced_ids:
        raise doc_check_profile.ProfileError(
            "product_ddl_map のdomainが参照IDと一致しません"
            f"(未写像={sorted(referenced_ids - domain)}, "
            f"余分={sorted(domain - referenced_ids)})"
        )
    flattened = {key: next(iter(values)) for key, values in mappings.items()}
    return lambda value: flattened[value]


def check_cross_consistency(
    profile: Any,
    assets: Any,
    *,
    text: str,
    raw_manifest: Mapping[str, Any],
) -> tuple[Finding, ...]:
    """WAITとAUTHの二段階射影およびFORB衝突を検査する。"""
    findings: list[Finding] = []
    extracted = doc_check_profile.extract_structures(
        profile,
        assets,
        text=text,
        manifest=raw_manifest,
    )
    manifest_extractor_ids = {
        declaration["id"]
        for declaration in profile.raw["structure_extractors"]
        if declaration["source"] == "manifest"
    }
    manifest_ids = {
        endpoint.id
        for extractor_id, structures in extracted.items()
        if extractor_id in manifest_extractor_ids
        for structure in structures
        for endpoint in (
            structure.source,
            structure.target,
            *structure.participants,
        )
    }
    extracted_structures = tuple(
        structure
        for values in extracted.values()
        for structure in values
    )

    waiting_structures: list[Any] = []
    for record in _asset_records(assets, "waiting"):
        if record.raw.get("status") != "resolved":
            continue
        physical = record.raw.get("physical")
        if not isinstance(physical, str) or not physical:
            raise doc_check_profile.ProfileError("resolved WAIT の physical が不正です")
        normalized = doc_check_profile.normalize_identifier(
            physical,
            "table",
            assets.normalize,
        ).id
        if normalized not in manifest_ids:
            findings.append(
                Finding(
                    "cross-consistency",
                    "cross-consistency",
                    f"resolved WAIT の physical がmanifestにない: {normalized}",
                )
            )
        if normalized not in text:
            findings.append(
                Finding(
                    "cross-consistency",
                    "cross-consistency",
                    f"resolved WAIT の physical が本文にない: {normalized}",
                )
            )
        waiting_structures.extend(
            structure
            for structure in extracted_structures
            if any(value.id == normalized for value in structure.participants)
        )

    auth_records = _asset_records(assets, "auth_catalog")
    map_records = _asset_records(assets, "auth_ddl_map")
    auth_ids = {
        identifier.id for record in auth_records for identifier in record.identifiers
    }
    map_ids = {
        identifier.id for record in map_records for identifier in record.identifiers
    }
    if auth_ids != map_ids:
        findings.append(
            Finding(
                "cross-consistency",
                "cross-consistency",
                "auth_ddl_map ID集合がauth_catalogと不一致"
                f"(脱落={sorted(auth_ids - map_ids)}, 過剰={sorted(map_ids - auth_ids)})",
            )
        )

    ddl_ids = {
        identifier.id
        for record in _asset_records(assets, "ddl_elements")
        for identifier in record.identifiers
    }
    map_refs: set[str] = set()
    auth_structures: list[Any] = []
    for record in map_records:
        refs = {reference.id for reference in record.refs}
        if not refs:
            findings.append(
                Finding(
                    "cross-consistency",
                    "cross-consistency",
                    f"auth_ddl_map entry のrefsが空: {record.raw.get('catalog_entry_id')}",
                )
            )
        if not record.structures:
            findings.append(
                Finding(
                    "cross-consistency",
                    "cross-consistency",
                    "auth_ddl_map entry のstructuresが空: "
                    f"{record.raw.get('catalog_entry_id')}",
                )
            )
        map_refs.update(refs)
        auth_structures.extend(record.structures)
        if not refs <= ddl_ids:
            findings.append(
                Finding(
                    "cross-consistency",
                    "cross-consistency",
                    f"auth_ddl_map refがDDLにない: {sorted(refs - ddl_ids)}",
                )
            )
        participant_ids = {
            participant.id
            for structure in record.structures
            for participant in structure.participants
        }
        if not participant_ids <= refs:
            findings.append(
                Finding(
                    "cross-consistency",
                    "cross-consistency",
                    "auth_ddl_map structures.participantsがrefs外: "
                    f"{sorted(participant_ids - refs)}",
                )
            )

    ddl_structures = doc_check_profile.asset_structures(assets, "ddl_elements")
    if set(auth_structures) != set(ddl_structures):
        findings.append(
            Finding(
                "cross-consistency",
                "cross-consistency",
                "auth_ddl_map structuresがDDL導出構造と不一致"
                f"(脱落={len(set(ddl_structures) - set(auth_structures))}, "
                f"過剰={len(set(auth_structures) - set(ddl_structures))})",
            )
        )

    referenced_ids = set(map_refs)
    for structure in auth_structures:
        referenced_ids.update(
            value.id
            for value in (structure.source, structure.target, *structure.participants)
        )
    project = _product_projector(assets, referenced_ids)
    projected_refs = {project(value) for value in map_refs}
    if not projected_refs <= manifest_ids:
        findings.append(
            Finding(
                "cross-consistency",
                "cross-consistency",
                f"射影後AUTH refがmanifestにない: "
                f"{sorted(projected_refs - manifest_ids)}",
            )
        )
    projected_structures = tuple(
        _project_structure(structure, project) for structure in auth_structures
    )
    forbidden = doc_check_profile.asset_structures(assets, "forbidden")
    for forbidden_structure in forbidden:
        if any(
            _structure_matches(forbidden_structure, candidate)
            for candidate in (*projected_structures, *waiting_structures)
        ):
            findings.append(
                Finding(
                    "cross-consistency",
                    "cross-consistency",
                    "射影後構造が禁止構造と衝突: "
                    + _format_structure(forbidden_structure),
                )
            )
    return tuple(findings)


def _ledger_entries(value: Any) -> tuple[dict[str, Any], ...]:
    """欠陥台帳のmapping/list形を項目列へ正規化する。"""
    if isinstance(value, Mapping):
        entries: list[dict[str, Any]] = []
        for key, item in value.items():
            if not isinstance(item, Mapping):
                raise doc_check_profile.ProfileError(f"台帳項目 {key} がobjectではありません")
            entry = dict(item)
            if entry.get("id") != key:
                raise doc_check_profile.ProfileError(
                    f"台帳キー {key} と id が一致しません"
                )
            entries.append(entry)
        return tuple(entries)
    if isinstance(value, list) and all(isinstance(item, Mapping) for item in value):
        return tuple(dict(item) for item in value)
    raise doc_check_profile.ProfileError("欠陥台帳はobjectまたはobject arrayが必要です")


def _immutable_ledger_entry(entry: Mapping[str, Any]) -> dict[str, Any]:
    """台帳項目から版1のimmutable exact-setを取り出す。"""
    result: dict[str, Any] = {}
    for field in doc_check_profile.ASSET_IMMUTABLE_FIELDS:
        if field.startswith("invariant."):
            invariant = entry.get("invariant")
            nested = field.split(".", 1)[1]
            if not isinstance(invariant, Mapping) or nested not in invariant:
                raise doc_check_profile.ProfileError(
                    f"台帳 {entry.get('id')} の {field} がありません"
                )
            result[field] = invariant[nested]
        else:
            if field not in entry:
                raise doc_check_profile.ProfileError(
                    f"台帳 {entry.get('id')} の {field} がありません"
                )
            result[field] = entry[field]
    return result


def render_baseline_digest(entries: Sequence[Mapping[str, Any]]) -> str:
    """台帳のimmutable項目を版1のbaseline digestにする。"""
    rendered: list[tuple[str, str]] = []
    for entry in entries:
        immutable = _immutable_ledger_entry(entry)
        identifier = immutable["id"]
        if not isinstance(identifier, str) or not identifier:
            raise doc_check_profile.ProfileError("台帳 id が空または文字列外です")
        rendered.append((identifier, doc_check_profile.canonical_digest(immutable)))
    rendered.sort(key=lambda value: value[0].encode("utf-8"))
    fields = ",".join(doc_check_profile.ASSET_IMMUTABLE_FIELDS)
    lines = [f"envelope schema_version=1 algo=sha256 fields={fields}"]
    lines.extend(f"{identifier} {digest}" for identifier, digest in rendered)
    return "\n".join(lines) + "\n"


def _load_global_ledger(
    profile: Any,
    invariants: Any | None,
) -> tuple[Any, tuple[dict[str, Any], ...]]:
    """unique-owner宣言と台帳項目を読む。"""
    declarations = (
        tuple(
            value
            for value in invariants.global_invariants
            if value.get("kind") == "unique-owner"
        )
        if invariants is not None
        else ()
    )
    if len(declarations) != 1:
        raise doc_check_profile.ProfileError(
            "required_checks=unique-owner にglobal_invariantsのunique-owner 1件が必要です"
        )
    declaration = declarations[0]
    ledger_path = _resolve(profile.root, Path(declaration["ledger"]))
    return declaration, _ledger_entries(doc_check_profile.load_json(ledger_path))


def check_baseline_digest(
    profile: Any,
    assets: Any,
    invariants: Any | None,
) -> tuple[Finding, ...]:
    """欠陥台帳のbaseline digestと固定ファイルを逐語照合する。"""
    if invariants is not None and any(
        value.get("kind") == "unique-owner" for value in invariants.global_invariants
    ):
        declaration, entries = _load_global_ledger(profile, invariants)
        digest_path = _resolve(profile.root, Path(declaration["digest_file"]))
    else:
        entries = _ledger_entries(doc_check_profile.load_json(profile.defects))
        digest_path = assets.assets["baseline_digest"].path
    expected = render_baseline_digest(entries)
    try:
        actual = digest_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise doc_check_profile.ProfileError(
            f"baseline digestを読めません: {digest_path}: {error}"
        ) from error
    if actual == expected:
        return ()
    return (
        Finding(
            "baseline-digest",
            "baseline-digest",
            "baseline digestが台帳のimmutable項目と一致しません",
        ),
    )


def check_unique_owner(
    profile: Any,
    assets: Any,
    invariants: Any | None,
) -> tuple[Finding, ...]:
    """台帳IDの独立期待集合とowner_stepの一意性を検査する。"""
    declaration, entries = _load_global_ledger(profile, invariants)
    expected_asset = assets.assets.get("expected_ids")
    digest_asset = assets.assets.get("baseline_digest")
    if expected_asset is None or digest_asset is None:
        raise doc_check_profile.ProfileError(
            "required_checks=unique-owner に expected_ids と baseline_digest が必要です"
        )
    expected_path = _resolve(profile.root, Path(declaration["expected_ids"]))
    digest_path = _resolve(profile.root, Path(declaration["digest_file"]))
    if expected_path != expected_asset.path or digest_path != digest_asset.path:
        raise doc_check_profile.ProfileError(
            "unique-owner宣言のexpected_ids/digest_fileがプロファイル資産と不一致です"
        )
    expected_ids = {
        identifier.id
        for record in _asset_records(assets, "expected_ids")
        for identifier in record.identifiers
    }
    if not expected_ids:
        raise doc_check_profile.ProfileError("unique-owner のexpected_ids資産が空です")
    actual_values = [entry.get("id") for entry in entries]
    invalid_ids = [
        value for value in actual_values if not isinstance(value, str) or not value
    ]
    if invalid_ids:
        raise doc_check_profile.ProfileError(f"台帳のidが不正です: {invalid_ids}")
    actual_ids = [str(value) for value in actual_values]
    findings: list[Finding] = []
    duplicates = sorted(
        identifier
        for identifier, count in Counter(actual_ids).items()
        if count > 1
    )
    if duplicates:
        findings.append(
            Finding(
                "unique-owner",
                "unique-owner",
                f"台帳idが重複: {duplicates}",
            )
        )
    actual_set = set(actual_ids)
    if actual_set != expected_ids:
        findings.append(
            Finding(
                "unique-owner",
                "unique-owner",
                "台帳IDがexpected_idsと不一致"
                f"(欠落={sorted(expected_ids - actual_set)}, "
                f"過剰={sorted(actual_set - expected_ids)})",
            )
        )
    allowed = set(declaration["owner_steps_allowed"])
    invalid_owners = sorted(
        f"{entry.get('id')}={entry.get('owner_step')!r}"
        for entry in entries
        if entry.get("owner_step") not in allowed
    )
    if invalid_owners:
        findings.append(
            Finding(
                "unique-owner",
                "unique-owner",
                f"owner_stepが許可集合外: {invalid_owners}",
            )
        )
    return tuple(findings)


def _global_findings(
    text: str,
    root: Path,
    document_path: Path,
    manifest: dict[str, ManifestRelation],
    checks: frozenset[str],
    link_base_dir: Path | None,
    profile: Any | None,
    invariants: Any | None,
    raw_manifest: Mapping[str, Any] | None,
    *,
    legacy_prefixes: Sequence[str],
    legacy_infix: str,
    noncanonical_scan_start: str,
    noncanonical_path_pattern: str,
    declaration_section: str,
    declaration_row_prefix: str,
    declaration_column_count: int,
) -> list[Finding]:
    findings: list[Finding] = []
    if "element-coverage" in checks:
        reasons = check_element_coverage(text, manifest)
        if reasons:
            findings.append(
                Finding("element-coverage", "element-coverage", "; ".join(reasons))
            )
    if "manifest-consistency" in checks:
        reasons = check_manifest_consistency(
            text,
            manifest,
            declaration_section=declaration_section,
            declaration_row_prefix=declaration_row_prefix,
            declaration_column_count=declaration_column_count,
        )
        if reasons:
            findings.append(
                Finding("manifest-consistency", "manifest-consistency", "; ".join(reasons))
            )
    if "citation-format" in checks:
        formats = check_citation_format(
            text,
            legacy_prefixes=legacy_prefixes,
            legacy_infix=legacy_infix,
        )
        if formats:
            findings.append(
                Finding("citation-format", "citation-format", ", ".join(formats))
            )
    if "noncanonical-reference" in checks:
        lines = check_noncanonical_reference(
            text,
            scan_start=noncanonical_scan_start,
            path_pattern=noncanonical_path_pattern,
        )
        if lines:
            findings.append(
                Finding(
                    "noncanonical-reference",
                    "noncanonical-reference",
                    "docs/features/配下への規範参照が残存: "
                    + ",".join(str(line) for line in lines),
                )
            )
    if "link-target" in checks:
        targets = check_link_targets(text, root, link_base_dir)
        if targets:
            findings.append(
                Finding("link-target", "link-target", "実在しないリンク: " + ",".join(targets))
            )
    if (
        "reference-class" in checks
        and profile is not None
        and "reference-class" in profile.required_checks
    ):
        findings.extend(
            check_reference_classes(
                text,
                profile=profile,
                document_path=document_path,
                root=root,
            )
        )
    profile_checks = (
        checks & profile.required_checks & PROFILE_ASSET_CHECK_IDS
        if profile is not None
        else frozenset()
    )
    if profile_checks:
        if raw_manifest is None:
            raise CheckError("プロファイル資産検査にraw manifestが必要")
        assets = doc_check_profile.load_assets(profile)
        if "collection-consistency" in profile_checks:
            findings.extend(
                check_collection_consistency(profile, assets, raw_manifest)
            )
        if "forbidden-structure" in profile_checks:
            findings.extend(
                check_forbidden_structures(
                    profile,
                    assets,
                    text=text,
                    raw_manifest=raw_manifest,
                )
            )
        if "cross-consistency" in profile_checks:
            findings.extend(
                check_cross_consistency(
                    profile,
                    assets,
                    text=text,
                    raw_manifest=raw_manifest,
                )
            )
        if "baseline-digest" in profile_checks:
            findings.extend(check_baseline_digest(profile, assets, invariants))
        if "unique-owner" in profile_checks:
            findings.extend(check_unique_owner(profile, assets, invariants))
    return findings


def _parse_csv(value: str | None, option: str) -> frozenset[str] | None:
    if value is None:
        return None
    items = [item.strip() for item in value.split(",") if item.strip()]
    if not items:
        raise CheckError(f"{option} にIDがない")
    return frozenset(items)


def select_checks_and_defects(
    defects: dict[str, Defect],
    defect_csv: str | None,
    check_csv: str | None,
) -> tuple[frozenset[str], tuple[Defect, ...], bool]:
    """CLIセレクタを検証し、実行する検査と欠陥を決める。

    ``--defects`` と ``--checks`` の併用時は和集合ではなく積集合とする。
    欠陥IDを持たない4検査は ``--defects`` 条件を満たせないため実行しない。

    Args:
        defects: 欠陥oracle。
        defect_csv: カンマ区切り欠陥ID。未指定なら ``None``。
        check_csv: カンマ区切り検査ID。未指定なら ``None``。

    Returns:
        ``(実行検査ID, 実行欠陥, 全体検査を許可するか)``。

    Raises:
        CheckError: 未知IDまたは人間照合IDを指定した場合。
    """
    selected_defect_ids = _parse_csv(defect_csv, "--defects")
    selected_check_ids = _parse_csv(check_csv, "--checks")
    if selected_check_ids is not None:
        unknown_checks = sorted(selected_check_ids - CHECK_ID_SET)
        if unknown_checks:
            raise CheckError("未知の検査ID: " + ",".join(unknown_checks))

    if selected_defect_ids is not None:
        unknown_defects = sorted(selected_defect_ids - set(defects))
        if unknown_defects:
            raise CheckError("未知の欠陥ID: " + ",".join(unknown_defects))
        human = sorted(
            defect_id
            for defect_id in selected_defect_ids
            if defects[defect_id].detection != "machine"
        )
        if human:
            raise CheckError("人間照合の欠陥IDは指定できない: " + ",".join(human))
        candidates = [defects[defect_id] for defect_id in selected_defect_ids]
    else:
        candidates = [defect for defect in defects.values() if defect.detection == "machine"]

    if selected_check_ids is not None:
        active_checks = selected_check_ids
    elif selected_defect_ids is not None:
        active_checks = frozenset(
            defect.check for defect in candidates if defect.check is not None
        )
    else:
        active_checks = CHECK_ID_SET

    selected_defects = tuple(
        sorted(
            (
                defect
                for defect in candidates
                if defect.check is not None and defect.check in active_checks
            ),
            key=lambda defect: defect.id,
        )
    )
    return active_checks, selected_defects, selected_defect_ids is None


def run_checks(
    text: str,
    root: Path,
    manifest: dict[str, ManifestRelation],
    defects: dict[str, Defect],
    defect_csv: str | None = None,
    check_csv: str | None = None,
    link_base_dir: Path | None = None,
    invariants: Any | None = None,
    profile: Any | None = None,
    raw_manifest: Mapping[str, Any] | None = None,
    document_path: Path | None = None,
    *,
    section_id_grammar: str = DEFAULT_SECTION_ID_GRAMMAR,
    preamble: str = DEFAULT_PREAMBLE,
    legacy_prefixes: Sequence[str] = DEFAULT_LEGACY_PREFIXES,
    legacy_infix: str = DEFAULT_LEGACY_INFIX,
    noncanonical_scan_start: str = DEFAULT_NONCANONICAL_SCAN_START,
    noncanonical_path_pattern: str = NONCANONICAL_PATH_RE.pattern,
    declaration_section: str = DEFAULT_DECLARATION_SECTION,
    declaration_row_prefix: str = DEFAULT_DECLARATION_ROW_PREFIX,
    declaration_column_count: int = DEFAULT_DECLARATION_COLUMN_COUNT,
) -> tuple[Finding, ...]:
    """選択条件に従って設計伝播検査を実行する。

    Args:
        text: 検査対象のMarkdown本文。
        root: リポジトリルート。
        manifest: 関係マニフェスト。
        defects: 欠陥oracle。
        defect_csv: ``--defects`` 相当のカンマ区切りID。
        check_csv: ``--checks`` 相当のカンマ区切りID。
        link_base_dir: 相対Markdownリンクの解決基準。
        invariants: 検証済みの不変条件宣言資産。未指定なら結合検査を省く。
        profile: 宣言評価に使う検証済みプロファイル。
        raw_manifest: 資産・構造検査で使うマニフェスト原値。
        document_path: 参照分類で使う検査対象文書の実パス。
        section_id_grammar: scopeの節IDを判定する正規表現。
        preamble: 冒頭スコープの切り出し方式。
        legacy_prefixes: legacy引用と認識するパス接頭辞。
        legacy_infix: legacy引用と認識するパス中間文字列。
        noncanonical_scan_start: 非正本参照の走査開始見出し。
        noncanonical_path_pattern: 非正本参照を表すパスの正規表現。
        declaration_section: 宣言表を置く節ID。
        declaration_row_prefix: 関係行を識別する接頭辞。
        declaration_column_count: 関係行に必要な列数。

    Returns:
        欠陥IDまたは全体検査ID単位の違反。
    """
    if invariants is not None:
        machine_defect_ids = {
            defect.id for defect in defects.values() if defect.detection == "machine"
        }
        forbidden_defect_ids = {
            defect.id
            for defect in defects.values()
            if defect.detection == "machine"
            and defect.invariant is not None
            and defect.invariant.forbidden
        }
        doc_check_profile.validate_binding_rules(
            invariants,
            machine_defect_ids=machine_defect_ids,
            forbidden_defect_ids=forbidden_defect_ids,
            legacy_branch_ids=LEGACY_STRUCTURAL_BRANCH_IDS,
        )
    checks, selected_defects, allow_global = select_checks_and_defects(
        defects, defect_csv, check_csv
    )
    if profile is not None and defect_csv is None and check_csv is None:
        checks = checks & profile.required_checks
        selected_defects = tuple(
            defect
            for defect in selected_defects
            if defect.check in profile.required_checks
        )
    findings: list[Finding] = []
    for defect in selected_defects:
        reason = defect_violation_reason(
            defect,
            text,
            manifest,
            section_id_grammar=section_id_grammar,
            preamble=preamble,
            invariants=invariants,
            profile=profile,
        )
        if reason is not None:
            assert defect.check is not None
            findings.append(Finding(defect.id, defect.check, reason))
    if allow_global:
        findings.extend(
            _global_findings(
                text,
                root,
                document_path or (profile.document if profile is not None else root),
                manifest,
                checks,
                link_base_dir,
                profile,
                invariants,
                raw_manifest,
                legacy_prefixes=legacy_prefixes,
                legacy_infix=legacy_infix,
                noncanonical_scan_start=noncanonical_scan_start,
                noncanonical_path_pattern=noncanonical_path_pattern,
                declaration_section=declaration_section,
                declaration_row_prefix=declaration_row_prefix,
                declaration_column_count=declaration_column_count,
            )
        )
    return tuple(sorted(findings, key=lambda finding: finding.identifier))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """コマンドライン引数を解釈する。

    Args:
        argv: テスト時に指定する引数列。省略時はコマンドライン引数を使う。

    Returns:
        解釈済み引数。
    """
    parser = argparse.ArgumentParser(description="同期プロトコル設計の伝播を突合する")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="リポジトリルート(既定: カレントディレクトリ)",
    )
    parser.add_argument(
        "--document",
        type=Path,
        help="検査対象文書(未指定時はプロファイルのdocument)",
    )
    parser.add_argument(
        "--profile",
        type=Path,
        help="使用するプロファイル(未指定時はレジストリ先頭のプロファイル)",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        help="プロファイルレジストリ(既定: 本番レジストリ)",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        help="関係マニフェスト(未指定時はプロファイルのmanifest)",
    )
    parser.add_argument(
        "--defects-file",
        type=Path,
        help="欠陥oracle(未指定時はプロファイルのdefects)",
    )
    parser.add_argument("--defects", help="実行する機械欠陥IDのカンマ区切り")
    parser.add_argument("--checks", help="実行する検査IDのカンマ区切り")
    return parser.parse_args(argv)


def _resolve(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


def _run_registered_profiles(profiles: Sequence[Any], root: Path) -> int:
    """登録順に全プロファイルを実行し、2優先で終了コードを合成する。"""
    exit_codes: list[int] = []
    for profile in profiles:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exit_code = main(
                ["--root", str(root), "--profile", str(profile.path)]
            )
        exit_codes.append(exit_code)
        prefix = f"[{profile.name}]"
        output_lines = stdout.getvalue().splitlines()
        error_lines = stderr.getvalue().splitlines()
        for line in output_lines:
            print(f"{prefix} {line}")
        for line in error_lines:
            print(f"{prefix} {line}", file=sys.stderr)
        if not output_lines and not error_lines:
            print(f"{prefix} document={profile.document} rc={exit_code}")
    return max(exit_codes, default=2)


def main(argv: Sequence[str] | None = None) -> int:
    """検査を実行し、違反の有無に応じた終了コードを返す。

    Args:
        argv: テスト時に指定する引数列。省略時はコマンドライン引数を使う。

    Returns:
        違反なしなら0、違反ありなら1、入力やセレクタの不正なら2。
    """
    try:
        args = parse_args(argv)
        root = args.root.resolve()
        enumerate_registry = (
            args.profile is None
            and args.document is None
            and args.manifest is None
            and args.defects_file is None
            and args.checks is None
            and args.defects is None
        )
        if args.profile is not None:
            profile = doc_check_profile.load_profile(args.profile, root=root)
        else:
            registry_path = args.registry
            if registry_path is None:
                registry_path = doc_check_profile.default_registry_path(root)
            registry = doc_check_profile.load_registry(registry_path, root=root)
            profiles = doc_check_profile.resolve_profiles(registry, root=root)
            if enumerate_registry and len(profiles) > 1:
                return _run_registered_profiles(profiles, root)
            profile = profiles[0]

        document = (
            _resolve(root, args.document)
            if args.document is not None
            else profile.document
        )
        manifest_path = (
            _resolve(root, args.manifest)
            if args.manifest is not None
            else profile.manifest
        )
        defects_path = (
            _resolve(root, args.defects_file)
            if args.defects_file is not None
            else profile.defects
        )
        try:
            text = document.read_text(encoding="utf-8")
        except OSError as error:
            raise CheckError(f"検査対象を読めない: {document}: {error}") from error
        raw_manifest_value = doc_check_profile.load_json(manifest_path)
        if not isinstance(raw_manifest_value, Mapping):
            raise CheckError(f"関係マニフェストがobjectでない: {manifest_path}")
        requested_checks = _parse_csv(args.checks, "--checks")
        manifest = (
            load_manifest(manifest_path)
            if requested_checks is None
            or bool(requested_checks & LEGACY_PROP_CHECK_IDS)
            else {}
        )
        defects = load_defects(defects_path)
        invariants = (
            doc_check_profile.load_invariants(
                profile.invariants,
                schema_dir=profile.schema_dir,
            )
            if profile.invariants is not None
            else None
        )
        citation = profile.raw["citation"]
        declaration_table = profile.raw["declaration_table"]
        findings = run_checks(
            text,
            root,
            manifest,
            defects,
            defect_csv=args.defects,
            check_csv=args.checks,
            link_base_dir=profile.link_base_dir,
            invariants=invariants,
            profile=profile,
            raw_manifest=raw_manifest_value,
            document_path=document,
            section_id_grammar=profile.raw["section_id_grammar"],
            preamble=profile.raw["preamble"],
            legacy_prefixes=citation["legacy_prefixes"],
            legacy_infix=citation["legacy_infix"],
            noncanonical_scan_start=profile.raw["noncanonical_scan_start"],
            noncanonical_path_pattern=profile.raw["noncanonical_path_pattern"],
            declaration_section=declaration_table["section"],
            declaration_row_prefix=declaration_table["row_prefix"],
            declaration_column_count=declaration_table["column_count"],
        )
    except (
        CheckError,
        doc_check_profile.ProfileError,
        doc_check_invariants.doc_check_profile.ProfileError,
    ) as error:
        print(f"check_design_propagation.py: {error}", file=sys.stderr)
        return 2
    if requested_checks is not None:
        for check_id in CHECK_IDS:
            if check_id in requested_checks and check_id in profile.not_applicable:
                print(f"{check_id}: 対象なし: {profile.not_applicable[check_id]}")
    for finding in findings:
        print(f"{finding.identifier}: [{finding.check}] {finding.reason}", file=sys.stderr)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
