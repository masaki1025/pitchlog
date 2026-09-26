"""凍結基準CIディスパッチのfail-closed性を固定する負例。"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CHECKER_PATH = REPOSITORY_ROOT / "scripts/check_frozen_baselines.py"


def _run_ci(event_name: str | None) -> subprocess.CompletedProcess[str]:
    """指定したイベント名でCIディスパッチを実行する。"""
    environment = os.environ.copy()
    if event_name is None:
        environment.pop("GITHUB_EVENT_NAME", None)
    else:
        environment["GITHUB_EVENT_NAME"] = event_name
    return subprocess.run(
        [sys.executable, str(CHECKER_PATH), "--ci"],
        cwd=REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.frozen_negative
def test_ci_dispatch_missing_and_unknown_event_names_are_red() -> None:
    """N29: CIイベント名の未設定と未知値をいずれも拒否する。"""
    baseline = _run_ci("push")
    assert baseline.returncode == 0
    assert baseline.stdout == "frozen-baselines: OK\n"
    assert baseline.stderr == ""

    missing = _run_ci(None)
    assert missing.returncode == 1
    assert missing.stdout == ""
    assert missing.stderr == (
        "frozen-baselines: ERROR: "
        "GITHUB_EVENT_NAME が未設定または未対応: <未設定>\n"
    )

    unknown = _run_ci("schedule")
    assert unknown.returncode == 1
    assert unknown.stdout == ""
    assert unknown.stderr == (
        "frozen-baselines: ERROR: "
        "GITHUB_EVENT_NAME が未設定または未対応: 'schedule'\n"
    )
