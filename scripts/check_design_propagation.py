"""同期プロトコル設計の表間伝播、参照、残存欠陥を検査する。"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
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
)
CHECK_ID_SET = frozenset(CHECK_IDS)
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
    relations: dict[str, ManifestRelation] = {}
    for key, value in raw.items():
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


def _global_findings(
    text: str,
    root: Path,
    manifest: dict[str, ManifestRelation],
    checks: frozenset[str],
    link_base_dir: Path | None,
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
                manifest,
                checks,
                link_base_dir,
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
        if args.profile is not None:
            profile = doc_check_profile.load_profile(args.profile, root=root)
        else:
            registry_path = args.registry
            if registry_path is None:
                registry_path = doc_check_profile.default_registry_path(root)
            registry = doc_check_profile.load_registry(registry_path, root=root)
            profiles = doc_check_profile.resolve_profiles(registry, root=root)
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
        manifest = load_manifest(manifest_path)
        defects = load_defects(defects_path)
        invariants = (
            doc_check_profile.load_invariants(profile.invariants)
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
    for finding in findings:
        print(f"{finding.identifier}: [{finding.check}] {finding.reason}", file=sys.stderr)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
