"""正本6-2と処理段階スナップショットの逐語照合を検証する。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY_ROOT / "scripts" / "check_processing_stages.py"
DOCUMENT = REPOSITORY_ROOT / "docs" / "design" / "sync-protocol.md"
SNAPSHOT = (
    REPOSITORY_ROOT
    / "frontend"
    / "src"
    / "lib"
    / "sync"
    / "processingStages.snapshot.json"
)
SECTION_HEADING = "### 6-2."
NEXT_SECTION_HEADING = "### 6-3."
D1_HEADER = "| 段階 | 何を確かめるか | ここで止まったときの境界結果 |"
P3_HEADER = (
    "| 順序 | 進行中の P3 | 終了後の P3 | ここで止まったときの境界結果 |"
)


def _run_cli(
    *, document: Path = DOCUMENT, snapshot: Path = SNAPSHOT
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--root",
            str(REPOSITORY_ROOT),
            "--document",
            str(document),
            "--snapshot",
            str(snapshot),
        ],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _duplicate_heading(document: str, heading_prefix: str) -> str:
    lines = document.splitlines()
    heading_index = next(
        index for index, line in enumerate(lines) if line.startswith(heading_prefix)
    )
    lines.insert(heading_index + 1, lines[heading_index])
    return "\n".join(lines)


def _duplicate_table_with_mutated_cell(
    document: str,
    header: str,
    row_count: int,
    original_cell: str,
    mutated_cell: str,
) -> str:
    lines = document.splitlines()
    header_index = lines.index(header)
    table_line_count = row_count + 2
    table_block = lines[header_index : header_index + table_line_count]
    mutated_block = [
        line.replace(original_cell, mutated_cell, 1) for line in table_block
    ]
    insertion_index = header_index + table_line_count
    lines[insertion_index:insertion_index] = ["", *mutated_block]
    return "\n".join(lines)


def _write_document(tmp_path: Path, document: str) -> Path:
    path = tmp_path / "sync-protocol.md"
    path.write_text(document, encoding="utf-8")
    return path


def test_canonical_document_matches_processing_stage_snapshot() -> None:
    result = _run_cli()

    assert result.returncode == 0
    assert "processing-stages: OK" in result.stdout


def test_document_row_mutation_is_reported_without_modifying_canon(
    tmp_path: Path,
) -> None:
    document = DOCUMENT.read_text(encoding="utf-8")
    original = "| ② 認証 | 呼び出し元が認証されているか | **B5 認証失効** |"
    mutated = "| ② 認証 | 呼び出し元を後から認証するか | **B5 認証失効** |"
    assert original in document
    mutated_document = tmp_path / "sync-protocol.md"
    mutated_document.write_text(document.replace(original, mutated, 1), encoding="utf-8")

    result = _run_cli(document=mutated_document)

    assert result.returncode == 1
    assert "d1Stages[1].check が一致しません" in result.stderr


def test_snapshot_row_mutation_is_reported_without_modifying_snapshot(
    tmp_path: Path,
) -> None:
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    snapshot["p3Stages"][0]["stopBoundaryResult"] = "B10以外"
    mutated_snapshot = tmp_path / "processingStages.snapshot.json"
    mutated_snapshot.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    result = _run_cli(snapshot=mutated_snapshot)

    assert result.returncode == 1
    assert "p3Stages[0].stopBoundaryResult が一致しません" in result.stderr


def test_duplicate_section_heading_is_rejected(tmp_path: Path) -> None:
    document = DOCUMENT.read_text(encoding="utf-8")
    mutated_document = _write_document(
        tmp_path, _duplicate_heading(document, SECTION_HEADING)
    )

    result = _run_cli(document=mutated_document)

    assert result.returncode == 1
    assert "入力不正" in result.stderr
    assert "正本の6-2見出しは厳密に1件必要ですが2件" in result.stderr


def test_duplicate_next_section_heading_is_rejected(tmp_path: Path) -> None:
    document = DOCUMENT.read_text(encoding="utf-8")
    mutated_document = _write_document(
        tmp_path, _duplicate_heading(document, NEXT_SECTION_HEADING)
    )

    result = _run_cli(document=mutated_document)

    assert result.returncode == 1
    assert "入力不正" in result.stderr
    assert "6-2節開始後の6-3見出しは厳密に1件必要ですが2件" in result.stderr


def test_duplicate_d1_table_with_later_mutation_is_rejected(tmp_path: Path) -> None:
    document = DOCUMENT.read_text(encoding="utf-8")
    mutation = _duplicate_table_with_mutated_cell(
        document,
        D1_HEADER,
        9,
        "要求が届き、処理が完了したか",
        "後続側だけを変更",
    )
    assert mutation.count(D1_HEADER) == 2
    assert mutation.count("後続側だけを変更") == 1
    mutated_document = _write_document(tmp_path, mutation)

    result = _run_cli(document=mutated_document)

    assert result.returncode == 1
    assert "入力不正" in result.stderr
    assert "6-2節の表ヘッダー" in result.stderr
    assert "段階" in result.stderr
    assert "厳密に1件必要ですが2件" in result.stderr


def test_duplicate_p3_table_with_later_mutation_is_rejected(tmp_path: Path) -> None:
    document = DOCUMENT.read_text(encoding="utf-8")
    mutation = _duplicate_table_with_mutated_cell(
        document,
        P3_HEADER,
        11,
        "要求が届き、処理が完了したか",
        "後続側だけを変更",
    )
    assert mutation.count(P3_HEADER) == 2
    assert mutation.count("後続側だけを変更") == 1
    mutated_document = _write_document(tmp_path, mutation)

    result = _run_cli(document=mutated_document)

    assert result.returncode == 1
    assert "入力不正" in result.stderr
    assert "6-2節の表ヘッダー" in result.stderr
    assert "進行中の P3" in result.stderr
    assert "厳密に1件必要ですが2件" in result.stderr
