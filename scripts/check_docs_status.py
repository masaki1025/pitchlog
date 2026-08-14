"""正本と feature 計画書の frontmatter status を検査する。"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Sequence


DOCUMENT_STATUSES = frozenset({"draft", "in-review", "approved", "superseded"})
PLAN_STATUSES = frozenset({"active", "in-review"})
EXCLUDED_PREFIXES = (
    ("docs", "worklog"),
    ("docs", "legacy"),
    ("docs", "development", "templates"),
)
PRIMARY_HEADING_RE = re.compile(r"^##\s+正本\s*$")
SECTION_HEADING_RE = re.compile(r"^##\s+")
STATUS_PREFIX_RE = re.compile(r"^status\s*:")
PRIMARY_STATUS_LINE_RE = re.compile(r"^status: (?P<status>[^\s#]+)$")
PLAN_STATUS_LINE_RE = re.compile(
    r"^status:\s*(?P<status>[^\s#]+)(?:\s+#.*)?$"
)
MARKDOWN_LINK_RE = re.compile(
    r"\[[^\]]+\]\((?P<target><[^>]+>|[^)\s]+)(?:\s+[^)]*)?\)"
)
INDEX_VERSION_NONE = "—"
INDEX_VERSION_RE = re.compile(r"^\d+(?:\.\d+)*$")
INDEX_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class IndexedDocument:
    """索引から取得した正本文書、状態、版、最終更新を表す。

    Attributes:
        path: 正本文書の絶対パス。
        index_status: 索引の状態セルを正規化した値。
        index_version: 索引の版セルを正規化した値。
        index_updated: 索引の最終更新セルを正規化した値。
    """

    path: Path
    index_status: str
    index_version: str
    index_updated: str


def display_path(path: Path, root: Path) -> str:
    """違反出力に使うリポジトリ相対パスを返す。

    Args:
        path: 表示対象のパス。
        root: リポジトリルート。

    Returns:
        リポジトリ配下なら POSIX 形式の相対パス、配下でなければ絶対パス。
    """
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def violation(path: Path, root: Path, reason: str) -> str:
    """所定形式の違反メッセージを作る。

    Args:
        path: 違反対象のパス。
        root: リポジトリルート。
        reason: 違反理由。

    Returns:
        ``ファイルパス: 理由`` 形式の文字列。
    """
    return f"{display_path(path, root)}: {reason}"


def is_excluded(path: Path, root: Path) -> bool:
    """検査対象から除外するディレクトリ配下かを判定する。

    Args:
        path: 判定対象のパス。
        root: リポジトリルート。

    Returns:
        除外対象なら ``True``、それ以外なら ``False``。
    """
    try:
        relative_parts = path.resolve().relative_to(root.resolve()).parts
    except ValueError:
        return False
    return any(relative_parts[:len(prefix)] == prefix for prefix in EXCLUDED_PREFIXES)


def normalize_index_cell(cell: str) -> str:
    """索引セルから太字マーカーと前後空白を除去する。

    Args:
        cell: Markdown 表にある索引セルの文字列。

    Returns:
        太字マーカーと前後空白を除去した値。
    """
    return cell.replace("**", "").strip()


def normalize_index_status(cell: str) -> str:
    """索引の状態セルを frontmatter と比較できる形に正規化する。

    Args:
        cell: Markdown 表にある状態セルの文字列。

    Returns:
        太字マーカーと最初の括弧以降を除去した状態語彙。
    """
    return normalize_index_cell(cell).split("(", 1)[0].strip()


def is_valid_index_version(value: str) -> bool:
    """索引の版セルが許可された書式かを判定する。

    Args:
        value: 太字マーカーを除去した版セルの値。

    Returns:
        数値のドット区切り形式または EM DASH なら ``True``、それ以外なら ``False``。
    """
    return value == INDEX_VERSION_NONE or INDEX_VERSION_RE.fullmatch(value) is not None


def is_valid_index_updated(value: str) -> bool:
    """索引の最終更新セルが実在する ISO 形式の日付かを判定する。

    Args:
        value: 太字マーカーを除去した最終更新セルの値。

    Returns:
        ``YYYY-MM-DD`` 形式かつ実在する日付なら ``True``、それ以外なら ``False``。
    """
    if INDEX_DATE_RE.fullmatch(value) is None:
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def parse_table_cells(line: str) -> list[str]:
    """Markdown 表の 1 行をセル配列へ分割する。

    Args:
        line: ``|`` で始まる Markdown 表の行。

    Returns:
        前後空白を除去したセルの配列。
    """
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def is_table_separator(cells: Sequence[str]) -> bool:
    """Markdown 表の区切り行かを判定する。

    Args:
        cells: 表のセル配列。

    Returns:
        区切り行なら ``True``、それ以外なら ``False``。
    """
    if not cells:
        return False
    return all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells)


def extract_link_target(cell: str) -> str | None:
    """Markdown リンクセルからローカル Markdown のリンク先を取り出す。

    Args:
        cell: 文書列の Markdown 表セル。

    Returns:
        フラグメントを除いた Markdown ファイルへの相対パス。取得できなければ ``None``。
    """
    match = MARKDOWN_LINK_RE.search(cell)
    if match is None:
        return None
    target = match.group("target").strip().strip("<>").split("#", 1)[0]
    if not target.endswith(".md") or Path(target).is_absolute() or "://" in target:
        return None
    return target


def primary_table_lines(lines: Sequence[str]) -> list[str] | None:
    """索引の「正本」見出し直下にある最初の Markdown 表を取得する。

    Args:
        lines: 索引ファイルを行単位で分割した配列。

    Returns:
        表の行配列。見出しまたは表が無ければ ``None``。
    """
    section_start = next(
        (index + 1 for index, line in enumerate(lines) if PRIMARY_HEADING_RE.fullmatch(line)),
        None,
    )
    if section_start is None:
        return None

    table_start = None
    for index in range(section_start, len(lines)):
        line = lines[index]
        if SECTION_HEADING_RE.match(line):
            break
        if line.lstrip().startswith("|"):
            table_start = index
            break
    if table_start is None:
        return None

    table: list[str] = []
    for index in range(table_start, len(lines)):
        line = lines[index]
        if not line.lstrip().startswith("|"):
            break
        table.append(line)
    return table


def extract_indexed_documents(root: Path) -> tuple[list[IndexedDocument], list[str]]:
    """正本一覧から文書パスと状態を動的に取得する。

    Args:
        root: リポジトリルート。

    Returns:
        取得できた正本文書の配列と、索引自体の違反メッセージ配列。
    """
    index_path = root / "docs" / "README.md"
    try:
        lines = index_path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        return [], [violation(index_path, root, f"索引を読み込めない: {error}")]
    except UnicodeDecodeError as error:
        return [], [violation(index_path, root, f"索引が UTF-8 ではない: {error}")]

    table = primary_table_lines(lines)
    if table is None:
        return [], [violation(index_path, root, "「## 正本」配下に Markdown 表がない")]
    if not table:
        return [], [violation(index_path, root, "正本一覧の表が空")]

    header = parse_table_cells(table[0])
    try:
        document_column = header.index("文書")
        status_column = header.index("状態")
        version_column = header.index("版")
        updated_column = header.index("最終更新")
    except ValueError:
        return [], [
            violation(index_path, root, "正本一覧に「文書」「状態」「版」「最終更新」の列が必要")
        ]

    documents: list[IndexedDocument] = []
    violations: list[str] = []
    for line in table[1:]:
        cells = parse_table_cells(line)
        if is_table_separator(cells):
            continue
        if len(cells) <= max(
            document_column,
            status_column,
            version_column,
            updated_column,
        ):
            violations.append(violation(index_path, root, "正本一覧の行に必要な列がない"))
            continue
        target = extract_link_target(cells[document_column])
        if target is None:
            violations.append(
                violation(index_path, root, "正本一覧の文書列にローカル .md リンクがない")
            )
            continue
        index_version = normalize_index_cell(cells[version_column])
        index_updated = normalize_index_cell(cells[updated_column])
        if not is_valid_index_version(index_version):
            violations.append(
                violation(index_path, root, f"正本一覧の版が不正: {index_version}")
            )
        if not is_valid_index_updated(index_updated):
            violations.append(
                violation(index_path, root, f"正本一覧の最終更新が不正: {index_updated}")
            )
        documents.append(
            IndexedDocument(
                path=(index_path.parent / target).resolve(),
                index_status=normalize_index_status(cells[status_column]),
                index_version=index_version,
                index_updated=index_updated,
            )
        )

    if not documents:
        violations.append(violation(index_path, root, "正本一覧に文書行がない"))
    return documents, violations


def read_markdown_lines(path: Path) -> tuple[list[str] | None, str | None]:
    """Markdown ファイルを UTF-8 で行単位に読み込む。

    Args:
        path: 読み込む Markdown ファイルのパス。

    Returns:
        ``(行配列, None)`` または ``(None, 違反理由)`` の組。
    """
    try:
        return path.read_text(encoding="utf-8").splitlines(), None
    except OSError as error:
        return None, f"読み込めない: {error}"
    except UnicodeDecodeError as error:
        return None, f"UTF-8 として読み込めない: {error}"


def validate_status_value(status: str, allowed_statuses: frozenset[str]) -> str | None:
    """status が対象文書で許可された語彙かを検証する。

    Args:
        status: frontmatter から抽出した status。
        allowed_statuses: 文書種別に許可する status 語彙。

    Returns:
        許可値なら ``None``、それ以外なら違反理由。
    """
    if status in allowed_statuses:
        return None
    allowed = " | ".join(sorted(allowed_statuses))
    return f"status の語彙が不正: {status} (許可値: {allowed})"


def read_primary_frontmatter_status(
    path: Path,
    allowed_statuses: frozenset[str],
) -> tuple[str | None, str | None]:
    """正本の厳格な3行 frontmatter から status を読み取る。

    Args:
        path: 検査対象の正本 Markdown ファイル。
        allowed_statuses: このファイル種別で許可する status 語彙。

    Returns:
        ``(status, None)`` または ``(None, 違反理由)`` の組。
    """
    lines, read_error = read_markdown_lines(path)
    if read_error is not None:
        return None, read_error
    assert lines is not None

    if not lines or lines[0] != "---":
        return None, "先頭行が frontmatter 開始記号 `---` ではない"
    if len(lines) < 3 or lines[2] != "---":
        return None, "frontmatter の終端 `---` が 3 行目ではない"

    match = PRIMARY_STATUS_LINE_RE.fullmatch(lines[1])
    if match is None:
        return None, "2 行目が status: <語彙> 形式ではない"
    status = match.group("status")
    return status, validate_status_value(status, allowed_statuses)


def read_plan_frontmatter_status(
    path: Path,
    allowed_statuses: frozenset[str],
) -> tuple[str | None, str | None]:
    """feature 計画書の frontmatter から status を読み取る。

    他の frontmatter キーは許容し、status 行の行末コメントは ``#`` 以降を無視する。

    Args:
        path: 検査対象の feature 計画書。
        allowed_statuses: このファイル種別で許可する status 語彙。

    Returns:
        ``(status, None)`` または ``(None, 違反理由)`` の組。
    """
    lines, read_error = read_markdown_lines(path)
    if read_error is not None:
        return None, read_error
    assert lines is not None

    if not lines or lines[0] != "---":
        return None, "先頭行が frontmatter 開始記号 `---` ではない"

    try:
        end = next(index for index, line in enumerate(lines[1:], start=1) if line == "---")
    except StopIteration:
        return None, "frontmatter の終端 `---` がない"

    status_lines = [line for line in lines[1:end] if STATUS_PREFIX_RE.match(line)]
    if not status_lines:
        return None, "frontmatter に status 行がない"
    if len(status_lines) != 1:
        return None, "frontmatter の status 行がちょうど 1 行ではない"

    match = PLAN_STATUS_LINE_RE.fullmatch(status_lines[0])
    if match is None:
        return None, "status 行の形式が不正"
    status = match.group("status")
    return status, validate_status_value(status, allowed_statuses)


def check_document_status(
    path: Path,
    root: Path,
    allowed_statuses: frozenset[str],
    index_status: str | None = None,
    strict_primary: bool = False,
) -> list[str]:
    """1 つの Markdown ファイルの frontmatter と索引整合を検査する。

    Args:
        path: 検査対象 Markdown ファイル。
        root: リポジトリルート。
        allowed_statuses: このファイル種別で許可する status 語彙。
        index_status: 索引から取得した比較対象の状態。不要なら ``None``。
        strict_primary: 正本向けの厳格な3行 frontmatter を要求するか。

    Returns:
        検出した違反メッセージの配列。
    """
    if strict_primary:
        status, reason = read_primary_frontmatter_status(path, allowed_statuses)
    else:
        status, reason = read_plan_frontmatter_status(path, allowed_statuses)
    if reason is not None:
        return [violation(path, root, reason)]
    if index_status is not None and status != index_status:
        return [
            violation(
                path,
                root,
                f"frontmatter の status({status})と索引の状態({index_status})が一致しない",
            )
        ]
    return []


def check_repository(root: Path) -> list[str]:
    """リポジトリ内の正本と feature 計画書を検査する。

    Args:
        root: リポジトリルート。

    Returns:
        検出した違反メッセージの配列。
    """
    root = root.resolve()
    documents, violations = extract_indexed_documents(root)
    for document in documents:
        if is_excluded(document.path, root):
            continue
        violations.extend(
            check_document_status(
                document.path,
                root,
                DOCUMENT_STATUSES,
                document.index_status,
                strict_primary=True,
            )
        )

    features_dir = root / "docs" / "features"
    if features_dir.is_dir():
        for plan_path in sorted(features_dir.glob("*/plan.md")):
            if is_excluded(plan_path, root):
                continue
            violations.extend(check_document_status(plan_path, root, PLAN_STATUSES))
    return violations


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """コマンドライン引数を解釈する。

    Args:
        argv: テスト時に指定する引数列。省略時は標準入力以外の通常の引数を使う。

    Returns:
        解釈済みのコマンドライン引数。
    """
    parser = argparse.ArgumentParser(description="正本と feature 計画書の status を検査する")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="リポジトリルート(既定: カレントディレクトリ)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """検査を実行し、違反の有無に応じた終了コードを返す。

    Args:
        argv: テスト時に指定する引数列。省略時はコマンドライン引数を使う。

    Returns:
        違反なしなら 0、違反ありなら 1。
    """
    args = parse_args(argv)
    violations = check_repository(args.root)
    for message in violations:
        print(message, file=sys.stderr)
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
