"""ORM スキーマ移行の受入証跡突合シートを機械生成する。"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence, cast

DATA_MODEL_RELATIVE_PATH = Path("docs/design/data-model.md")
MANIFEST_RELATIVE_PATH = Path("contracts/db/schema-manifest.json")
OUTPUT_RELATIVE_PATH = Path(
    "docs/features/orm-schema-migration/acceptance-sheets"
)
SCHEMA_AUDIT_REFERENCE = (
    "backend/tests/db/test_schema_audit.py::"
    "test_schema_manifest_matches_catalog_and_cross_table_rules"
)

SHEET_FILENAMES = (
    "N1-table-completeness.md",
    "N3-immutability-completeness.md",
    "N4-deletion-lifecycle.md",
    "N7-required-attributes.md",
)
SHEET_HEADERS = ("対象", "正本側", "実装側", "判定", "理由と典拠")

N3_TERMS = (
    "不変",
    "変えない",
    "昇格させない",
    "後退させない",
    "追記のみ",
    "変更不可",
    "更新しない",
    "上書きしない",
    "書き換えない",
)
N7_PROSE_TERMS = ("必須", "無条件", "保持する")

_HEADING_RE = re.compile(r"^(?P<marks>#{2,6})\s+(?P<title>.+?)\s*$")
_NUMBERED_SECTION_RE = re.compile(
    r"^(?P<section>\d+(?:-\d+(?:-[A-Z])?)?)\.\s*"
)
_SEPARATOR_CELL_RE = re.compile(r"^:?-{3,}:?$")
_MODEL_TABLE_RE = re.compile(r'^\s*__tablename__\s*=\s*["\'](?P<table>[^"\']+)["\']')
_REFERENCE_RE = re.compile(
    r"(?:docs/[^ :|]+\.md|[^ :|]+\.md):§?\d+(?:-\d+(?:-[A-Z])?)?"
)
_QUOTED_FRAGMENT_RE = re.compile(
    r'''(?P<quote>["'])(?P<value>.*?)(?P=quote)'''
)
_CONTRACT_IDENTIFIER_RE = re.compile(
    r"[A-Za-z_][A-Za-z0-9_]*|[\u3040-\u30ff\u3400-\u9fff]+"
)
_DECLARED_IDENTIFIER_RE = re.compile(
    r"^[+-]\s*(?P<identifier>[A-Za-z_][A-Za-z0-9_]*)\s*:"
)
_DIFF_STRUCTURE_WORDS = frozenset(
    {
        "allowed_update_columns",
        "AND",
        "append_mode",
        "BETWEEN",
        "checks",
        "columns",
        "composite",
        "cross_tenant",
        "default",
        "deletion",
        "False",
        "foreign_keys",
        "immutability",
        "info",
        "IN",
        "IS",
        "lifecycle",
        "Mapped",
        "mapped_column",
        "match",
        "migration_retirement",
        "name",
        "NO",
        "NOT",
        "NULL",
        "None",
        "nullable",
        "on_delete",
        "ondelete",
        "OR",
        "protected_columns",
        "references",
        "table",
        "True",
        "type",
    }
)

ManifestTable = dict[str, Any]


@dataclass(frozen=True)
class SheetRow:
    """突合シートの人間判定対象となる 1 行を表す。

    Attributes:
        target: 突き合わせる対象。
        canonical: 正本側の節と抽出内容。
        implementation: manifest・models・実カタログ側の候補。
        judgment: 人間が記入する判定。
        rationale: 人間が記入する理由と典拠。
    """

    target: str
    canonical: str
    implementation: str
    judgment: str = ""
    rationale: str = ""


@dataclass(frozen=True)
class Heading:
    """正本から抽出した見出しを表す。"""

    position: int
    level: int
    section: str
    title: str


@dataclass(frozen=True)
class MarkdownTableRow:
    """正本の Markdown 表から抽出した行を表す。"""

    position: int
    cells: tuple[str, ...]


@dataclass(frozen=True)
class MarkdownTable:
    """正本の Markdown 表を節とともに表す。"""

    position: int
    section: str
    headers: tuple[str, ...]
    rows: tuple[MarkdownTableRow, ...]


@dataclass(frozen=True)
class N7Group:
    """N7 の同じ正本節に属する列契約と判定行を表す。"""

    section: str
    tables: tuple[ManifestTable, ...]
    rows: tuple[SheetRow, ...]


@dataclass(frozen=True)
class CarryForwardStats:
    """判定持ち越しと空欄化の件数を表す。"""

    carried: int = 0
    key_changed: int = 0
    difference: int = 0
    changed_identifier: int = 0
    reset_count: int = 0

    @property
    def reset(self) -> int:
        """空欄へ戻した行数を返す。"""
        return self.reset_count


def _plain_markdown(value: str) -> str:
    value = re.sub(r"\[([^]]+)]\([^)]+\)", r"\1", value)
    value = value.replace("**", "").replace("`", "")
    return " ".join(value.split())


def _excerpt(value: str, limit: int = 240) -> str:
    plain = _plain_markdown(value)
    if len(plain) <= limit:
        return plain
    return f"{plain[: limit - 1]}…"


def _split_markdown_row(line: str) -> tuple[str, ...]:
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for character in line.strip():
        if escaped:
            current.append(character)
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == "|":
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(character)
    cells.append("".join(current).strip())
    if cells and cells[0] == "":
        cells.pop(0)
    if cells and cells[-1] == "":
        cells.pop()
    return tuple(cells)


def _is_separator_row(cells: Sequence[str]) -> bool:
    return bool(cells) and all(_SEPARATOR_CELL_RE.fullmatch(cell) for cell in cells)


def _section_labels(lines: Sequence[str]) -> tuple[str, ...]:
    labels: list[str] = []
    current = "文書冒頭"
    for line in lines:
        match = _HEADING_RE.match(line)
        if match:
            title = _plain_markdown(match.group("title"))
            section_match = _NUMBERED_SECTION_RE.match(title)
            if section_match:
                current = section_match.group("section")
            elif len(match.group("marks")) == 2:
                current = title
        labels.append(current)
    return tuple(labels)


def _chapter(section: str) -> int | None:
    match = re.match(r"^(\d+)", section)
    return int(match.group(1)) if match else None


def _headings_in_schema_chapters(lines: Sequence[str]) -> tuple[Heading, ...]:
    labels = _section_labels(lines)
    headings: list[Heading] = []
    active_chapter: int | None = None
    for position, line in enumerate(lines):
        match = _HEADING_RE.match(line)
        if not match:
            continue
        title = _plain_markdown(match.group("title"))
        level = len(match.group("marks"))
        if level == 2:
            active_chapter = _chapter(labels[position])
        if active_chapter is not None and 5 <= active_chapter <= 12:
            headings.append(
                Heading(position, level, labels[position], title)
            )
    return tuple(headings)


def _markdown_tables(lines: Sequence[str]) -> tuple[MarkdownTable, ...]:
    labels = _section_labels(lines)
    tables: list[MarkdownTable] = []
    position = 0
    while position + 1 < len(lines):
        if not lines[position].lstrip().startswith("|"):
            position += 1
            continue
        headers = _split_markdown_row(lines[position])
        separators = _split_markdown_row(lines[position + 1])
        if len(headers) != len(separators) or not _is_separator_row(separators):
            position += 1
            continue
        row_position = position + 2
        rows: list[MarkdownTableRow] = []
        while row_position < len(lines) and lines[row_position].lstrip().startswith(
            "|"
        ):
            cells = _split_markdown_row(lines[row_position])
            if len(cells) == len(headers):
                rows.append(MarkdownTableRow(row_position, cells))
            row_position += 1
        tables.append(
            MarkdownTable(
                position,
                labels[position],
                tuple(_plain_markdown(header) for header in headers),
                tuple(rows),
            )
        )
        position = row_position
    return tuple(tables)


def _load_manifest_tables(repo_root: Path) -> tuple[ManifestTable, ...]:
    payload = cast(
        dict[str, Any],
        json.loads(
            (repo_root / MANIFEST_RELATIVE_PATH).read_text(encoding="utf-8")
        ),
    )
    return tuple(cast(list[ManifestTable], payload["tables"]))


def _source_sections(table: ManifestTable) -> tuple[str, ...]:
    return tuple(cast(list[str], table["source_sections"]))


def _tables_for_section(
    tables: Sequence[ManifestTable], section: str
) -> tuple[ManifestTable, ...]:
    if not section[0:1].isdigit():
        return ()
    if "-" not in section:
        prefix = f"{section}-"
        return tuple(
            table
            for table in tables
            if any(
                source == section or source.startswith(prefix)
                for source in _source_sections(table)
            )
        )
    return tuple(
        table for table in tables if section in _source_sections(table)
    )


def _model_sources(repo_root: Path) -> dict[str, str]:
    source_root = repo_root / "backend" / "src" / "pitchlog" / "db"
    sources: dict[str, str] = {}
    for path in sorted(source_root.rglob("models.py")):
        relative_path = path.relative_to(repo_root).as_posix()
        for line in path.read_text(encoding="utf-8").splitlines():
            match = _MODEL_TABLE_RE.match(line)
            if match:
                sources[match.group("table")] = relative_path
    return sources


def _column_contract(column: Mapping[str, Any]) -> str:
    nullability = "NULL" if cast(bool, column["nullable"]) else "NOT NULL"
    default_value = column.get("default")
    default = "なし" if default_value is None else str(default_value)
    return f"{column['name']}:{column['type']}/{nullability}/default={default}"


def _implementation_references(
    tables: Sequence[ManifestTable],
    model_sources: Mapping[str, str],
    section: str,
) -> str:
    candidates = _tables_for_section(tables, section)
    if not candidates:
        return (
            "manifest=該当候補なし; models=該当候補なし; "
            "実カタログ=該当候補なし（人間が対象外適格性を判定）"
        )
    rendered: list[str] = []
    for table in candidates:
        table_name = cast(str, table["name"])
        model_source = model_sources.get(table_name, "models.py 未検出")
        rendered.append(
            f"manifest={table_name}(列契約ブロック); "
            f"models={model_source}::{table_name}; "
            f"実カタログ={SCHEMA_AUDIT_REFERENCE} が manifest 全列と照合済み"
            f"(public.{table_name})"
        )
    return " / ".join(rendered)


def _n1_rows(
    lines: Sequence[str], tables: Sequence[ManifestTable]
) -> tuple[SheetRow, ...]:
    rows: list[SheetRow] = []
    for ordinal, heading in enumerate(_headings_in_schema_chapters(lines), start=1):
        candidates = _tables_for_section(tables, heading.section)
        implementation = (
            "manifest tables: "
            + ", ".join(cast(str, table["name"]) for table in candidates)
            if candidates
            else "manifest tables: 該当候補なし"
        )
        rows.append(
            SheetRow(
                target=f"見出し {ordinal:03d}: {heading.title}",
                canonical=f"data-model.md §{heading.section}",
                implementation=implementation,
            )
        )
    return tuple(rows)


def _n3_rows(
    lines: Sequence[str],
    markdown_tables: Sequence[MarkdownTable],
    tables: Sequence[ManifestTable],
) -> tuple[SheetRow, ...]:
    labels = _section_labels(lines)
    table_rows = {
        row.position: (table, row)
        for table in markdown_tables
        for row in table.rows
    }
    rows: list[SheetRow] = []
    ordinal = 0
    for position, line in enumerate(lines):
        for term in N3_TERMS:
            for _ in re.finditer(re.escape(term), line):
                ordinal += 1
                candidates = _tables_for_section(tables, labels[position])
                if candidates:
                    matrices = " / ".join(
                        f"{table['name']}: "
                        f"protected={table['immutability']['protected_columns']}; "
                        f"allowed={table['immutability']['allowed_update_columns']}"
                        for table in candidates
                    )
                else:
                    matrices = "manifest immutability: 該当候補なし"
                table_context = table_rows.get(position)
                if (
                    table_context is not None
                    and table_context[0].section == "変更履歴"
                ):
                    version = _plain_markdown(table_context[1].cells[0])
                    canonical = (
                        f"data-model.md §変更履歴 — 版 {version} の行（語: {term}）"
                    )
                else:
                    canonical = (
                        f"data-model.md §{labels[position]} — {_excerpt(line)}"
                    )
                rows.append(
                    SheetRow(
                        target=f"出現 {ordinal:03d}: {term}",
                        canonical=canonical,
                        implementation=matrices,
                    )
                )
    return tuple(rows)


def _n4_direct_rows(
    markdown_tables: Sequence[MarkdownTable],
    tables: Sequence[ManifestTable],
) -> tuple[SheetRow, ...]:
    lifecycle_table = next(
        table
        for table in markdown_tables
        if table.section == "11-1"
        and table.headers[:2] == ("系統", "対象")
    )
    rows: list[SheetRow] = []
    ordinal = 0
    for source_row in lifecycle_table.rows:
        lifecycle = _plain_markdown(source_row.cells[0])
        lifecycle_value = lifecycle.split("(", maxsplit=1)[0]
        targets = re.split(r"\s*/\s*", source_row.cells[1])
        candidates = [
            cast(str, table["name"])
            for table in tables
            if cast(dict[str, str], table["lifecycle"])["deletion"]
            == lifecycle_value
        ]
        for target in targets:
            ordinal += 1
            rows.append(
                SheetRow(
                    target=f"11-1 対象 {ordinal:02d}: {_plain_markdown(target)}",
                    canonical=f"data-model.md §11-1 — 軸1={lifecycle_value}",
                    implementation=(
                        f"manifest lifecycle.deletion={lifecycle_value} の候補: "
                        + (", ".join(candidates) if candidates else "なし")
                    ),
                )
            )
    return tuple(rows)


def _section_sort_key(section: str) -> tuple[int, ...]:
    values: list[int] = []
    for part in section.split("-"):
        if part.isdigit():
            values.append(int(part))
        else:
            values.extend(ord(character) for character in part)
    return tuple(values)


def _n4_manifest_candidate_rows(
    tables: Sequence[ManifestTable],
) -> tuple[SheetRow, ...]:
    candidates = list(tables)
    candidates.sort(
        key=lambda table: (
            _section_sort_key(_source_sections(table)[0]),
            cast(str, table["name"]),
        )
    )
    rows: list[SheetRow] = []
    for table in candidates:
        table_name = cast(str, table["name"])
        lifecycle = cast(dict[str, str], table["lifecycle"])
        sections = ", ".join(_source_sections(table))
        rows.append(
            SheetRow(
                target=f"正本に直接割当なし候補: {table_name}",
                canonical=(
                    "data-model.md §11-1 の直接割当有無を人間確認; "
                    f"個別典拠候補 §{sections}"
                ),
                implementation=(
                    f"manifest {table_name}.lifecycle.deletion="
                    f"{lifecycle['deletion']}"
                ),
            )
        )
    return tuple(rows)


def _n7_candidates(
    lines: Sequence[str], markdown_tables: Sequence[MarkdownTable]
) -> tuple[tuple[int, str, str, str], ...]:
    candidates: list[tuple[int, str, str, str]] = []
    attribute_positions: set[int] = set()
    for table in markdown_tables:
        chapter = _chapter(table.section)
        if chapter is None or not 5 <= chapter <= 12:
            continue
        if not table.headers or table.headers[0] != "属性":
            continue
        for row in table.rows:
            attribute_positions.add(row.position)
            attribute = _plain_markdown(row.cells[0])
            details = "; ".join(_plain_markdown(cell) for cell in row.cells[1:])
            candidates.append(
                (
                    row.position,
                    table.section,
                    f"属性表: {attribute}",
                    f"{attribute}: {details}",
                )
            )

    labels = _section_labels(lines)
    for position, line in enumerate(lines):
        chapter = _chapter(labels[position])
        if (
            chapter is None
            or not 5 <= chapter <= 12
            or position in attribute_positions
            or line.lstrip().startswith("|")
        ):
            continue
        matched_terms = [term for term in N7_PROSE_TERMS if term in line]
        if matched_terms:
            candidates.append(
                (
                    position,
                    labels[position],
                    f"記述語: {', '.join(matched_terms)}",
                    _excerpt(line),
                )
            )
    candidates.sort(key=lambda candidate: candidate[0])
    return tuple(candidates)


def _n7_rows(
    lines: Sequence[str],
    markdown_tables: Sequence[MarkdownTable],
    tables: Sequence[ManifestTable],
    model_sources: Mapping[str, str],
) -> tuple[N7Group, ...]:
    grouped_rows: dict[str, list[SheetRow]] = {}
    for ordinal, (_, section, kind, excerpt) in enumerate(
        _n7_candidates(lines, markdown_tables), start=1
    ):
        grouped_rows.setdefault(section, []).append(
            SheetRow(
                target=f"候補 {ordinal:03d}: {kind}",
                canonical=f"data-model.md §{section} — {excerpt}",
                implementation=_implementation_references(
                    tables, model_sources, section
                ),
            )
        )
    return tuple(
        N7Group(
            section=section,
            tables=_tables_for_section(tables, section),
            rows=tuple(rows),
        )
        for section, rows in grouped_rows.items()
    )


def _escape_cell(value: str) -> str:
    return " ".join(value.split()).replace("|", "\\|")


def _common_preamble(
    identifier: str, title: str, target: str, scope: str, method: str
) -> list[str]:
    return [
        f"# {identifier} — {title}",
        "",
        (
            "<!-- scripts/generate_orm_acceptance_sheets.py により生成。"
            "判定欄と理由欄だけを人間が記入する。 -->"
        ),
        "",
        "## 対象・範囲・方法",
        "",
        f"- 対象: {target}",
        f"- 範囲: {scope}",
        f"- 方法: {method}",
        "",
        "## 判定区分と適格条件",
        "",
        "| 区分 | 適格条件 |",
        "| --- | --- |",
        (
            "| `一致` | 正本側と対応する manifest / 実装側を両方特定できる。"
            "片方しか特定できない行は一致にできない。 |"
        ),
        "| `差分` | 欠落・余剰・内容不一致のいずれか。未解消のまま完了にできない。 |",
        (
            "| `対象外` | 当該 N の対象・範囲外にある生成候補だけ。"
            "対象内の欠落には使えず、理由と典拠（ファイル:節）が必須。 |"
        ),
        "",
        "完了条件は、未判定 0・未解消の `差分` 0・不適格な `対象外` 0。",
        "",
        "## 差分時の是正遷移",
        "",
        (
            "`差分` が出たら番号付きの是正ステップを追加する。是正ステップは "
            "`core-areas.json` 登録ステップ（現ステップ 29）より前へ挿入し、"
            "登録ステップを後ろへ繰り下げる。是正後にシートを再生成し、"
            "全行を再度判定する。"
        ),
        "",
    ]


def _render_row_table(rows: Sequence[SheetRow]) -> list[str]:
    rendered = [
        "| 対象 | 正本側 | 実装側 | 判定 | 理由と典拠 |",
        "| --- | --- | --- | --- | --- |",
    ]
    rendered.extend(
        "| "
        + " | ".join(
            _escape_cell(value)
            for value in (
                row.target,
                row.canonical,
                row.implementation,
                row.judgment,
                row.rationale,
            )
        )
        + " |"
        for row in rows
    )
    return rendered


def _render_sheet(
    identifier: str,
    title: str,
    target: str,
    scope: str,
    method: str,
    groups: Sequence[tuple[str, Sequence[SheetRow]]],
) -> str:
    lines = _common_preamble(identifier, title, target, scope, method)
    for heading, rows in groups:
        lines.extend((f"## {heading}", ""))
        lines.extend(_render_row_table(rows))
        lines.append("")
    return "\n".join(lines)


def _render_n7_sheet(groups: Sequence[N7Group]) -> str:
    """N7 を節別の列契約ブロックと短い参照行に分けて描画する。"""
    lines = _common_preamble(
        "N7",
        "必須属性の全数性",
        "data-model.md 5〜12 章の属性表と、必須・無条件・保持するを含む散文",
        "属性・型・NULL 性・既定値。列の意味対応は機械決定せず、人間が4者を判定する。",
        (
            "属性表の全行と指定語を含む散文を文書順に抽出する。節ごとに manifest の"
            "列契約を一度だけ掲示し、判定行はそのブロックを参照する。models と manifest、"
            "実カタログと manifest の照合済み経路も併記する。"
        ),
    )
    lines.extend(("## 4 者突合行（正本の文書順）", ""))
    for group in groups:
        table_names = ", ".join(cast(str, table["name"]) for table in group.tables)
        heading_suffix = f" {table_names}" if table_names else " 該当候補なし"
        lines.extend((f"### §{group.section}{heading_suffix}", ""))
        if group.tables:
            for table in group.tables:
                table_name = cast(str, table["name"])
                columns = cast(list[dict[str, Any]], table["columns"])
                contracts = ", ".join(
                    _column_contract(column) for column in columns
                )
                lines.extend(
                    (
                        f"**列契約（manifest: `{table_name}`）**: {contracts}",
                        "",
                    )
                )
        else:
            lines.extend(("**列契約（manifest）**: 該当候補なし", ""))
        lines.extend(_render_row_table(group.rows))
        lines.append("")
    return "\n".join(lines)


def _render_readme(row_counts: Mapping[str, int]) -> str:
    n1_count = row_counts["N1-table-completeness.md"]
    n3_count = row_counts["N3-immutability-completeness.md"]
    n4_count = row_counts["N4-deletion-lifecycle.md"]
    n7_count = row_counts["N7-required-attributes.md"]
    return "\n".join(
        [
            "# ORM スキーマ移行の受入証跡突合シート",
            "",
            (
                "このディレクトリの N1・N3・N4・N7 は "
                "`scripts/generate_orm_acceptance_sheets.py` が機械生成する。"
                "対象・正本側・実装側は生成器が更新し、判定・理由と典拠は人間が記入する。"
            ),
            "",
            "## 生成コマンド",
            "",
            "```bash",
            "uv run python scripts/generate_orm_acceptance_sheets.py",
            "```",
            "",
            "既定の再生成では判定欄と理由欄が空になる。",
            "",
            "是正前の判定を安全な行だけ持ち越す場合:",
            "",
            "```bash",
            (
                "uv run python scripts/generate_orm_acceptance_sheets.py "
                "--carry-judgments-from <是正前のrevision>"
            ),
            "```",
            "",
            (
                "持ち越しモードは突合キーが不変・旧判定が差分でない・旧理由が"
                "契約 diff の変更識別子を含まない行だけを引き継ぐ。"
            ),
            "",
            "## シート",
            "",
            f"- [N1 表の全数性](N1-table-completeness.md): {n1_count} 行",
            (
                "- [N3 不変列マトリクスの全数性]"
                f"(N3-immutability-completeness.md): {n3_count} 行"
            ),
            (
                "- [N4 削除系統の割り当て]"
                f"(N4-deletion-lifecycle.md): {n4_count} 行"
            ),
            (
                "- [N7 必須属性の全数性]"
                f"(N7-required-attributes.md): {n7_count} 行"
            ),
            "",
            "## シートを作らない受け取り先",
            "",
            "- N2: TSK-250 の 88 列写像の確定ゲートで閉じる。",
            "- N5: TSK-356 の 88 列互換出力（FR-031）の往復検証で閉じる。",
            (
                "- N6: 運用証跡として、各環境の初回 migration 前に実施者・確認時点・"
                "endpoint 種別だけを PR 本文の実施記録行へ残す。"
                "URL や資格情報は記録しない。"
            ),
            "",
        ]
    )


def render_sheets(repo_root: Path) -> dict[str, str]:
    """正本・manifest・models から未判定の突合シートを生成する。

    Args:
        repo_root: リポジトリルート。

    Returns:
        出力ファイル名から生成本文への対応。README も含む。
    """
    lines = (repo_root / DATA_MODEL_RELATIVE_PATH).read_text(
        encoding="utf-8"
    ).splitlines()
    tables = _load_manifest_tables(repo_root)
    markdown_tables = _markdown_tables(lines)
    model_sources = _model_sources(repo_root)

    n1_rows = _n1_rows(lines, tables)
    n3_rows = _n3_rows(lines, markdown_tables, tables)
    n4_direct_rows = _n4_direct_rows(markdown_tables, tables)
    n4_manifest_candidate_rows = _n4_manifest_candidate_rows(tables)
    n7_rows = _n7_rows(lines, markdown_tables, tables, model_sources)

    sheets = {
        "N1-table-completeness.md": _render_sheet(
            "N1",
            "表の全数性",
            "data-model.md の 5〜12 章の全見出し",
            "表を定義している記述の全数。表を定義しない見出しも対象外候補として残す。",
            (
                "見出しを文書順に機械抽出し、manifest の source_sections から"
                "表候補を並べて人間が判定する。"
            ),
            (("突合行（正本の文書順）", n1_rows),),
        ),
        "N3-immutability-completeness.md": _render_sheet(
            "N3",
            "不変列マトリクスの全数性",
            "data-model.md 全文にある設計指定の 9 語の全出現",
            (
                "不変・変えない・昇格させない・後退させない・追記のみ・変更不可・"
                "更新しない・上書きしない・書き換えない。"
            ),
            (
                "各語を文書順に機械抽出し、同じ正本節を持つ manifest の "
                "immutability 候補と人間が突き合わせる。"
            ),
            (("突合行（正本の文書順）", n3_rows),),
        ),
        "N4-deletion-lifecycle.md": _render_sheet(
            "N4",
            "削除系統の割り当て",
            "data-model.md 11-1 節の削除 4 系統表が挙げる業務オブジェクト",
            (
                "同表の直接対象と manifest の lifecycle.deletion。"
                "その他の物理表は直接割当なし候補として分離する。"
            ),
            (
                "4 系統表を表順・対象順に抽出する。続けて manifest 全表を"
                "正本節順に直接割当なしの確認候補として並べ、人間が対象を切り分ける。"
            ),
            (
                ("11-1 節の直接割当", n4_direct_rows),
                (
                    "正本に直接割当なしの確認候補",
                    n4_manifest_candidate_rows,
                ),
            ),
        ),
        "N7-required-attributes.md": _render_n7_sheet(n7_rows),
    }
    row_counts = {
        filename: len(parse_sheet_rows(content))
        for filename, content in sheets.items()
    }
    sheets["README.md"] = _render_readme(row_counts)
    return sheets


def parse_sheet_rows(content: str) -> tuple[SheetRow, ...]:
    """生成済み Markdown から人間判定対象の行だけを読む。

    Args:
        content: 突合シートの Markdown。

    Returns:
        判定欄と理由欄を含む突合行。
    """
    rows: list[SheetRow] = []
    in_table = False
    for line in content.splitlines():
        if not line.lstrip().startswith("|"):
            in_table = False
            continue
        cells = _split_markdown_row(line)
        if cells == SHEET_HEADERS:
            in_table = True
            continue
        if not in_table or _is_separator_row(cells):
            continue
        if len(cells) != len(SHEET_HEADERS):
            raise ValueError("突合行の列数が 5 ではない")
        rows.append(SheetRow(*cells))
    return tuple(rows)


def _row_key(row: SheetRow) -> tuple[str, str, str]:
    """判定持ち越しに使う三つ組を返す。"""
    return row.target, row.canonical, row.implementation


def _replace_sheet_rows(content: str, rows: Sequence[SheetRow]) -> str:
    """生成本文の突合行だけを、同じ三つ組を持つ行へ置き換える。"""
    replacements = iter(rows)
    rendered: list[str] = []
    in_table = False
    replaced = 0
    for line in content.splitlines():
        if not line.lstrip().startswith("|"):
            in_table = False
            rendered.append(line)
            continue
        cells = _split_markdown_row(line)
        if cells == SHEET_HEADERS:
            in_table = True
            rendered.append(line)
            continue
        if not in_table or _is_separator_row(cells):
            rendered.append(line)
            continue
        replacement = next(replacements)
        if tuple(cells[:3]) != _row_key(replacement):
            raise ValueError("置換対象の突合キーが生成本文と一致しない")
        rendered.append(
            "| "
            + " | ".join(
                _escape_cell(value)
                for value in (
                    replacement.target,
                    replacement.canonical,
                    replacement.implementation,
                    replacement.judgment,
                    replacement.rationale,
                )
            )
            + " |"
        )
        replaced += 1
    if replaced != len(rows):
        raise ValueError("置換されなかった突合行がある")
    try:
        next(replacements)
    except StopIteration:
        pass
    else:
        raise ValueError("生成本文より置換行が多い")
    suffix = "\n" if content.endswith("\n") else ""
    return "\n".join(rendered) + suffix


def without_human_judgments(content: str) -> str:
    """判定欄と理由欄だけを空にし、生成された本文構造を保つ。"""
    rows = tuple(
        SheetRow(row.target, row.canonical, row.implementation)
        for row in parse_sheet_rows(content)
    )
    return _replace_sheet_rows(content, rows)


def _rationale_mentions_identifier(
    rationale: str, identifiers: set[str]
) -> bool:
    """理由欄が変更識別子を独立した語として含むかを返す。"""
    for identifier in identifiers:
        if identifier.isascii():
            if re.search(
                rf"(?<![A-Za-z0-9_]){re.escape(identifier)}(?![A-Za-z0-9_])",
                rationale,
            ):
                return True
        elif identifier in rationale:
            return True
    return False


def carry_forward_sheet(
    generated: str,
    previous: str,
    changed_identifiers: set[str],
) -> tuple[str, CarryForwardStats]:
    """3 条件を満たす旧判定だけを新しい生成本文へ持ち越す。"""
    previous_by_key = {_row_key(row): row for row in parse_sheet_rows(previous)}
    previous_by_target = {
        row.target: row for row in parse_sheet_rows(previous)
    }
    carried_rows: list[SheetRow] = []
    counts: Counter[str] = Counter()
    for row in parse_sheet_rows(generated):
        previous_row = previous_by_key.get(_row_key(row))
        comparable_previous = previous_row or previous_by_target.get(row.target)
        key_changed = previous_row is None
        was_difference = (
            comparable_previous is not None
            and comparable_previous.judgment == "差分"
        )
        mentions_changed_identifier = (
            comparable_previous is not None
            and _rationale_mentions_identifier(
                comparable_previous.rationale, changed_identifiers
            )
        )
        if key_changed:
            counts["key_changed"] += 1
        if was_difference:
            counts["difference"] += 1
        if mentions_changed_identifier:
            counts["changed_identifier"] += 1
        if key_changed or was_difference or mentions_changed_identifier:
            counts["reset_count"] += 1
            carried_rows.append(row)
        else:
            assert previous_row is not None
            counts["carried"] += 1
            carried_rows.append(
                SheetRow(
                    row.target,
                    row.canonical,
                    row.implementation,
                    previous_row.judgment,
                    previous_row.rationale,
                )
            )
    stats = CarryForwardStats(
        carried=counts["carried"],
        key_changed=counts["key_changed"],
        difference=counts["difference"],
        changed_identifier=counts["changed_identifier"],
        reset_count=counts["reset_count"],
    )
    return _replace_sheet_rows(generated, carried_rows), stats


def carry_forward_sheets(
    generated: Mapping[str, str],
    previous: Mapping[str, str],
    changed_identifiers: set[str],
) -> tuple[dict[str, str], dict[str, CarryForwardStats]]:
    """4 シートへ判定を持ち越し、README は生成結果をそのまま使う。"""
    carried = dict(generated)
    stats: dict[str, CarryForwardStats] = {}
    for filename in SHEET_FILENAMES:
        carried[filename], stats[filename] = carry_forward_sheet(
            generated[filename], previous[filename], changed_identifiers
        )
    return carried, stats


def _identifiers_from_contract_diff(diff: str) -> set[str]:
    """契約 diff の追加・削除行から列名・値・制約名を抽出する。"""
    identifiers: set[str] = set()
    for line in diff.splitlines():
        if (
            not line.startswith(("+", "-"))
            or line.startswith(("+++", "---"))
            or '"""' in line
        ):
            continue
        declaration = _DECLARED_IDENTIFIER_RE.match(line)
        if declaration:
            identifiers.add(declaration.group("identifier"))
        for quoted in _QUOTED_FRAGMENT_RE.finditer(line):
            for identifier in _CONTRACT_IDENTIFIER_RE.findall(
                quoted.group("value")
            ):
                if identifier not in _DIFF_STRUCTURE_WORDS:
                    identifiers.add(identifier)
        if '"checks"' in line or "CheckConstraint" in line:
            identifiers.add("CHECK")
    return identifiers


def changed_contract_identifiers(repo_root: Path, baseline: str) -> set[str]:
    """基準 revision 以後の manifest・DB 製品コード差分から識別子を返す。"""
    result = subprocess.run(
        [
            "git",
            "diff",
            "--unified=0",
            f"{baseline}..HEAD",
            "--",
            MANIFEST_RELATIVE_PATH.as_posix(),
            "backend/src/pitchlog/db/",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"変更識別子の抽出に失敗した: {result.stderr.strip()}"
        )
    return _identifiers_from_contract_diff(result.stdout)


def judgment_errors(sheets: Mapping[str, str]) -> list[str]:
    """人間判定済みシートが完了条件を満たすか調べる。

    Args:
        sheets: シート名から Markdown 本文への対応。

    Returns:
        未判定・未解消差分・不適格な対象外などの集約エラー。
    """
    errors: list[str] = []
    allowed = {"一致", "差分", "対象外"}
    for filename in SHEET_FILENAMES:
        counts: Counter[str] = Counter()
        rows = parse_sheet_rows(sheets[filename])
        for row in rows:
            if not row.judgment:
                counts["未判定"] += 1
            elif row.judgment not in allowed:
                counts["不正な判定"] += 1
            elif row.judgment == "差分":
                counts["未解消の差分"] += 1
            elif row.judgment == "対象外" and (
                not row.rationale or not _REFERENCE_RE.search(row.rationale)
            ):
                counts["理由とファイル:節の典拠がない対象外"] += 1
        errors.extend(
            f"{filename}: {category} {count} 行"
            for category, count in sorted(counts.items())
        )
    return errors


def _read_existing_sheets(repo_root: Path) -> dict[str, str]:
    """現在の判定済みシートを読み込む。"""
    output_root = repo_root / OUTPUT_RELATIVE_PATH
    return {
        filename: (output_root / filename).read_text(encoding="utf-8")
        for filename in SHEET_FILENAMES
    }


def render_sheets_with_carried_judgments(
    repo_root: Path,
    previous: Mapping[str, str],
    baseline: str,
) -> tuple[dict[str, str], dict[str, CarryForwardStats], set[str]]:
    """契約差分を基に安全な旧判定だけを持ち越して生成する。"""
    generated = render_sheets(repo_root)
    identifiers = changed_contract_identifiers(repo_root, baseline)
    carried, stats = carry_forward_sheets(generated, previous, identifiers)
    return carried, stats, identifiers


def write_sheets(
    repo_root: Path, *, carry_judgments_from: str | None = None
) -> dict[str, str]:
    """突合シートを所定ディレクトリへ書き出す。

    Args:
        repo_root: リポジトリルート。
        carry_judgments_from: 判定を持ち越す場合の是正前 revision。

    Returns:
        書き出したファイル名から本文への対応。
    """
    if carry_judgments_from is None:
        sheets = render_sheets(repo_root)
    else:
        sheets, _, _ = render_sheets_with_carried_judgments(
            repo_root,
            _read_existing_sheets(repo_root),
            carry_judgments_from,
        )
    output_root = repo_root / OUTPUT_RELATIVE_PATH
    output_root.mkdir(parents=True, exist_ok=True)
    for filename, content in sheets.items():
        (output_root / filename).write_text(content, encoding="utf-8")
    return sheets


def main(argv: Sequence[str] | None = None) -> int:
    """コマンドライン引数を解釈して突合シートを生成する。

    Args:
        argv: コマンドライン引数。``None`` なら実プロセスの引数を使う。

    Returns:
        正常終了時は 0。
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="リポジトリルート",
    )
    parser.add_argument(
        "--carry-judgments-from",
        metavar="REVISION",
        help="指定 revision 以後の契約差分を使い、安全な旧判定だけを持ち越す",
    )
    args = parser.parse_args(argv)
    sheets = write_sheets(
        args.repo_root.resolve(),
        carry_judgments_from=args.carry_judgments_from,
    )
    for filename in sorted(sheets):
        print(f"generated: {OUTPUT_RELATIVE_PATH / filename}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
