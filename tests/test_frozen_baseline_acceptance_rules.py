"""凍結基準の受理対象外ポリシーに対する正常系を検証する。"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = REPOSITORY_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_ROOT))
try:
    checker = importlib.import_module("check_frozen_baselines")
finally:
    sys.path.pop(0)


def test_non_develop_event_skips_only_acceptance_transition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """健全な非develop向けPRは受理遷移だけを対象外にする。"""
    head_sha = checker._resolve_commit(REPOSITORY_ROOT, "HEAD", "HEAD")
    event_path = tmp_path / "event.json"
    event_path.write_text(
        json.dumps(
            {
                "repository": {"full_name": "masaki1025/pitchlog"},
                "pull_request": {
                    "number": 73,
                    "base": {"ref": "release", "sha": head_sha},
                    "head": {"sha": head_sha},
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))

    messages = checker.check_acceptance(
        REPOSITORY_ROOT,
        REPOSITORY_ROOT / "contracts/authz/frozen-baselines.json",
    )

    assert messages == (
        "frozen-baselines: acceptance not evaluated: "
        "pull_request.base.ref='release' は develop でない",
    )
