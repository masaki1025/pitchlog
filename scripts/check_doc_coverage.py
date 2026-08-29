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

HEADING_RE = re.compile(r"^(?P<marks>#{2,6})\s+(?P<title>.+)$")
REQUIREMENT_RE = re.compile(r"^####\s+((?:FR|NFR)-\d{3}):")
NUMBERED_SECTION_RE = re.compile(
    r"^#{2,4}\s+(\d+(?:\.\d+)*(?:-\d+)?)(?:\.|\s|$)"
)
BLOCK_RE = re.compile(r"^###\s+ブロック(\d+):")
APPENDIX_RE = re.compile(r"^##\s+付録([A-F]):")
APPENDIX_HEADING_ITEM_RE = re.compile(r"^###\s+([AEF]-\d+[a-z]?)\b")
ORDERED_ITEM_RE = re.compile(r"^(\d+)\.\s+")
IDENTIFIED_ROW_RE = re.compile(r"^\|\s*((?:G|R)-\d+)\s*\|")


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


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """コマンドライン引数を解釈する。

    Args:
        argv: テスト時に指定する引数列。省略時はコマンドライン引数を使う。

    Returns:
        解釈済み引数。
    """
    parser = argparse.ArgumentParser(description="要件の安定 ID 抽出結果と帰属表を全数検査する")
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
    return parser.parse_args(argv)


def _resolve(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


def main(argv: Sequence[str] | None = None) -> int:
    """帰属検査を実行し、結果に応じた終了コードを返す。

    Args:
        argv: テスト時に指定する引数列。省略時はコマンドライン引数を使う。

    Returns:
        違反なしなら 0、検査違反なら 1、入力不正なら 2。
    """
    try:
        args = parse_args(argv)
        root = args.root.resolve()
        requirements = _read_text(_resolve(root, args.requirements), "要件書")
        document = _read_text(_resolve(root, args.document), "設計書")
        universe = load_universe(_resolve(root, args.universe))
        extracted = extract_requirement_ids(requirements)
        assignments = parse_assignments(document)
        findings = check_coverage(extracted, universe, assignments)
    except CoverageError as error:
        print(f"check_doc_coverage.py: {error}", file=sys.stderr)
        return 2
    for finding in findings:
        print(f"{finding.check}: {finding.reason}", file=sys.stderr)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
