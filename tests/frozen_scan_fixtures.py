"""凍結基準候補走査の合成fixtureを正常系と負例で共有する。"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CHECKER_PATH = REPOSITORY_ROOT / "scripts/check_frozen_baselines.py"
PERMANENT_VALUE = "a" * 40
PENDING_VALUE = "b" * 40
CHANGED_VALUE = "c" * 40
EMBEDDED_VALUE = "d" * 40


@dataclass(frozen=True)
class ScanFixture:
    """通常遷移用の合成走査fixtureを保持する。"""

    root: Path
    base_allowlist: Path
    head_allowlist: Path
    entries: list[dict[str, Any]]


def make_scan_entry(
    path: str,
    value: str,
    *,
    pending_removal: bool,
    reason: str | None = None,
) -> dict[str, Any]:
    """合成allow-listの1エントリを作る。"""
    return {
        "path": path,
        "value": value,
        "reason": reason if reason is not None else f"合成fixtureの{path}",
        "pending_removal": pending_removal,
    }


def write_scan_allowlist(path: Path, entries: list[dict[str, Any]]) -> None:
    """合成allow-listを完全なJSON objectとして書く。"""
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "asset_kind": "frozen_baseline_scan_allowlist",
                "entries": entries,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def write_scan_source(root: Path, path_text: str, source: str) -> None:
    """合成走査母集団へPythonソースを書く。"""
    path = root / path_text
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


def make_scan_root(tmp_path: Path) -> Path:
    """3つの走査rootを持つ空の合成repositoryを作る。"""
    root = tmp_path / "repository"
    for directory in ("scripts", "tests", "backend/tests"):
        (root / directory).mkdir(parents=True, exist_ok=True)
    return root


def run_synthetic_scan(
    root: Path,
    head_allowlist: Path,
    *,
    base_allowlist: Path | None = None,
    base_ledger_present: bool = False,
) -> subprocess.CompletedProcess[str]:
    """合成fixture専用の走査CLIを実行する。"""
    arguments = [
        sys.executable,
        str(CHECKER_PATH),
        "--scan-fixture",
        str(head_allowlist),
        "--root",
        str(root),
    ]
    if base_allowlist is not None:
        arguments.extend(["--base-scan-allowlist", str(base_allowlist)])
    if base_ledger_present:
        arguments.append("--base-ledger-present")
    return subprocess.run(
        arguments,
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def assert_synthetic_scan_green(
    root: Path,
    head_allowlist: Path,
    *,
    occurrences: int,
    pairs: int,
    base_allowlist: Path | None = None,
    base_ledger_present: bool = False,
) -> None:
    """合成fixture走査の件数を含む成功を表明する。"""
    result = run_synthetic_scan(
        root,
        head_allowlist,
        base_allowlist=base_allowlist,
        base_ledger_present=base_ledger_present,
    )
    assert result.returncode == 0
    assert result.stdout == (
        "frozen-baselines: synthetic scan fixture OK: "
        f"occurrences={occurrences}; pairs={pairs}\n"
        "frozen-baselines: OK\n"
    )
    assert result.stderr == ""


def assert_synthetic_scan_red(
    root: Path,
    head_allowlist: Path,
    expected_message: str,
    *,
    base_allowlist: Path | None = None,
    base_ledger_present: bool = False,
) -> None:
    """合成fixture走査が期待文言だけでredになることを表明する。"""
    result = run_synthetic_scan(
        root,
        head_allowlist,
        base_allowlist=base_allowlist,
        base_ledger_present=base_ledger_present,
    )
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == f"frozen-baselines: ERROR: {expected_message}\n"


def make_normal_scan_fixture(tmp_path: Path) -> ScanFixture:
    """継承可能なbase/head allow-listと対応ソースを作る。"""
    root = make_scan_root(tmp_path)
    entries = [
        make_scan_entry(
            "scripts/permanent.py",
            PERMANENT_VALUE,
            pending_removal=False,
            reason="恒久的な合成ダミー値",
        ),
        make_scan_entry(
            "tests/pending.py",
            PENDING_VALUE,
            pending_removal=True,
            reason="後続タスクで除去する合成債務",
        ),
    ]
    write_scan_source(root, "scripts/permanent.py", f'VALUE = "{PERMANENT_VALUE}"\n')
    write_scan_source(root, "tests/pending.py", f'VALUE = "{PENDING_VALUE}"\n')
    base_allowlist = root / "base-allowlist.json"
    head_allowlist = root / "head-allowlist.json"
    write_scan_allowlist(base_allowlist, copy.deepcopy(entries))
    write_scan_allowlist(head_allowlist, entries)
    return ScanFixture(
        root=root,
        base_allowlist=base_allowlist,
        head_allowlist=head_allowlist,
        entries=entries,
    )


def assert_normal_scan_baseline_green(fixture: ScanFixture) -> None:
    """通常遷移fixtureの変異前がgreenであることを表明する。"""
    assert_synthetic_scan_green(
        fixture.root,
        fixture.head_allowlist,
        occurrences=2,
        pairs=2,
        base_allowlist=fixture.base_allowlist,
        base_ledger_present=True,
    )
