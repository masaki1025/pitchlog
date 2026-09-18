"""design.md §12-3 の停止ゲートをプロセス境界で検査する。"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC = ROOT / "backend/src"
REGISTRY_PATH = ROOT / "backend/domain/review-triggers.json"


@pytest.fixture(scope="module")
def registry() -> dict[str, Any]:
    """未評価の見直しトリガー資産を読み込む。"""
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def _write_registry(tmp_path: Path, asset: dict[str, Any]) -> Path:
    path = tmp_path / "review-triggers.json"
    path.write_text(json.dumps(asset, ensure_ascii=False), encoding="utf-8")
    return path


def _all_evaluated(registry: dict[str, Any]) -> dict[str, Any]:
    asset = copy.deepcopy(registry)
    for trigger in asset["triggers"]:
        trigger["evaluation"] = {"fired": False}
    return asset


def _run_gate(registry_path: Path, step: str | int | None) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        "-m",
        "pitchlog.domaincheck.stopgate",
        "--registry",
        str(registry_path),
    ]
    if step is not None:
        command.extend(["--step", str(step)])
    return subprocess.run(
        command,
        cwd=ROOT,
        env={"PYTHONPATH": str(BACKEND_SRC)},
        capture_output=True,
        text=True,
        check=False,
    )


def test_fired_record_exits_two(
    tmp_path: Path, registry: dict[str, Any]
) -> None:
    asset = _all_evaluated(registry)
    asset["triggers"][0]["evaluation"] = {"fired": True}
    result = _run_gate(_write_registry(tmp_path, asset), step=56)

    assert result.returncode == 2


def test_unevaluated_before_deadline_exits_zero(
    tmp_path: Path, registry: dict[str, Any]
) -> None:
    asset = _all_evaluated(registry)
    trigger_five = next(trigger for trigger in asset["triggers"] if trigger["id"] == 5)
    trigger_five["evaluation"] = None
    result = _run_gate(_write_registry(tmp_path, asset), step=47)

    assert result.returncode == 0


def test_unevaluated_at_deadline_exits_zero(
    tmp_path: Path, registry: dict[str, Any]
) -> None:
    asset = _all_evaluated(registry)
    trigger_five = next(trigger for trigger in asset["triggers"] if trigger["id"] == 5)
    trigger_five["evaluation"] = None
    result = _run_gate(_write_registry(tmp_path, asset), step=48)

    assert result.returncode == 0


def test_overdue_unevaluated_trigger_exits_two(
    tmp_path: Path, registry: dict[str, Any]
) -> None:
    asset = _all_evaluated(registry)
    trigger_five = next(trigger for trigger in asset["triggers"] if trigger["id"] == 5)
    trigger_five["evaluation"] = None
    result = _run_gate(_write_registry(tmp_path, asset), step=49)

    assert result.returncode == 2


def test_no_firing_or_overdue_evaluation_exits_zero(
    tmp_path: Path, registry: dict[str, Any]
) -> None:
    asset = _all_evaluated(registry)
    result = _run_gate(_write_registry(tmp_path, asset), step=56)

    assert result.returncode == 0


def test_invalid_registry_schema_exits_one(
    tmp_path: Path, registry: dict[str, Any]
) -> None:
    asset = _all_evaluated(registry)
    asset["triggers"][0]["evaluation"] = {"fired": "yes"}
    result = _run_gate(_write_registry(tmp_path, asset), step=56)

    assert result.returncode == 1


def test_malformed_registry_json_exits_one(tmp_path: Path) -> None:
    path = tmp_path / "review-triggers.json"
    path.write_text("{", encoding="utf-8")
    result = _run_gate(path, step=1)

    assert result.returncode == 1


def test_missing_registry_exits_one(tmp_path: Path) -> None:
    result = _run_gate(tmp_path / "missing-review-triggers.json", step=1)

    assert result.returncode == 1


def test_missing_step_exits_one(tmp_path: Path, registry: dict[str, Any]) -> None:
    path = _write_registry(tmp_path, registry)
    result = _run_gate(path, step=None)

    assert result.returncode == 1


@pytest.mark.parametrize("invalid_step", ["not-a-step", "0", "-1"])
def test_invalid_step_exits_one(
    tmp_path: Path, registry: dict[str, Any], invalid_step: str
) -> None:
    path = _write_registry(tmp_path, registry)
    result = _run_gate(path, step=invalid_step)

    assert result.returncode == 1
