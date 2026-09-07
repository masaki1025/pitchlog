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
