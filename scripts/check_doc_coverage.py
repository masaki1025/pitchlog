"""要件書の安定 ID 抽出結果と同期設計の帰属表を全数検査する。"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


def _load_profile_module() -> Any:
    """隣接する共通プロファイルローダーをファイルパスから読む。"""
    path = Path(__file__).resolve().parent / "doc_check_profile.py"
    spec = importlib.util.spec_from_file_location(
        "check_doc_coverage_doc_check_profile",
        path,
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"プロファイルローダーを読み込めない: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


doc_check_profile = _load_profile_module()

DEFAULT_REQUIREMENTS = Path("docs/requirements/requirements-pitchlog-2026-07-22.md")
DEFAULT_DOCUMENT = Path("docs/design/sync-protocol.md")
DEFAULT_UNIVERSE = Path("scripts/design_relations/req-universe.json")

COVERAGE_CHECK_IDS = ("attribution", "ledger")
COVERAGE_CHECK_ID_SET = frozenset(COVERAGE_CHECK_IDS)
ATTRIBUTION_DESTINATION_CHECK_ID = "attribution-destination"
ATTRIBUTION_DIRECT_CHECK_ID = "attribution-direct"
COVERAGE_SELECTABLE_CHECK_IDS = (
    *COVERAGE_CHECK_IDS,
    ATTRIBUTION_DESTINATION_CHECK_ID,
    ATTRIBUTION_DIRECT_CHECK_ID,
)
COVERAGE_SELECTABLE_CHECK_ID_SET = frozenset(COVERAGE_SELECTABLE_CHECK_IDS)
CATEGORY_IDS = (
    "requirements",
    "sections",
    "blocks",
    "appendix_items",
    "identified_table_rows",
    "keyed_table_rows",
    "release_dod",
    "clause_subitems",
)
ASSIGNMENT_KINDS = frozenset({"同期側で決める", "境界として参照", "対象外"})
ASSIGNMENT_HEADER = ("ID", "区分", "本書の対応箇所または対象外の理由")
LEDGER_HEADER = (
    "主張 ID",
    "主張内 ordinal",
    "参照先パス",
    "参照先の種別",
    "参照先の安定 ID",
    "判定",
    "是正内容",
)
REFERENCE_KINDS = frozenset({"要件", "正本", "legacy"})
LEDGER_VERDICTS = frozenset({"支持", "不支持", "射程過大", "誤典拠"})
REQUIREMENTS_PATH = "docs/requirements/requirements-pitchlog-2026-07-22.md"
LEDGER_SECTION_ID = "11-5"
ATTRIBUTION_SECTION_RE = r"^11-3\."
DESTINATION_GRAMMAR = "sync-v1"

HEADING_RE = re.compile(r"^(?P<marks>#{1,6})\s+(?P<title>.+)$")
REQUIREMENT_RE = re.compile(r"^####\s+((?:FR|NFR)-\d{3}):")
NUMBERED_SECTION_RE = re.compile(
    r"^#{2,4}\s+(\d+(?:\.\d+)*(?:-\d+)?)(?:\.|\s|$)"
)
BLOCK_RE = re.compile(r"^###\s+ブロック(\d+):")
APPENDIX_RE = re.compile(r"^##\s+付録([A-F]):")
APPENDIX_HEADING_ITEM_RE = re.compile(r"^###\s+([AEF]-\d+[a-z]?)\b")
ORDERED_ITEM_RE = re.compile(r"^(\d+)\.\s+")
IDENTIFIED_ROW_RE = re.compile(r"^\|\s*((?:G|R)-\d+)\s*\|")
MARKDOWN_REFERENCE_RE = re.compile(
    r"\[(?P<label>[^\]]+)\]\((?P<target>[^)\s]+\.md(?:#[^)\s]+)?)\)"
)
REQ_LINE_REFERENCE_RE = re.compile(r"\bREQ:(?P<line>\d+)\b")
PATH_LINE_REFERENCE_RE = re.compile(
    r"(?P<path>(?:docs/|\.\.?/)[^`\s()\[\]]+\.md):(?P<line>\d+)"
)
SHORTHAND_LINE_REFERENCE_RE = re.compile(r"(?:同\s+`?)?(?<![\w.]):(?P<line>\d+)\b")
STABLE_ID_RE = re.compile(
    r"^(?:(?:FR|NFR)-\d{3}(?:\([a-z]\))?(?:/[A-Z]\d+)?"
    r"|付録[A-F]"
    r"|(?:付録[A-F]/)?[A-Z]-\d+[a-z]?"
    r"|[A-Z]+-\d+(?:-[A-Za-z0-9]+)?"
    r"|\d+(?:\.\d+)*(?:-\d+)?"
    r"|\d+-\d+(?:-[A-Za-z0-9]+)?"
    r"|NFR-018/\([αβa-d]\)(?:[①-⑧])?)$"
)


class CoverageError(Exception):
    """入力文書または oracle の構造不正を表す。"""


@dataclass(frozen=True)
class Universe:
    """要件母集合の検証済みデータを表す。

    Attributes:
        categories: カテゴリ名ごとの期待 ID 列。
        ids: 全カテゴリを結合した期待 ID 集合。
    """

    categories: dict[str, tuple[str, ...]]
    ids: frozenset[str]


@dataclass(frozen=True)
class Assignment:
    """11-3 の帰属表にある 1 行を表す。

    Attributes:
        id: 要件の安定 ID。
        kind: 帰属区分。
        destination: 本書の節、または対象外の理由。
        sections: destination から展開した帰属先節。対象外なら空。
    """

    id: str
    kind: str
    destination: str
    sections: tuple[str, ...] = ()


@dataclass(frozen=True)
class Finding:
    """帰属検査の 1 違反を表す。

    Attributes:
        check: 違反経路の識別子。
        reason: 違反内容。
    """

    check: str
    reason: str


@dataclass(frozen=True)
class Citation:
    """本文から抽出した引用 1 件を表す。

    Attributes:
        claim_id: 見出し ID と段落・表行連番からなる主張 ID。
        ordinal: 同一主張・同一参照先での 1 始まりの出現順。
        target_path: リポジトリ相対の参照先パス。
        target_kind: ``要件``、``正本``、``legacy`` のいずれか。
        stable_id: 参照先文書内の安定 ID。
    """

    claim_id: str
    ordinal: int
    target_path: str
    target_kind: str
    stable_id: str

    @property
    def key(self) -> tuple[str, int, str, str]:
        """台帳と突合する 4 要素キーを返す。"""
        return (self.claim_id, self.ordinal, self.target_path, self.stable_id)


@dataclass(frozen=True)
class LedgerEntry:
    """意味照合台帳の 1 行を表す。

    Attributes:
        claim_id: 本書の主張 ID。
        ordinal: 同一主張・同一参照先での出現順。
        target_path: リポジトリ相対の参照先パス。
        target_kind: 参照先の種別。
        stable_id: 参照先文書内の安定 ID。
        verdict: 意味照合の判定。
        correction: ``支持`` 以外のときの是正内容。
    """

    claim_id: str
    ordinal: int
    target_path: str
    target_kind: str
    stable_id: str
    verdict: str
    correction: str

    @property
    def key(self) -> tuple[str, int, str, str]:
        """本文の引用と突合する 4 要素キーを返す。"""
        return (self.claim_id, self.ordinal, self.target_path, self.stable_id)


def _read_text(path: Path, label: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        raise CoverageError(f"{label}を読めない: {path}: {error}") from error


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise CoverageError(f"要件母集合を読めない: {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise CoverageError(f"要件母集合の JSON が不正: {path}: {error}") from error


def load_universe(path: Path) -> Universe:
    """要件母集合を読み、カテゴリ・件数・重複を検証する。

    Args:
        path: ``req-universe.json`` のパス。

    Returns:
        検証済みの要件母集合。

    Raises:
        CoverageError: JSON または母集合の構造が不正な場合。
    """
    raw = _read_json(path)
    if not isinstance(raw, dict):
        raise CoverageError("要件母集合のルートはオブジェクトでなければならない")
    raw_categories = raw.get("categories")
    if not isinstance(raw_categories, dict):
        raise CoverageError("要件母集合に categories がない")
    if set(raw_categories) != set(CATEGORY_IDS):
        missing = sorted(set(CATEGORY_IDS) - set(raw_categories))
        unknown = sorted(set(raw_categories) - set(CATEGORY_IDS))
        raise CoverageError(f"要件母集合のカテゴリ不一致: 不足={missing}, 未知={unknown}")

    categories: dict[str, tuple[str, ...]] = {}
    all_ids: list[str] = []
    for category_id in CATEGORY_IDS:
        raw_category = raw_categories[category_id]
        if not isinstance(raw_category, dict):
            raise CoverageError(f"カテゴリがオブジェクトでない: {category_id}")
        raw_ids = raw_category.get("ids")
        count = raw_category.get("count")
        if not isinstance(raw_ids, list) or not all(
            isinstance(identifier, str) for identifier in raw_ids
        ):
            raise CoverageError(f"カテゴリの ids が文字列配列でない: {category_id}")
        if not isinstance(count, int) or count != len(raw_ids):
            raise CoverageError(f"カテゴリの count と ids 件数が不一致: {category_id}")
        ids = tuple(raw_ids)
        categories[category_id] = ids
        all_ids.extend(ids)

    if len(all_ids) != len(set(all_ids)):
        duplicates = sorted(
            identifier for identifier, count in Counter(all_ids).items() if count > 1
        )
        raise CoverageError(f"要件母集合の ID が重複: {duplicates}")
    total = raw.get("total")
    if not isinstance(total, int) or total != len(all_ids):
        raise CoverageError("要件母集合の total と全 ID 件数が不一致")
    return Universe(categories=categories, ids=frozenset(all_ids))


def _section_lines(lines: list[str], title_pattern: re.Pattern[str]) -> list[str]:
    start: int | None = None
    level = 0
    for index, line in enumerate(lines):
        match = HEADING_RE.match(line)
        if match is None or title_pattern.match(match.group("title")) is None:
            continue
        start = index
        level = len(match.group("marks"))
        break
    if start is None:
        return []
    end = len(lines)
    for index in range(start + 1, len(lines)):
        match = HEADING_RE.match(lines[index])
        if match is not None and len(match.group("marks")) <= level:
            end = index
            break
    return lines[start:end]


def _table_cells(line: str) -> list[str] | None:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return None
    return [cell.strip() for cell in stripped[1:-1].split("|")]


def _table_first_column(lines: list[str], header: str) -> list[str]:
    for index, line in enumerate(lines):
        cells = _table_cells(line)
        if cells is None or not cells or cells[0] != header:
            continue
        rows: list[str] = []
        for row in lines[index + 2 :]:
            row_cells = _table_cells(row)
            if row_cells is None:
                break
            if not row_cells:
                continue
            rows.append(row_cells[0])
        return rows
    return []


def _without_emphasis(value: str) -> str:
    return value.replace("**", "").strip()


def _leading_bold_key(value: str) -> str:
    match = re.match(r"^\*\*(.+?)\*\*", value)
    return match.group(1).strip() if match is not None else _without_emphasis(value)


def _extract_keyed_rows(lines: list[str]) -> list[str]:
    specifications = (
        (r"^6\.1\s", "データ", "6.1", _without_emphasis),
        (r"^10\.\s", "項目", "10章", _leading_bold_key),
        (r"^FR-034:", "要求されるリソース", "FR-034/認可行列", _without_emphasis),
        (r"^付録C:", "設定値", "付録C", _without_emphasis),
    )
    identifiers: list[str] = []
    for title_pattern, header, prefix, normalizer in specifications:
        section = _section_lines(lines, re.compile(title_pattern))
        for key in _table_first_column(section, header):
            identifiers.append(f"{prefix}/{normalizer(key)}")
    return identifiers


def _extract_appendix_items(lines: list[str]) -> list[str]:
    current: str | None = None
    identifiers: list[str] = []
    for line in lines:
        appendix = APPENDIX_RE.match(line)
        if appendix is not None:
            current = appendix.group(1)
            continue
        heading_item = APPENDIX_HEADING_ITEM_RE.match(line)
        if current in {"A", "E", "F"} and heading_item is not None:
            identifiers.append(f"付録{current}/{heading_item.group(1)}")
            continue
        ordered_item = ORDERED_ITEM_RE.match(line)
        if current in {"B", "D"} and ordered_item is not None:
            number = ordered_item.group(1)
            identifiers.append(f"付録{current}/{current}-{number}")
    return identifiers


def _contains_bold_label(section: list[str], label: str) -> bool:
    marker = re.compile(rf"\*\*{re.escape(label)}(?:\*\*|\s)")
    return any(marker.search(line) is not None for line in section)


def _extract_clause_subitems(lines: list[str]) -> list[str]:
    identifiers: list[str] = []
    nfr018 = _section_lines(lines, re.compile(r"^NFR-018:"))
    for label in ("(α)", "(β)"):
        if _contains_bold_label(nfr018, label):
            identifiers.append(f"NFR-018/{label}")
    beta_enumeration = next(
        (line for line in nfr018 if "現時点の列挙" in line),
        "",
    )
    for ordinal in "①②③④⑤⑥⑦⑧":
        if ordinal in beta_enumeration:
            identifiers.append(f"NFR-018/(β){ordinal}")
    for label in ("(a)", "(b)", "(c)", "(d)"):
        if _contains_bold_label(nfr018, label):
            identifiers.append(f"NFR-018/{label}")

    nfr019 = _section_lines(lines, re.compile(r"^NFR-019:"))
    nfr019_text = "\n".join(nfr019)
    for label in ("(a)", "(b)", "(c)", "(d)"):
        if re.search(rf"(?<![\w-]){re.escape(label)}\s+", nfr019_text):
            identifiers.append(f"NFR-019/{label}")

    for requirement, labels in (
        ("FR-012", ("E0", "E1", "E2", "E3")),
        ("NFR-007", ("E4",)),
        ("NFR-019", ("E5",)),
    ):
        section = _section_lines(lines, re.compile(rf"^{requirement}:"))
        for label in labels:
            if _contains_bold_label(section, label):
                identifier = (
                    f"NFR-019(d)/{label}" if label == "E5" else f"{requirement}/{label}"
                )
                identifiers.append(identifier)
    return identifiers


def extract_requirement_ids(text: str) -> dict[str, tuple[str, ...]]:
    """要件書から 8 カテゴリの安定 ID を抽出する。

    oracle の列挙値は参照せず、要件書の見出し、指定されたキー表、条内ラベルを
    直接解析する。受入基準の無採番行は抽出しない。

    Args:
        text: 要件書の Markdown 全文。

    Returns:
        カテゴリ名ごとの抽出 ID 列。
    """
    lines = text.splitlines()
    requirements = [
        match.group(1) for line in lines if (match := REQUIREMENT_RE.match(line))
    ]
    sections = [
        match.group(1) for line in lines if (match := NUMBERED_SECTION_RE.match(line))
    ]
    blocks = [f"ブロック{match.group(1)}" for line in lines if (match := BLOCK_RE.match(line))]
    identified_rows = [
        match.group(1) for line in lines if (match := IDENTIFIED_ROW_RE.match(line))
    ]
    chapter8 = _section_lines(lines, re.compile(r"^8\.\s"))
    release_dod = [
        f"8章DoD/{match.group(1)}"
        for line in chapter8
        if (match := ORDERED_ITEM_RE.match(line))
    ]
    extracted = {
        "requirements": tuple(requirements),
        "sections": tuple(sections),
        "blocks": tuple(blocks),
        "appendix_items": tuple(_extract_appendix_items(lines)),
        "identified_table_rows": tuple(identified_rows),
        "keyed_table_rows": tuple(_extract_keyed_rows(lines)),
        "release_dod": tuple(release_dod),
        "clause_subitems": tuple(_extract_clause_subitems(lines)),
    }
    return extracted


def _section_text(text: str, title_pattern: re.Pattern[str]) -> str:
    return "\n".join(_section_lines(text.splitlines(), title_pattern))


def parse_assignment_destination(
    kind: str,
    destination: str,
    *,
    destination_grammar: str = DESTINATION_GRAMMAR,
) -> tuple[str, ...]:
    """区分別の帰属先文法を検証し、節IDへ展開する。

    Args:
        kind: 帰属区分。
        destination: 帰属表の3列目。
        destination_grammar: プロファイルが指定する文法名。

    Returns:
        展開した節ID。対象外の理由文なら空タプル。

    Raises:
        CoverageError: 文法名が未対応か、帰属先を解析できない場合。
    """
    if destination_grammar != DESTINATION_GRAMMAR:
        raise CoverageError(f"未対応の destination 文法: {destination_grammar}")
    if kind == "対象外":
        if not destination.strip():
            raise CoverageError("対象外の理由文が空")
        return ()

    expression, separator, description = destination.partition("。")
    expression = expression.strip()
    if not expression or (separator and not description.strip()):
        raise CoverageError(f"帰属先の節式が不正: {destination}")

    sections: list[str] = []
    section_atom = re.compile(r"\d+(?:-\d+(?:-[A-Z])?)?")
    chapter_range = re.compile(r"(\d+)〜(\d+)")
    for token in expression.split("・"):
        if section_atom.fullmatch(token) is not None:
            sections.append(token)
            continue
        range_match = chapter_range.fullmatch(token)
        if range_match is None:
            raise CoverageError(f"帰属先に未解析トークンがある: {token}")
        first = int(range_match.group(1))
        last = int(range_match.group(2))
        if first > last:
            raise CoverageError(f"帰属先の章範囲が逆順: {token}")
        sections.extend(str(chapter) for chapter in range(first, last + 1))
    return tuple(sections)


def parse_assignments(
    text: str,
    *,
    section_re: str = ATTRIBUTION_SECTION_RE,
    assignment_kinds: frozenset[str] = ASSIGNMENT_KINDS,
    assignment_header: Sequence[str] = ASSIGNMENT_HEADER,
    destination_grammar: str = DESTINATION_GRAMMAR,
) -> tuple[Assignment, ...]:
    """同期設計 11-3 の帰属表を読み取る。

    Args:
        text: 同期プロトコル設計の Markdown 全文。
        section_re: 帰属表を持つ節見出しの正規表現。
        assignment_kinds: 許可する帰属区分。
        assignment_header: 帰属表のヘッダー。
        destination_grammar: 帰属先の文法名。

    Returns:
        表に記載された順の帰属行。

    Raises:
        CoverageError: 11-3 または所定ヘッダーの帰属表がない場合。
    """
    try:
        section_pattern = re.compile(section_re)
    except re.error as error:
        raise CoverageError(f"帰属表の節正規表現が不正: {section_re}: {error}") from error
    section = _section_text(text, section_pattern)
    if not section:
        raise CoverageError(f"本書に帰属表の節がない: {section_re}")
    lines = section.splitlines()
    header_index: int | None = None
    for index, line in enumerate(lines):
        cells = _table_cells(line)
        if cells is not None and tuple(cells) == tuple(assignment_header):
            header_index = index
            break
    if header_index is None:
        raise CoverageError("11-3 に所定ヘッダーの帰属表がない")

    assignments: list[Assignment] = []
    for line in lines[header_index + 2 :]:
        cells = _table_cells(line)
        if cells is None:
            break
        if len(cells) != 3:
            raise CoverageError(f"帰属表の列数が 3 でない: {line}")
        identifier, kind, destination = (_without_emphasis(cell) for cell in cells)
        if not identifier or not kind or not destination:
            raise CoverageError(f"帰属表に空セルがある: {line}")
        if kind not in assignment_kinds:
            raise CoverageError(f"帰属表の区分が不正: {identifier}: {kind}")
        sections = parse_assignment_destination(
            kind,
            destination,
            destination_grammar=destination_grammar,
        )
        assignments.append(Assignment(identifier, kind, destination, sections))
    if not assignments:
        raise CoverageError("11-3 の帰属表にデータ行がない")
    return tuple(assignments)


def check_coverage(
    extracted: dict[str, tuple[str, ...]],
    universe: Universe,
    assignments: Sequence[Assignment],
) -> tuple[Finding, ...]:
    """抽出結果と帰属表を母集合へ突合する。

    Args:
        extracted: 要件書からのカテゴリ別抽出結果。
        universe: ステップ 7 で固定した要件母集合。
        assignments: 本書 11-3 の帰属行。

    Returns:
        取りこぼし、未帰属、重複帰属、未知 ID の違反列。
    """
    findings: list[Finding] = []
    for category_id in CATEGORY_IDS:
        actual = set(extracted.get(category_id, ()))
        expected = set(universe.categories[category_id])
        missing = sorted(expected - actual)
        unknown = sorted(actual - expected)
        if missing or unknown:
            findings.append(
                Finding(
                    "extractor-mismatch",
                    f"{category_id}: 抽出不足={missing}, oracle外の抽出={unknown}",
                )
            )

    assignment_ids = [assignment.id for assignment in assignments]
    assigned = set(assignment_ids)
    missing_assignments = sorted(universe.ids - assigned)
    if missing_assignments:
        findings.append(Finding("unassigned", f"帰属表にない ID={missing_assignments}"))
    duplicates = sorted(
        identifier for identifier, count in Counter(assignment_ids).items() if count > 1
    )
    if duplicates:
        findings.append(Finding("duplicate-assignment", f"重複 ID={duplicates}"))
    unknown_assignments = sorted(assigned - universe.ids)
    if unknown_assignments:
        findings.append(Finding("unknown-assignment", f"母集合外 ID={unknown_assignments}"))
    return tuple(findings)


def check_attribution_destinations(
    text: str,
    assignments: Sequence[Assignment],
    *,
    destination_grammar: str = DESTINATION_GRAMMAR,
) -> tuple[Finding, ...]:
    """帰属先節の実在と要件IDの根拠行を検査する。

    Args:
        text: 帰属表と帰属先節を持つ Markdown 全文。
        assignments: 検査する帰属行。
        destination_grammar: 帰属先の文法名。

    Returns:
        実在しない節と根拠行不足の違反列。
    """
    findings: list[Finding] = []
    for assignment in assignments:
        if assignment.kind == "対象外":
            continue
        sections = assignment.sections or parse_assignment_destination(
            assignment.kind,
            assignment.destination,
            destination_grammar=destination_grammar,
        )
        section_texts: list[str] = []
        missing: list[str] = []
        for section_id in sections:
            pattern = re.compile(rf"^{re.escape(section_id)}(?:[.\s(])")
            section = _section_text(text, pattern)
            if section:
                section_texts.append(section)
            else:
                missing.append(section_id)
        if missing:
            findings.append(
                Finding(
                    ATTRIBUTION_DESTINATION_CHECK_ID,
                    f"{assignment.id}: 帰属先の節が存在しない: {missing}",
                )
            )
            continue

        stable_id_match = re.match(r"(?:FR|NFR)-\d{3}", assignment.id)
        stable_id = (
            stable_id_match.group(0)
            if stable_id_match is not None
            else assignment.id
        )
        stable_id_re = re.compile(
            rf"(?<![A-Za-z0-9-]){re.escape(stable_id)}(?![A-Za-z0-9-])"
        )
        if not any(
            stable_id_re.search(line) is not None
            for section in section_texts
            for line in section.splitlines()
        ):
            findings.append(
                Finding(
                    ATTRIBUTION_DESTINATION_CHECK_ID,
                    f"{assignment.id}: 帰属先に要件ID {stable_id} の根拠行がない",
                )
            )
    return tuple(findings)


def _heading_identifier(
    title: str,
    level: int,
    parents: dict[int, str],
) -> str:
    title = _without_emphasis(title)
    if level == 1:
        return "document"
    token = re.match(
        r"^(?P<id>(?:\d+(?:\.\d+)*(?:-\d+(?:-[A-Za-z0-9]+)?)?|[A-Z]+-\d+))"
        r"(?:[.:\s]|$)",
        title,
    )
    if token is not None:
        return token.group("id")
    parent = next(
        (
            parents[parent_level]
            for parent_level in range(level - 1, 0, -1)
            if parent_level in parents
        ),
        "document",
    )
    label = re.sub(r"\s+", "-", title.strip())
    return f"{parent}/{label}"


def _is_table_separator(line: str) -> bool:
    cells = _table_cells(line)
    return cells is not None and bool(cells) and all(
        re.fullmatch(r":?-{3,}:?", cell) is not None for cell in cells
    )


def _claim_lines(
    text: str,
    *,
    ledger_section_id: str = LEDGER_SECTION_ID,
) -> tuple[tuple[str, str], ...]:
    lines = text.splitlines()
    parents: dict[int, str] = {}
    current_heading = "document"
    counters: dict[str, dict[str, int]] = {}
    claims: list[tuple[str, str]] = []
    in_fence = False
    excluded_level: int | None = None
    for index, line in enumerate(lines):
        if line.strip().startswith(("```", "~~~")):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        heading = HEADING_RE.match(line)
        if heading is not None:
            level = len(heading.group("marks"))
            heading_id = _heading_identifier(heading.group("title"), level, parents)
            parents = {
                parent_level: value
                for parent_level, value in parents.items()
                if parent_level < level
            }
            parents[level] = heading_id
            current_heading = heading_id
            if heading_id == ledger_section_id:
                excluded_level = level
            elif excluded_level is not None and level <= excluded_level:
                excluded_level = None
            continue
        if excluded_level is not None or not line.strip() or line.strip() == "---":
            continue
        cells = _table_cells(line)
        if cells is not None:
            if _is_table_separator(line):
                continue
            next_line = lines[index + 1] if index + 1 < len(lines) else ""
            if _is_table_separator(next_line):
                continue
            kind = "r"
        else:
            kind = "p"
        heading_counters = counters.setdefault(current_heading, {"p": 0, "r": 0})
        heading_counters[kind] += 1
        claims.append((f"{current_heading}/{kind}{heading_counters[kind]}", line))
    return tuple(claims)


def _normalize_target_path(root: Path, document_path: Path, target: str) -> tuple[str, str | None]:
    path_text, separator, fragment = target.partition("#")
    if path_text.startswith("docs/"):
        resolved = root / path_text
    else:
        resolved = document_path.parent / path_text
    try:
        relative = resolved.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as error:
        raise CoverageError(f"引用先がリポジトリ外を指す: {target}") from error
    return relative, fragment if separator else None


def _reference_kind(path: str) -> str:
    if path.startswith("docs/legacy/"):
        return "legacy"
    if path.startswith("docs/requirements/"):
        return "要件"
    return "正本"


def _stable_id_from_label(label: str, fragment: str | None) -> str | None:
    candidates = []
    if fragment is not None:
        candidates.append(fragment)
    candidates.append(label.replace("**", "").replace("`", "").strip())
    for candidate in candidates:
        if STABLE_ID_RE.fullmatch(candidate) is not None:
            return candidate
    return None


def _stable_row_id(line: str) -> str | None:
    cells = _table_cells(line)
    if cells is None or not cells:
        return None
    candidate = cells[0].replace("**", "").replace("`", "").strip()
    return candidate if STABLE_ID_RE.fullmatch(candidate) is not None else None


def _stable_id_at_line(path: Path, line_number: int, cache: dict[Path, list[str]]) -> str:
    if path not in cache:
        try:
            cache[path] = path.read_text(encoding="utf-8").splitlines()
        except OSError as error:
            raise CoverageError(f"行番号引用の参照先を読めない: {path}: {error}") from error
    lines = cache[path]
    if line_number < 1 or line_number > len(lines):
        raise CoverageError(f"行番号引用が参照先の範囲外: {path}:{line_number}")

    current = "document"
    appendix: str | None = None
    for index, line in enumerate(lines[:line_number], start=1):
        appendix_heading = APPENDIX_RE.match(line)
        if appendix_heading is not None:
            appendix = appendix_heading.group(1)
            current = f"付録{appendix}"
            continue
        requirement = REQUIREMENT_RE.match(line)
        if requirement is not None:
            current = requirement.group(1)
            appendix = None
            continue
        numbered = NUMBERED_SECTION_RE.match(line)
        if numbered is not None:
            current = numbered.group(1)
            appendix = None
            continue
        appendix_item = APPENDIX_HEADING_ITEM_RE.match(line)
        if appendix is not None and appendix_item is not None:
            current = f"付録{appendix}/{appendix_item.group(1)}"
            continue
        ordered_item = ORDERED_ITEM_RE.match(line)
        if appendix in {"B", "D"} and ordered_item is not None:
            current = f"付録{appendix}/{appendix}-{ordered_item.group(1)}"
            continue
        heading = HEADING_RE.match(line)
        if heading is not None:
            stable_heading = re.match(
                r"^(?P<id>[A-Z]+-\d+(?:-[A-Za-z0-9]+)?)(?:[.:\s]|$)",
                heading.group("title"),
            )
            if stable_heading is not None:
                current = stable_heading.group("id")
        if index == line_number:
            row_id = _stable_row_id(line)
            if row_id is not None:
                return row_id
    return current


def _spans_overlap(left: tuple[int, int], right: tuple[int, int]) -> bool:
    return left[0] < right[1] and right[0] < left[1]


def _claim_references(
    claim: str,
    root: Path,
    document_path: Path,
    cache: dict[Path, list[str]],
) -> tuple[tuple[int, str, str], ...]:
    events: list[tuple[int, int, int, str, re.Match[str]]] = []
    patterns = (
        (0, "markdown", MARKDOWN_REFERENCE_RE),
        (1, "requirement-line", REQ_LINE_REFERENCE_RE),
        (2, "path-line", PATH_LINE_REFERENCE_RE),
        (3, "shorthand-line", SHORTHAND_LINE_REFERENCE_RE),
    )
    for priority, event_kind, pattern in patterns:
        events.extend(
            (match.start(), match.end(), priority, event_kind, match)
            for match in pattern.finditer(claim)
        )
    events.sort(key=lambda event: (event[0], event[2], -(event[1] - event[0])))

    occupied: list[tuple[int, int]] = []
    references: list[tuple[int, str, str]] = []
    last_path: str | None = None
    for start, end, _, event_kind, match in events:
        span = (start, end)
        if any(_spans_overlap(span, existing) for existing in occupied):
            continue
        occupied.append(span)
        if event_kind == "markdown":
            target_path, fragment = _normalize_target_path(
                root, document_path, match.group("target")
            )
            last_path = target_path
            stable_id = _stable_id_from_label(match.group("label"), fragment)
            if stable_id is not None:
                references.append((start, target_path, stable_id))
            continue
        if event_kind == "requirement-line":
            target_path = REQUIREMENTS_PATH
            last_path = target_path
        elif event_kind == "path-line":
            target_path, _ = _normalize_target_path(root, document_path, match.group("path"))
            last_path = target_path
        else:
            if last_path is None:
                continue
            target_path = last_path
        stable_id = _stable_id_at_line(root / target_path, int(match.group("line")), cache)
        references.append((start, target_path, stable_id))
    return tuple(sorted(references))


def extract_citations(
    text: str,
    root: Path,
    document_path: Path,
    *,
    ledger_section_id: str = LEDGER_SECTION_ID,
) -> tuple[Citation, ...]:
    """本文から主張 ID と 4 要素キーを持つ引用列を抽出する。

    現行の行番号引用は参照先文書の当該行を包含する安定 ID へ解決する。
    識別子参照は、安定 ID をラベルまたはフラグメントに持つ Markdown リンクを読む。
    意味照合台帳の節自体は自己参照を避けるため抽出しない。

    Args:
        text: 検査対象文書の Markdown 全文。
        root: リポジトリルート。
        document_path: 検査対象文書のパス。
        ledger_section_id: 抽出対象から除外する台帳節ID。

    Returns:
        本文での出現順に並ぶ引用。ordinal は同一主張・同一参照先ごとに振る。
    """
    cache: dict[Path, list[str]] = {}
    citations: list[Citation] = []
    for claim_id, claim in _claim_lines(text, ledger_section_id=ledger_section_id):
        ordinals: Counter[tuple[str, str]] = Counter()
        for _, target_path, stable_id in _claim_references(claim, root, document_path, cache):
            pair = (target_path, stable_id)
            ordinals[pair] += 1
            citations.append(
                Citation(
                    claim_id=claim_id,
                    ordinal=ordinals[pair],
                    target_path=target_path,
                    target_kind=_reference_kind(target_path),
                    stable_id=stable_id,
                )
            )
    return tuple(citations)


def parse_ledger(
    text: str,
    *,
    ledger_section_id: str = LEDGER_SECTION_ID,
    ledger_header: Sequence[str] = LEDGER_HEADER,
    reference_kinds: frozenset[str] = REFERENCE_KINDS,
    ledger_verdicts: frozenset[str] = LEDGER_VERDICTS,
) -> tuple[LedgerEntry, ...]:
    """11-5 の意味照合台帳を読み取る。

    Args:
        text: 同期プロトコル設計の Markdown 全文。
        ledger_section_id: 意味照合台帳の節ID。
        ledger_header: 台帳のヘッダー。
        reference_kinds: 許可する参照先種別。
        ledger_verdicts: 許可する照合判定。

    Returns:
        台帳に記載された順の行。空表は空タプルになる。

    Raises:
        CoverageError: 台帳節、列、列挙値または ordinal が不正な場合。
    """
    section = _section_text(text, re.compile(rf"^{re.escape(ledger_section_id)}\."))
    if not section:
        raise CoverageError(f"本書に {ledger_section_id} 節がない")
    lines = section.splitlines()
    header_index: int | None = None
    for index, line in enumerate(lines):
        cells = _table_cells(line)
        if cells is not None and tuple(cells) == tuple(ledger_header):
            header_index = index
            break
    if header_index is None:
        raise CoverageError("意味照合台帳に所定の 7 列がない")

    entries: list[LedgerEntry] = []
    for line in lines[header_index + 2 :]:
        cells = _table_cells(line)
        if cells is None:
            break
        if len(cells) != len(ledger_header):
            raise CoverageError(
                f"意味照合台帳の列数が {len(ledger_header)} でない: {line}"
            )
        claim_id, ordinal_text, target_path, target_kind, stable_id, verdict, correction = (
            _without_emphasis(cell) for cell in cells
        )
        try:
            ordinal = int(ordinal_text)
        except ValueError as error:
            raise CoverageError(f"台帳の ordinal が整数でない: {ordinal_text}") from error
        if ordinal < 1:
            raise CoverageError(f"台帳の ordinal が 1 未満: {ordinal}")
        if not claim_id or not target_path or not stable_id:
            raise CoverageError(f"意味照合台帳のキーに空セルがある: {line}")
        if target_kind not in reference_kinds:
            raise CoverageError(f"参照先の種別が不正: {target_kind}")
        if verdict not in ledger_verdicts:
            raise CoverageError(f"台帳の判定が不正: {verdict}")
        entries.append(
            LedgerEntry(
                claim_id=claim_id,
                ordinal=ordinal,
                target_path=target_path,
                target_kind=target_kind,
                stable_id=stable_id,
                verdict=verdict,
                correction=correction,
            )
        )
    return tuple(entries)


def check_ledger(
    citations: Sequence[Citation],
    entries: Sequence[LedgerEntry],
) -> tuple[Finding, ...]:
    """本文の引用集合と意味照合台帳を突合する。

    Args:
        citations: 本文から抽出した引用。
        entries: 11-5 の台帳行。

    Returns:
        キー集合、是正内容、参照先の対、ordinal に関する違反列。
    """
    findings: list[Finding] = []
    citation_keys = {citation.key for citation in citations}
    entry_keys = {entry.key for entry in entries}
    missing = sorted(citation_keys - entry_keys)
    unknown = sorted(entry_keys - citation_keys)
    if missing or unknown:
        findings.append(
            Finding(
                "ledger-key-mismatch",
                f"台帳不足={missing}, 本文にない台帳キー={unknown}",
            )
        )

    for entry in entries:
        if entry.verdict != "支持" and entry.correction.strip() in {"", "—"}:
            findings.append(
                Finding(
                    "ledger-correction",
                    f"非支持行の是正内容が空: {entry.key}",
                )
            )

    citation_paths: dict[tuple[str, int, str], set[str]] = {}
    entry_paths: dict[tuple[str, int, str], set[str]] = {}
    for citation in citations:
        signature = (citation.claim_id, citation.ordinal, citation.stable_id)
        citation_paths.setdefault(signature, set()).add(citation.target_path)
    for entry in entries:
        signature = (entry.claim_id, entry.ordinal, entry.stable_id)
        entry_paths.setdefault(signature, set()).add(entry.target_path)
    for signature in sorted(set(citation_paths) & set(entry_paths)):
        if citation_paths[signature] != entry_paths[signature]:
            findings.append(
                Finding(
                    "ledger-target-pair",
                    f"参照先パスと安定 ID の対が不一致: {signature}: "
                    f"本文={sorted(citation_paths[signature])}, "
                    f"台帳={sorted(entry_paths[signature])}",
                )
            )

    citation_by_key = {citation.key: citation for citation in citations}
    for entry in entries:
        citation = citation_by_key.get(entry.key)
        if citation is not None and entry.target_kind != citation.target_kind:
            findings.append(
                Finding(
                    "ledger-target-kind",
                    f"参照先の種別が不一致: {entry.key}: "
                    f"本文={citation.target_kind}, 台帳={entry.target_kind}",
                )
            )

    ordinal_groups: dict[tuple[str, str, str], list[int]] = {}
    for entry in entries:
        group = (entry.claim_id, entry.target_path, entry.stable_id)
        ordinal_groups.setdefault(group, []).append(entry.ordinal)
    for group, ordinals in sorted(ordinal_groups.items()):
        actual = sorted(ordinals)
        expected = list(range(1, len(ordinals) + 1))
        if actual != expected:
            findings.append(
                Finding(
                    "ledger-ordinal",
                    f"ordinal が 1 始まりの連番でない: {group}: {actual}",
                )
            )
    return tuple(findings)


def _direct_universe_ids(value: Any) -> frozenset[str]:
    """直接要件照合用に要件母集合のIDを平坦化する。"""
    if not isinstance(value, dict):
        raise CoverageError("要件母集合がobjectでない")
    if isinstance(value.get("ids"), list):
        values = value["ids"]
    elif isinstance(value.get("categories"), dict):
        values = [
            identifier
            for category in value["categories"].values()
            if isinstance(category, dict)
            for identifier in category.get("ids", [])
        ]
    else:
        raise CoverageError("要件母集合に ids/categories がない")
    if not all(isinstance(identifier, str) and identifier for identifier in values):
        raise CoverageError("要件母集合のIDが不正")
    return frozenset(values)


def check_attribution_direct(
    profile: Any,
    assignments: Sequence[Assignment],
) -> tuple[Finding, ...]:
    """直接要件集合とclaims分類および帰属表を照合する。"""
    assets = doc_check_profile.load_assets(profile)
    direct_asset = assets.assets.get("direct_requirements")
    if direct_asset is None or profile.direct_requirements is None:
        raise doc_check_profile.ProfileError(
            "required_checks=attribution-direct に direct_requirements が必要です"
        )
    if direct_asset.path != profile.direct_requirements:
        raise doc_check_profile.ProfileError(
            "profile.direct_requirements と assets.direct_requirements.path が不一致です"
        )
    direct_ids = {
        identifier.id
        for collection in direct_asset.collections
        for record in collection.records
        for identifier in record.identifiers
    }
    if not direct_ids:
        raise doc_check_profile.ProfileError("direct_requirements 資産が空です")
    universe = _direct_universe_ids(doc_check_profile.load_json(profile.universe))
    outside = direct_ids - universe
    if outside:
        raise doc_check_profile.ProfileError(
            f"direct_requirements に母集合外IDがあります: {sorted(outside)}"
        )

    collection_results = doc_check_profile.evaluate_collection_sets(
        profile,
        assets,
        manifest={"relations": []},
    )
    direct_results = tuple(
        result
        for result in collection_results
        if result.id == "direct-requirements-vs-claims"
    )
    if len(direct_results) != 1:
        raise doc_check_profile.ProfileError(
            "attribution-direct に collection_sets "
            "direct-requirements-vs-claims 1件が必要です"
        )
    findings: list[Finding] = []
    if direct_results[0].reason is not None:
        findings.append(
            Finding(ATTRIBUTION_DIRECT_CHECK_ID, direct_results[0].reason)
        )
    excluded = sorted(
        assignment.id
        for assignment in assignments
        if assignment.kind == "対象外" and assignment.id in direct_ids
    )
    if excluded:
        findings.append(
            Finding(
                ATTRIBUTION_DIRECT_CHECK_ID,
                f"直接要件が対象外に分類されている: {excluded}",
            )
        )
    return tuple(findings)


def select_coverage_checks(
    check_csv: str | None,
    *,
    required_checks: frozenset[str] | None = None,
) -> tuple[str, ...]:
    """実行対象の帰属検査・台帳検査を選ぶ。

    Args:
        check_csv: ``--checks`` のカンマ区切り値。省略時は両検査を選ぶ。
        required_checks: プロファイルの必須検査。省略時は従来2検査。

    Returns:
        宣言順に並べた検査 ID。

    Raises:
        CoverageError: 空要素または未知の検査 ID がある場合。
    """
    if check_csv is None:
        if required_checks is None:
            return COVERAGE_CHECK_IDS
        return tuple(
            check_id
            for check_id in COVERAGE_SELECTABLE_CHECK_IDS
            if check_id in required_checks
        )
    requested = check_csv.split(",")
    if not requested or any(not item for item in requested):
        raise CoverageError("--checks に空の検査 ID がある")
    unknown = sorted(set(requested) - COVERAGE_SELECTABLE_CHECK_ID_SET)
    if unknown:
        raise CoverageError(f"未知の検査 ID: {unknown}")
    return tuple(
        check_id for check_id in COVERAGE_SELECTABLE_CHECK_IDS if check_id in requested
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """コマンドライン引数を解釈する。

    Args:
        argv: テスト時に指定する引数列。省略時はコマンドライン引数を使う。

    Returns:
        解釈済み引数。
    """
    parser = argparse.ArgumentParser(description="要件帰属と意味照合台帳を検査する")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="リポジトリルート(既定: カレントディレクトリ)",
    )
    parser.add_argument(
        "--requirements",
        type=Path,
        help="検査対象の要件書(未指定時はプロファイルのrequirements)",
    )
    parser.add_argument(
        "--document",
        type=Path,
        help="帰属表を持つ設計書(未指定時はプロファイルのdocument)",
    )
    parser.add_argument(
        "--universe",
        type=Path,
        help="要件母集合のJSON(未指定時はプロファイルのuniverse)",
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
        "--checks",
        help=(
            "実行する検査IDのカンマ区切り"
            "(attribution,ledger,attribution-destination,attribution-direct)"
        ),
    )
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
    """要件帰属・意味照合台帳検査を実行し、結果に応じた終了コードを返す。

    Args:
        argv: テスト時に指定する引数列。省略時はコマンドライン引数を使う。

    Returns:
        違反なしなら 0、検査違反なら 1、入力不正なら 2。
    """
    try:
        args = parse_args(argv)
        root = args.root.resolve()
        enumerate_registry = (
            args.profile is None
            and args.requirements is None
            and args.document is None
            and args.universe is None
            and args.checks is None
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

        checks = select_coverage_checks(
            args.checks,
            required_checks=profile.required_checks,
        )
        document_path = (
            _resolve(root, args.document)
            if args.document is not None
            else profile.document
        )
        requirements_path = (
            _resolve(root, args.requirements)
            if args.requirements is not None
            else profile.requirements
        )
        universe_path = (
            _resolve(root, args.universe)
            if args.universe is not None
            else profile.universe
        )
        document = _read_text(document_path, "設計書")
        attribution = profile.raw["attribution"]
        assignment_options = {
            "section_re": attribution["section_re"],
            "assignment_kinds": frozenset(attribution["kinds"]),
            "assignment_header": tuple(attribution["assignment_header"]),
            "destination_grammar": attribution["destination_grammar"],
        }
        findings: list[Finding] = []
        if "attribution" in checks:
            requirements = _read_text(requirements_path, "要件書")
            universe = load_universe(universe_path)
            extracted = extract_requirement_ids(requirements)
            assignments = parse_assignments(document, **assignment_options)
            findings.extend(check_coverage(extracted, universe, assignments))
        if "ledger" in checks:
            citations = extract_citations(
                document,
                root,
                document_path,
                ledger_section_id=attribution["ledger_section"],
            )
            entries = parse_ledger(
                document,
                ledger_section_id=attribution["ledger_section"],
                ledger_header=tuple(attribution["ledger_header"]),
                reference_kinds=frozenset(attribution["reference_kinds"]),
                ledger_verdicts=frozenset(attribution["ledger_verdicts"]),
            )
            findings.extend(check_ledger(citations, entries))
        if ATTRIBUTION_DESTINATION_CHECK_ID in checks:
            reason = profile.not_applicable.get(ATTRIBUTION_DESTINATION_CHECK_ID)
            if reason is not None:
                print(
                    f"{ATTRIBUTION_DESTINATION_CHECK_ID}: 対象なし: {reason}"
                )
            else:
                assignments = parse_assignments(document, **assignment_options)
                findings.extend(
                    check_attribution_destinations(
                        document,
                        assignments,
                        destination_grammar=attribution["destination_grammar"],
                    )
                )
        if ATTRIBUTION_DIRECT_CHECK_ID in checks:
            reason = profile.not_applicable.get(ATTRIBUTION_DIRECT_CHECK_ID)
            if reason is not None:
                print(f"{ATTRIBUTION_DIRECT_CHECK_ID}: 対象なし: {reason}")
            else:
                assignments = parse_assignments(document, **assignment_options)
                findings.extend(check_attribution_direct(profile, assignments))
    except (CoverageError, doc_check_profile.ProfileError) as error:
        print(f"check_doc_coverage.py: {error}", file=sys.stderr)
        return 2
    for finding in findings:
        print(f"{finding.check}: {finding.reason}", file=sys.stderr)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
