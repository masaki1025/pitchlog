"""凍結基準台帳の追記規律と初期移設値を負例で固定する。"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_RELATIVE_PATH = Path("scripts/check_frozen_baselines.py")
CATALOG_RELATIVE_PATH = Path("contracts/authz/frozen-baselines.json")
SCRIPT_PATH = REPOSITORY_ROOT / SCRIPT_RELATIVE_PATH
CATALOG_PATH = REPOSITORY_ROOT / CATALOG_RELATIVE_PATH


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _commit_all(root: Path, subject: str) -> str:
    _git(root, "add", "-A")
    _git(root, "commit", "--quiet", "-m", subject)
    return _git(root, "rev-parse", "HEAD")


def _copy_current_assets(root: Path) -> None:
    for relative_path in (SCRIPT_RELATIVE_PATH, CATALOG_RELATIVE_PATH):
        destination = root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPOSITORY_ROOT / relative_path, destination)


@pytest.fixture
def cloned_repository(tmp_path: Path) -> Iterator[Path]:
    """Git objectを共有する一時cloneへ検査器と台帳の現物を配置する。"""
    originals = {
        SCRIPT_PATH: SCRIPT_PATH.read_bytes(),
        CATALOG_PATH: CATALOG_PATH.read_bytes(),
    }
    root = tmp_path / "repository"
    result = subprocess.run(
        [
            "git",
            "clone",
            "--quiet",
            "--shared",
            str(REPOSITORY_ROOT),
            str(root),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    _copy_current_assets(root)
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "test")

    yield root

    assert {path: path.read_bytes() for path in originals} == originals


def _read_catalog(root: Path) -> dict[str, Any]:
    loaded = json.loads((root / CATALOG_RELATIVE_PATH).read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _write_catalog(root: Path, catalog: dict[str, Any]) -> None:
    (root / CATALOG_RELATIVE_PATH).write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _history(catalog: dict[str, Any], series: str) -> list[dict[str, Any]]:
    baselines = catalog["baselines"]
    assert isinstance(baselines, dict)
    history = baselines[series]
    assert isinstance(history, list)
    assert all(isinstance(record, dict) for record in history)
    return history


def _run_cli(
    root: Path,
    base: str = "origin/develop",
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            SCRIPT_RELATIVE_PATH.as_posix(),
            "--base",
            base,
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )


def _base_without_catalog(root: Path) -> str:
    introductions = _git(
        root,
        "log",
        "--format=%H",
        "--diff-filter=A",
        "--",
        CATALOG_RELATIVE_PATH.as_posix(),
    ).splitlines()
    if introductions:
        return _git(root, "rev-parse", f"{introductions[-1]}^")
    return _git(root, "merge-base", "origin/develop", "HEAD")


def _new_record(root: Path, previous_commit: str) -> dict[str, object]:
    return {
        "commit": _git(root, "rev-parse", "HEAD"),
        "supersedes": previous_commit,
        "approved_by": "山田正輝",
        "approved_at": "2026-09-14",
        "reason": "負例テスト用の追記",
    }


def _replace_constant(
    root: Path,
    relative_path: str,
    constant_name: str,
    replacement: str,
) -> None:
    path = root / relative_path
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(
        rf'^{re.escape(constant_name)}\s*=\s*"([0-9a-f]{{40}})"$',
        re.MULTILINE,
    )
    replaced, count = pattern.subn(f'{constant_name} = "{replacement}"', text)
    assert count == 1
    path.write_text(replaced, encoding="utf-8")


def test_repository_frozen_baselines_are_valid() -> None:
    """実リポジトリの初期台帳がbase側の3定数と一致する。"""
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--root",
            str(REPOSITORY_ROOT),
            "--base",
            "origin/develop",
        ],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "frozen-baselines: OK" in result.stdout


def test_n3_empty_approved_by_is_red(cloned_repository: Path) -> None:
    """N3: 承認者が空の追記をF-3で拒否する。"""
    root = cloned_repository
    catalog = _read_catalog(root)
    history = _history(catalog, "oracle_input")
    record = _new_record(root, history[-1]["commit"])
    record["approved_by"] = ""
    history.append(record)
    _write_catalog(root, catalog)

    result = _run_cli(root)

    assert result.returncode == 1
    assert "F-3" in result.stderr


def test_n5_changed_existing_approval_is_red(cloned_repository: Path) -> None:
    """N5: baseに存在する承認者の書き換えをF-4で拒否する。"""
    root = cloned_repository
    _git(root, "checkout", "--quiet", "--detach", _base_without_catalog(root))
    _copy_current_assets(root)
    base = _commit_all(root, "test: 台帳をbaseへ追加")
    catalog = _read_catalog(root)
    _history(catalog, "oracle_input")[0]["approved_by"] = "別の承認者"
    _write_catalog(root, catalog)
    _commit_all(root, "test: 既存の承認者を書き換え")

    result = _run_cli(root, base)

    assert result.returncode == 1
    assert "F-4" in result.stderr


def test_n6_unlinked_supersedes_is_red(cloned_repository: Path) -> None:
    """N6: 直前commitを指さない追記をF-2で拒否する。"""
    root = cloned_repository
    catalog = _read_catalog(root)
    history = _history(catalog, "oracle_input")
    record = _new_record(root, history[-1]["commit"])
    record["supersedes"] = record["commit"]
    history.append(record)
    _write_catalog(root, catalog)

    result = _run_cli(root)

    assert result.returncode == 1
    assert "F-2" in result.stderr


def test_n9_initial_commit_mismatch_is_red(cloned_repository: Path) -> None:
    """N9: 新設台帳の初期値すり替えをbase側定数とのF-7で拒否する。"""
    root = cloned_repository
    catalog = _read_catalog(root)
    record = _history(catalog, "oracle_input")[0]
    replacement = _git(root, "rev-parse", "HEAD")
    assert replacement != record["commit"]
    record["commit"] = replacement
    _write_catalog(root, catalog)

    result = _run_cli(root, _base_without_catalog(root))

    assert result.returncode == 1
    assert "F-7" in result.stderr


def test_n10_changed_base_source_constant_is_red(cloned_repository: Path) -> None:
    """N10: base側ソースを変えると、その値を読んだF-7が拒否する。"""
    root = cloned_repository
    base_without_catalog = _base_without_catalog(root)
    _git(root, "checkout", "--quiet", "--detach", base_without_catalog)
    _copy_current_assets(root)
    _replace_constant(
        root,
        "scripts/check_authz_catalog.py",
        "ORACLE_INPUT_BASELINE_COMMIT",
        base_without_catalog,
    )
    _git(root, "add", "scripts/check_authz_catalog.py")
    _git(root, "commit", "--quiet", "-m", "test: base側定数を書き換え")
    changed_base = _git(root, "rev-parse", "HEAD")
    _git(root, "add", CATALOG_RELATIVE_PATH.as_posix())
    _git(root, "commit", "--quiet", "-m", "test: 台帳を新設")

    result = _run_cli(root, changed_base)

    assert result.returncode == 1
    assert "F-7" in result.stderr
