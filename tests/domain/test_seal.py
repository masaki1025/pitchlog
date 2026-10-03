"""NFR-018 (e) BOOT-SEAL の封印機構をプロセス境界で検査する。"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC = ROOT / "backend/src"
SEAL_SOURCE = BACKEND_SRC / "pitchlog/domaincheck/seal.py"


def _git(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    """一時リポジトリで Git を実行する。"""
    return subprocess.run(
        ["git", *arguments],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )


def _write_json(path: Path, value: object) -> None:
    """一時 fixture を読みやすい JSON で書く。"""
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _asset() -> dict[str, Any]:
    """製品資産に依存しない合成封印対象を返す。"""
    return {
        "schemaVersion": 1,
        "targets": [
            {"id": "synthetic-alpha", "enabled": True},
            {"id": "synthetic-beta", "enabled": False},
        ],
    }


def _make_repository(tmp_path: Path) -> tuple[Path, str]:
    """固定比較元を 1 件持つ小さな Git リポジトリを作る。"""
    root = tmp_path / "repository"
    root.mkdir()
    _git(root, "init", "--quiet")
    _git(root, "config", "user.email", "seal-test@example.invalid")
    _git(root, "config", "user.name", "Seal Test")
    _write_json(root / "asset.json", _asset())
    _git(root, "add", "asset.json")
    _git(root, "commit", "--quiet", "-m", "固定比較元")
    base_commit = _git(root, "rev-parse", "HEAD").stdout.strip()
    assert len(base_commit) == 40
    return root, base_commit


def _run_seal(
    root: Path,
    base_commit: str,
    *modes: str,
    ci: str | None = None,
    path: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """封印 CLI を独立プロセスで実行する。"""
    command = [
        sys.executable,
        "-m",
        "pitchlog.domaincheck.seal",
        "--root",
        str(root),
        "--asset",
        "asset.json",
        "--seal",
        "seal.json",
        "--base-commit",
        base_commit,
        *modes,
    ]
    environment = {
        "PYTHONPATH": str(BACKEND_SRC),
        "PATH": path if path is not None else os.environ["PATH"],
    }
    if ci is not None:
        environment["CI"] = ci
    return subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def _canonical_digest(value: object) -> str:
    """テスト側で独立に canonical SHA-256 を計算する。"""
    serialized = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    digest = hashlib.sha256(f"{serialized}\n".encode()).hexdigest()
    return f"sha256:{digest}"


def _reseal_successfully(root: Path, base_commit: str) -> bytes:
    """正当な再封印を行い、書き込まれた bytes を返す。"""
    result = _run_seal(root, base_commit, "--reseal")
    assert result.returncode == 0, result.stderr
    return (root / "seal.json").read_bytes()


def test_reseal_is_rejected_when_ci_variable_exists(tmp_path: Path) -> None:
    root, base_commit = _make_repository(tmp_path)

    result = _run_seal(root, base_commit, "--reseal", ci="true")

    assert result.returncode == 1
    assert "CI 環境" in result.stderr
    assert not (root / "seal.json").exists()


def test_reseal_and_verify_flags_are_mutually_exclusive(tmp_path: Path) -> None:
    root, base_commit = _make_repository(tmp_path)

    result = _run_seal(root, base_commit, "--verify", "--reseal")

    assert result.returncode == 2
    assert "判定不能" in result.stderr
    assert not (root / "seal.json").exists()


def test_missing_version_control_tool_exits_two_without_traceback(
    tmp_path: Path,
) -> None:
    root, base_commit = _make_repository(tmp_path)
    seal_before = _reseal_successfully(root, base_commit)
    empty_path = tmp_path / "empty-path"
    empty_path.mkdir()

    result = _run_seal(root, base_commit, path=str(empty_path))

    assert result.returncode == 2
    assert "版管理ツール" in result.stderr
    assert "Traceback" not in result.stderr
    assert (root / "seal.json").read_bytes() == seal_before


def test_normal_validation_does_not_silently_reseal(tmp_path: Path) -> None:
    root, base_commit = _make_repository(tmp_path)
    seal_before = _reseal_successfully(root, base_commit)
    changed = _asset()
    changed["targets"][0]["enabled"] = False
    _write_json(root / "asset.json", changed)

    result = _run_seal(root, base_commit)

    assert result.returncode == 1
    assert "blob digest" in result.stderr
    assert (root / "seal.json").read_bytes() == seal_before


def test_executable_git_paths_use_only_closed_history_commands() -> None:
    source = SEAL_SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    subprocess_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "subprocess"
    ]

    assert len(subprocess_calls) == 1
    call = subprocess_calls[0]
    assert isinstance(call.func, ast.Attribute)
    assert call.func.attr == "run"
    assert call.args and isinstance(call.args[0], ast.List)
    command = call.args[0].elts
    assert len(command) == 2
    assert isinstance(command[0], ast.Constant) and command[0].value == "git"
    assert isinstance(command[1], ast.Starred)

    git_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_run_git"
    ]
    subcommands: list[str] = []
    for git_call in git_calls:
        assert len(git_call.args) >= 2
        subcommand = git_call.args[1]
        assert isinstance(subcommand, ast.Constant)
        assert isinstance(subcommand.value, str)
        subcommands.append(subcommand.value)
    assert set(subcommands) == {"rev-parse", "log", "show"}


@pytest.mark.parametrize("mode", [(), ("--reseal",)])
def test_changed_fixed_sha_fails_without_writing(
    tmp_path: Path,
    mode: tuple[str, ...],
) -> None:
    root, base_commit = _make_repository(tmp_path)
    _reseal_successfully(root, base_commit)
    _git(root, "add", "seal.json")
    _git(root, "commit", "--quiet", "-m", "封印レコード")
    other_commit = _git(root, "rev-parse", "HEAD").stdout.strip()
    seal = json.loads((root / "seal.json").read_text(encoding="utf-8"))
    seal["baseCommitOid"] = other_commit
    _write_json(root / "seal.json", seal)
    changed_bytes = (root / "seal.json").read_bytes()

    assert _git(root, "diff", "--name-only").stdout.splitlines() == ["seal.json"]

    result = _run_seal(root, other_commit, *mode)

    assert result.returncode == 1
    assert "BOOT-SEAL-IMMUTABLE" in result.stderr
    assert (root / "seal.json").read_bytes() == changed_bytes


def test_valid_reseal_updates_seal_and_subsequent_verification_passes(
    tmp_path: Path,
) -> None:
    root, base_commit = _make_repository(tmp_path)

    reseal_result = _run_seal(root, base_commit, "--reseal")
    seal = json.loads((root / "seal.json").read_text(encoding="utf-8"))
    verify_result = _run_seal(root, base_commit)

    assert reseal_result.returncode == 0, reseal_result.stderr
    assert "再封印した" in reseal_result.stdout
    assert seal == {
        "schemaVersion": 1,
        "assetPath": "asset.json",
        "baseCommitOid": base_commit,
        "blobDigest": _canonical_digest(_asset()),
    }
    assert verify_result.returncode == 0, verify_result.stderr


def test_key_order_only_change_keeps_canonical_blob_digest(tmp_path: Path) -> None:
    root, base_commit = _make_repository(tmp_path)
    seal_before = _reseal_successfully(root, base_commit)
    asset = _asset()
    reordered = {
        "targets": [
            {"enabled": row["enabled"], "id": row["id"]}
            for row in asset["targets"]
        ],
        "schemaVersion": asset["schemaVersion"],
    }
    _write_json(root / "asset.json", reordered)

    result = _run_seal(root, base_commit)

    assert result.returncode == 0, result.stderr
    assert (root / "seal.json").read_bytes() == seal_before


def test_reseal_self_check_rejects_broken_input_before_writing(
    tmp_path: Path,
) -> None:
    root, base_commit = _make_repository(tmp_path)
    seal_before = _reseal_successfully(root, base_commit)
    (root / "asset.json").write_text("{", encoding="utf-8")

    result = _run_seal(root, base_commit, "--reseal")

    assert result.returncode == 2
    assert "JSON 資産を読めない" in result.stderr
    assert (root / "seal.json").read_bytes() == seal_before
