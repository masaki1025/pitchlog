"""同期プロトコル正本6-2の処理段階表とスナップショットを逐語照合する。"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DOCUMENT = Path("docs/design/sync-protocol.md")
DEFAULT_SNAPSHOT = Path("frontend/src/lib/sync/processingStages.snapshot.json")
SECTION_HEADING = "### 6-2."
NEXT_SECTION_HEADING = "### 6-3."
D1_HEADERS = ("段階", "何を確かめるか", "ここで止まったときの境界結果")
P3_HEADERS = (
    "順序",
    "進行中の P3",
    "終了後の P3",
    "ここで止まったときの境界結果",
)
D1_KEYS = ("stage", "check", "stopBoundaryResult")
P3_KEYS = ("order", "inProgress", "afterCompletion", "stopBoundaryResult")
TABLE_DELIMITER_RE = re.compile(r"^:?-{3,}:?$")


class ProcessingStagesError(Exception):
    """正本またはスナップショットの入力不正を表す。"""


class ProcessingStagesDuplicateError(ProcessingStagesError):
    """正本の見出しまたは表ヘッダーの重複を表す。"""


@dataclass(frozen=True)
class ProcessingStageTables:
    """正規化済みの2つの処理段階表を表す。

    Attributes:
        d1_stages: D1付き経路の9行3列。
        p3_stages: P3経路の11行4列。
    """

    d1_stages: tuple[tuple[str, ...], ...]
    p3_stages: tuple[tuple[str, ...], ...]


def _read_text(path: Path, label: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        raise ProcessingStagesError(f"{label}を読めない: {path}: {error}") from error


def _table_cells(line: str) -> tuple[str, ...] | None:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return None
    return tuple(cell.strip().replace("**", "") for cell in stripped[1:-1].split("|"))


def _require_unique_index(indices: tuple[int, ...], label: str) -> int:
    """対象位置が厳密に1件であることを検証する。

    Args:
        indices: 対象に一致した行の位置。
        label: エラーで特定する対象名。

    Returns:
        一意な対象位置。

    Raises:
        ProcessingStagesError: 対象が存在しない場合。
        ProcessingStagesDuplicateError: 対象が重複している場合。
    """
    count = len(indices)
    if count == 0:
        raise ProcessingStagesError(f"{label}は厳密に1件必要ですが0件でした")
    if count > 1:
        raise ProcessingStagesDuplicateError(
            f"{label}は厳密に1件必要ですが{count}件ありました"
        )
    return indices[0]


def _section_lines(document: str) -> list[str]:
    lines = document.splitlines()
    start = _require_unique_index(
        tuple(
            index
            for index, line in enumerate(lines)
            if line.startswith(SECTION_HEADING)
        ),
        "正本の6-2見出し",
    )
    end = _require_unique_index(
        tuple(
            index
            for index, line in enumerate(lines[start + 1 :], start=start + 1)
            if line.startswith(NEXT_SECTION_HEADING)
        ),
        "6-2節開始後の6-3見出し",
    )
    return lines[start:end]


def _extract_table(
    section_lines: list[str],
    headers: tuple[str, ...],
    expected_rows: int,
) -> tuple[tuple[str, ...], ...]:
    header_index = _require_unique_index(
        tuple(
            index
            for index, line in enumerate(section_lines)
            if _table_cells(line) == headers
        ),
        f"6-2節の表ヘッダー {headers}",
    )
    if header_index + 1 >= len(section_lines):
        raise ProcessingStagesError(f"6-2節の表区切りがありません: {headers}")
    delimiter = _table_cells(section_lines[header_index + 1])
    if delimiter is None or len(delimiter) != len(headers) or not all(
        TABLE_DELIMITER_RE.fullmatch(cell) for cell in delimiter
    ):
        raise ProcessingStagesError(f"6-2節の表区切りが不正です: {headers}")

    rows: list[tuple[str, ...]] = []
    for line in section_lines[header_index + 2 :]:
        cells = _table_cells(line)
        if cells is None:
            break
        if len(cells) != len(headers):
            raise ProcessingStagesError(
                f"6-2節の表列数が{len(headers)}ではありません: {line}"
            )
        rows.append(cells)
    if len(rows) != expected_rows:
        raise ProcessingStagesError(
            f"6-2節の表行数が{expected_rows}ではありません: headers={headers} actual={len(rows)}"
        )
    return tuple(rows)


def extract_processing_stage_tables(document: str) -> ProcessingStageTables:
    """正本6-2節からD1付き経路とP3の処理段階表を抽出する。

    Args:
        document: 同期プロトコル正本のMarkdown全文。

    Returns:
        強調記号を除去した2つの処理段階表。

    Raises:
        ProcessingStagesError: 6-2節または対象表の構造が不正な場合。
    """
    lines = _section_lines(document)
    return ProcessingStageTables(
        d1_stages=_extract_table(lines, D1_HEADERS, 9),
        p3_stages=_extract_table(lines, P3_HEADERS, 11),
    )


def _snapshot_rows(
    raw: object,
    table_key: str,
    row_keys: tuple[str, ...],
    expected_rows: int,
) -> tuple[tuple[str, ...], ...]:
    if not isinstance(raw, Mapping) or set(raw) != set(("d1Stages", "p3Stages")):
        raise ProcessingStagesError("スナップショットのキー集合が不正です")
    rows = raw.get(table_key)
    if not isinstance(rows, list) or len(rows) != expected_rows:
        raise ProcessingStagesError(
            f"スナップショットの{table_key}行数が{expected_rows}ではありません"
        )

    normalized: list[tuple[str, ...]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping) or set(row) != set(row_keys):
            raise ProcessingStagesError(
                f"スナップショットの{table_key}[{index}]キー集合が不正です"
            )
        cells = tuple(row.get(key) for key in row_keys)
        if not all(isinstance(cell, str) for cell in cells):
            raise ProcessingStagesError(
                f"スナップショットの{table_key}[{index}]に文字列でないセルがあります"
            )
        normalized.append(tuple(cell for cell in cells if isinstance(cell, str)))
    return tuple(normalized)


def load_snapshot(path: Path) -> ProcessingStageTables:
    """処理段階スナップショットを読み、閉じた構造を検証する。

    Args:
        path: スナップショットJSONのパス。

    Returns:
        検証済みの2つの処理段階表。

    Raises:
        ProcessingStagesError: JSONを読めない、または構造が不正な場合。
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ProcessingStagesError(f"スナップショットを読めない: {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise ProcessingStagesError(f"スナップショットのJSONが不正: {path}: {error}") from error
    return ProcessingStageTables(
        d1_stages=_snapshot_rows(raw, "d1Stages", D1_KEYS, 9),
        p3_stages=_snapshot_rows(raw, "p3Stages", P3_KEYS, 11),
    )


def compare_processing_stage_tables(
    document_tables: ProcessingStageTables,
    snapshot_tables: ProcessingStageTables,
) -> tuple[str, ...]:
    """正本表とスナップショットをセル単位で比較する。

    Args:
        document_tables: 正本から抽出した表。
        snapshot_tables: JSONから読んだ表。

    Returns:
        表名・行・セルを含む不一致メッセージ。空なら一致。
    """
    findings: list[str] = []
    for table_key, row_keys, document_rows, snapshot_rows in (
        (
            "d1Stages",
            D1_KEYS,
            document_tables.d1_stages,
            snapshot_tables.d1_stages,
        ),
        (
            "p3Stages",
            P3_KEYS,
            document_tables.p3_stages,
            snapshot_tables.p3_stages,
        ),
    ):
        for row_index, (document_row, snapshot_row) in enumerate(
            zip(document_rows, snapshot_rows, strict=True)
        ):
            for column_index, (document_cell, snapshot_cell) in enumerate(
                zip(document_row, snapshot_row, strict=True)
            ):
                if document_cell != snapshot_cell:
                    findings.append(
                        f"{table_key}[{row_index}].{row_keys[column_index]} が一致しません: "
                        f"正本={document_cell!r} スナップショット={snapshot_cell!r}"
                    )
    return tuple(findings)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """コマンドライン引数を解釈する。

    Args:
        argv: テスト時に指定する引数列。省略時はコマンドライン引数を使う。

    Returns:
        解釈済み引数。
    """
    parser = argparse.ArgumentParser(description="正本6-2の処理段階表を検査する")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="リポジトリルート(既定: カレントディレクトリ)",
    )
    parser.add_argument("--document", type=Path, default=DEFAULT_DOCUMENT)
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    return parser.parse_args(argv)


def _resolve(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


def main(argv: Sequence[str] | None = None) -> int:
    """正本6-2とスナップショットを照合して終了コードを返す。

    Args:
        argv: テスト時に指定する引数列。省略時はコマンドライン引数を使う。

    Returns:
        一致なら0、不一致または重複なら1、その他の入力不正なら2。
    """
    try:
        args = parse_args(argv)
        root = args.root.resolve()
        document_path = _resolve(root, args.document)
        snapshot_path = _resolve(root, args.snapshot)
        document = _read_text(document_path, "正本")
        document_tables = extract_processing_stage_tables(document)
        snapshot_tables = load_snapshot(snapshot_path)
        findings = compare_processing_stage_tables(document_tables, snapshot_tables)
    except ProcessingStagesDuplicateError as error:
        print(f"processing-stages: 入力不正: {error}", file=sys.stderr)
        return 1
    except ProcessingStagesError as error:
        print(f"processing-stages: 入力不正: {error}", file=sys.stderr)
        return 2

    if findings:
        for finding in findings:
            print(f"processing-stages: {finding}", file=sys.stderr)
        return 1
    print("processing-stages: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
