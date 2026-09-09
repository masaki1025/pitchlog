"""認可関数 body の manifest と静的照合の負例を検証する。"""

from __future__ import annotations

import importlib.util
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
SCRIPT = REPOSITORY_ROOT / "scripts" / "check_authz_function_bodies.py"
CATALOG_SCRIPT = REPOSITORY_ROOT / "scripts" / "check_authz_catalog.py"


def _load_module(name: str, path: Path) -> Any:
    """テスト対象と依存先をsys.path変更なしでモジュールとして読む。"""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_load_module("check_authz_catalog", CATALOG_SCRIPT)
checker = _load_module("check_authz_function_bodies_under_test", SCRIPT)


BODY_DIRECTORY = REPOSITORY_ROOT / checker.BODY_DIRECTORY
MANIFEST_PATH = REPOSITORY_ROOT / checker.MANIFEST_PATH
DDL_ELEMENTS_PATH = REPOSITORY_ROOT / checker.DDL_ELEMENTS_PATH
AUTHORIZED_SHARED_ROWS_PATH = (
    "contracts/authz/function-bodies/functions/authorized_shared_rows.sql"
)


def _asset_snapshot() -> dict[str, bytes]:
    """本物のbody資産とDDL要素資産を生バイトで採取する。"""
    paths = [DDL_ELEMENTS_PATH]
    paths.extend(path for path in BODY_DIRECTORY.rglob("*") if path.is_file())
    return {
        path.relative_to(REPOSITORY_ROOT).as_posix(): path.read_bytes()
        for path in sorted(paths)
    }


@pytest.fixture
def copied_repository(tmp_path: Path) -> Iterator[Path]:
    """Git objectを共有する一時コピーを作り、本物の資産が不変か事後検査する。"""
    original_assets = _asset_snapshot()
    root = tmp_path / "repository"
    result = subprocess.run(
        [
            "git",
            "clone",
            "--quiet",
            "--shared",
            "--no-checkout",
            str(REPOSITORY_ROOT),
            str(root),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    shutil.copytree(BODY_DIRECTORY, root / checker.BODY_DIRECTORY)
    shutil.copy2(DDL_ELEMENTS_PATH, root / checker.DDL_ELEMENTS_PATH)

    yield root

    assert _asset_snapshot() == original_assets


def _read_manifest(root: Path) -> dict[str, Any]:
    """一時コピーのmanifestを読む。"""
    raw = json.loads((root / checker.MANIFEST_PATH).read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return raw


def _write_manifest(root: Path, manifest: dict[str, Any]) -> None:
    """一時コピーのmanifestを書く。"""
    (root / checker.MANIFEST_PATH).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _run_cli(root: Path) -> subprocess.CompletedProcess[str]:
    """一時コピーに対して検査CLIを実行する。"""
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root)],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )


def _body_entry(manifest: dict[str, Any], path_text: str) -> dict[str, Any]:
    """指定パスのmanifest entryを返す。"""
    entries = manifest["entries"]
    assert isinstance(entries, list)
    entry = next(item for item in entries if item["path"] == path_text)
    assert isinstance(entry, dict)
    return entry


def _refresh_current_digest(root: Path, entry: dict[str, Any]) -> None:
    """一時変異したbodyの現物digestだけをmanifestへ反映する。"""
    path = root / entry["path"]
    entry["blob_digest"] = checker.git_blob_digest(path.read_bytes())


def test_repository_function_body_manifest_is_valid() -> None:
    """リポジトリ上のmanifestとbodyが正常に照合できる。"""
    result = _run_cli(REPOSITORY_ROOT)

    assert result.returncode == 0, result.stderr
    assert "authz-function-bodies: OK" in result.stdout


def test_changed_body_with_refreshed_current_digest_is_red_at_source_commit(
    copied_repository: Path,
) -> None:
    """現物digestを追随させてもsource commit側のblob不一致でredになる。"""
    root = copied_repository
    manifest = _read_manifest(root)
    entry = _body_entry(manifest, AUTHORIZED_SHARED_ROWS_PATH)
    body_path = root / entry["path"]
    body_path.write_bytes(body_path.read_bytes() + b"\n-- negative mutation\n")
    _refresh_current_digest(root, entry)
    _write_manifest(root, manifest)

    result = _run_cli(root)

    assert result.returncode == 1
    assert "source_commit上のblob digestが不一致" in result.stderr
    assert "現bodyのblob digestが不一致" not in result.stderr


def test_unresolvable_body_paths_at_another_source_commit_are_red(
    copied_repository: Path,
) -> None:
    """body導入前の別commitでは対象pathを解決できずredになる。"""
    root = copied_repository
    manifest = _read_manifest(root)
    source_commit = manifest["source_commit"]
    result = subprocess.run(
        ["git", "rev-parse", f"{source_commit}^"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    manifest["source_commit"] = result.stdout.strip()
    _write_manifest(root, manifest)

    check_result = _run_cli(root)

    assert check_result.returncode == 1
    assert "source_commit上のblobを解決できない" in check_result.stderr


def test_removed_manifest_entry_is_red_by_body_exact_set(
    copied_repository: Path,
) -> None:
    """bodyを照合対象から1件外すと現ファイル被覆のexact-setでredになる。"""
    root = copied_repository
    manifest = _read_manifest(root)
    entries = manifest["entries"]
    assert isinstance(entries, list) and entries
    removed = entries.pop()
    _write_manifest(root, manifest)

    result = _run_cli(root)

    assert result.returncode == 1
    assert "bodyファイル被覆がexact-set不一致" in result.stderr
    assert removed["path"] in result.stderr


def test_manifest_cannot_include_itself(copied_repository: Path) -> None:
    """manifest自身をentryへ追加すると自己digest禁止でredになる。"""
    root = copied_repository
    manifest = _read_manifest(root)
    entries = manifest["entries"]
    assert isinstance(entries, list) and entries
    first_entry = entries[0]
    entries.append(
        {
            "path": checker.MANIFEST_PATH.as_posix(),
            "blob_digest": "0" * len(first_entry["blob_digest"]),
            "element_type": first_entry["element_type"],
            "element_id": first_entry["element_id"],
        }
    )
    _write_manifest(root, manifest)

    result = _run_cli(root)

    assert result.returncode == 1
    assert "manifest.json自身をentriesに含めている" in result.stderr


def test_duplicate_decision_id_is_red(copied_repository: Path) -> None:
    """判定IDを重複させると一意性検査でredになる。"""
    root = copied_repository
    manifest = _read_manifest(root)
    entry = _body_entry(manifest, AUTHORIZED_SHARED_ROWS_PATH)
    body_path = root / entry["path"]
    text = body_path.read_text(encoding="utf-8")
    decision_ids = re.findall(r"-- DECISION: ([A-Z0-9_-]+)", text)
    assert len(decision_ids) >= 2
    text = text.replace(
        f"-- DECISION: {decision_ids[1]}",
        f"-- DECISION: {decision_ids[0]}",
        1,
    )
    body_path.write_text(text, encoding="utf-8")
    _refresh_current_digest(root, entry)
    _write_manifest(root, manifest)

    result = _run_cli(root)

    assert result.returncode == 1
    assert f"DECISION IDが重複: {decision_ids[0]}" in result.stderr


def test_invalid_decision_id_character_is_red(copied_repository: Path) -> None:
    """判定IDへ規約外文字を入れると構文検査でredになる。"""
    root = copied_repository
    manifest = _read_manifest(root)
    entry = _body_entry(manifest, AUTHORIZED_SHARED_ROWS_PATH)
    body_path = root / entry["path"]
    text = body_path.read_text(encoding="utf-8")
    match = re.search(r"-- DECISION: ([A-Z0-9_-]+)", text)
    assert match is not None
    text = text.replace(match.group(0), f"{match.group(0)}!", 1)
    body_path.write_text(text, encoding="utf-8")
    _refresh_current_digest(root, entry)
    _write_manifest(root, manifest)

    result = _run_cli(root)

    assert result.returncode == 1
    assert "DECISION注記の構文が不正" in result.stderr
