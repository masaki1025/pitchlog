"""要件書の安定 ID 抽出結果と同期設計の帰属表を全数検査する。"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

DEFAULT_REQUIREMENTS = Path("docs/requirements/requirements-pitchlog-2026-07-22.md")
DEFAULT_DOCUMENT = Path("docs/design/sync-protocol.md")
DEFAULT_UNIVERSE = Path("scripts/design_relations/req-universe.json")

COVERAGE_CHECK_IDS = ("attribution", "ledger")
COVERAGE_CHECK_ID_SET = frozenset(COVERAGE_CHECK_IDS)
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
    """

    id: str
    kind: str
    destination: str


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


def parse_assignments(text: str) -> tuple[Assignment, ...]:
    """同期設計 11-3 の帰属表を読み取る。

    Args:
        text: 同期プロトコル設計の Markdown 全文。

    Returns:
        表に記載された順の帰属行。

    Raises:
        CoverageError: 11-3 または所定ヘッダーの帰属表がない場合。
    """
    section = _section_text(text, re.compile(r"^11-3\."))
    if not section:
        raise CoverageError("本書に 11-3 節がない")
    lines = section.splitlines()
    header_index: int | None = None
    for index, line in enumerate(lines):
        cells = _table_cells(line)
        if cells is not None and tuple(cells) == ASSIGNMENT_HEADER:
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
        if kind not in ASSIGNMENT_KINDS:
            raise CoverageError(f"帰属表の区分が不正: {identifier}: {kind}")
        assignments.append(Assignment(identifier, kind, destination))
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


def _heading_identifier(
    title: str,
    level: int,
    parents: dict[int, str],
) -> str:
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


def _claim_lines(text: str) -> tuple[tuple[str, str], ...]:
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
            if heading_id == LEDGER_SECTION_ID:
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


def extract_citations(text: str, root: Path, document_path: Path) -> tuple[Citation, ...]:
    """本文から主張 ID と 4 要素キーを持つ引用列を抽出する。

    現行の行番号引用は参照先文書の当該行を包含する安定 ID へ解決する。
    識別子参照は、安定 ID をラベルまたはフラグメントに持つ Markdown リンクを読む。
    意味照合台帳の節自体は自己参照を避けるため抽出しない。

    Args:
        text: 検査対象文書の Markdown 全文。
        root: リポジトリルート。
        document_path: 検査対象文書のパス。

    Returns:
        本文での出現順に並ぶ引用。ordinal は同一主張・同一参照先ごとに振る。
    """
    cache: dict[Path, list[str]] = {}
    citations: list[Citation] = []
    for claim_id, claim in _claim_lines(text):
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


def parse_ledger(text: str) -> tuple[LedgerEntry, ...]:
    """11-5 の意味照合台帳を読み取る。

    Args:
        text: 同期プロトコル設計の Markdown 全文。

    Returns:
        台帳に記載された順の行。空表は空タプルになる。

    Raises:
        CoverageError: 台帳節、列、列挙値または ordinal が不正な場合。
    """
    section = _section_text(text, re.compile(rf"^{LEDGER_SECTION_ID}\."))
    if not section:
        raise CoverageError(f"本書に {LEDGER_SECTION_ID} 節がない")
    lines = section.splitlines()
    header_index: int | None = None
    for index, line in enumerate(lines):
        cells = _table_cells(line)
        if cells is not None and tuple(cells) == LEDGER_HEADER:
            header_index = index
            break
    if header_index is None:
        raise CoverageError("意味照合台帳に所定の 7 列がない")

    entries: list[LedgerEntry] = []
    for line in lines[header_index + 2 :]:
        cells = _table_cells(line)
        if cells is None:
            break
        if len(cells) != len(LEDGER_HEADER):
            raise CoverageError(f"意味照合台帳の列数が 7 でない: {line}")
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
        if target_kind not in REFERENCE_KINDS:
            raise CoverageError(f"参照先の種別が不正: {target_kind}")
        if verdict not in LEDGER_VERDICTS:
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


def select_coverage_checks(check_csv: str | None) -> tuple[str, ...]:
    """実行対象の帰属検査・台帳検査を選ぶ。

    Args:
        check_csv: ``--checks`` のカンマ区切り値。省略時は両検査を選ぶ。

    Returns:
        宣言順に並べた検査 ID。

    Raises:
        CoverageError: 空要素または未知の検査 ID がある場合。
    """
    if check_csv is None:
        return COVERAGE_CHECK_IDS
    requested = check_csv.split(",")
    if not requested or any(not item for item in requested):
        raise CoverageError("--checks に空の検査 ID がある")
    unknown = sorted(set(requested) - COVERAGE_CHECK_ID_SET)
    if unknown:
        raise CoverageError(f"未知の検査 ID: {unknown}")
    return tuple(check_id for check_id in COVERAGE_CHECK_IDS if check_id in requested)


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
        "--requirements", type=Path, default=DEFAULT_REQUIREMENTS, help="検査対象の要件書"
    )
    parser.add_argument(
        "--document", type=Path, default=DEFAULT_DOCUMENT, help="帰属表を持つ設計書"
    )
    parser.add_argument(
        "--universe", type=Path, default=DEFAULT_UNIVERSE, help="要件母集合の JSON"
    )
    parser.add_argument(
        "--checks",
        help="実行する検査 ID のカンマ区切り(attribution,ledger。既定: 両方)",
    )
    return parser.parse_args(argv)


def _resolve(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


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
        checks = select_coverage_checks(args.checks)
        document_path = _resolve(root, args.document)
        document = _read_text(document_path, "設計書")
        findings: list[Finding] = []
        if "attribution" in checks:
            requirements = _read_text(_resolve(root, args.requirements), "要件書")
            universe = load_universe(_resolve(root, args.universe))
            extracted = extract_requirement_ids(requirements)
            assignments = parse_assignments(document)
            findings.extend(check_coverage(extracted, universe, assignments))
        if "ledger" in checks:
            citations = extract_citations(document, root, document_path)
            entries = parse_ledger(document)
            findings.extend(check_ledger(citations, entries))
    except CoverageError as error:
        print(f"check_doc_coverage.py: {error}", file=sys.stderr)
        return 2
    for finding in findings:
        print(f"{finding.check}: {finding.reason}", file=sys.stderr)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
