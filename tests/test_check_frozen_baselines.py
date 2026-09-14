"""凍結基準台帳の追記規律と初期移設値を負例で固定する。"""

from __future__ import annotations

import hashlib
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
ALLOWLIST_RELATIVE_PATH = Path("scripts/frozen-baseline-scan-allowlist.json")
AUTHZ_CATALOG_RELATIVE_PATH = Path("scripts/check_authz_catalog.py")
CORPUS_RELATIVE_PATH = Path("contracts/authz/requirement-claims.json")
DERIVED_CORPUS_RELATIVE_PATHS = (
    Path("contracts/authz/route-registry.json"),
    Path("contracts/authz/auth-catalog.json"),
    Path("contracts/authz/http-route-matrix.json"),
)
MUTATION_COMPOSITION_RELATIVE_PATH = Path(
    "backend/tests/db/authz/mutation_composition.py"
)
AUTHZ_CATALOG_TEST_RELATIVE_PATH = Path("tests/test_check_authz_catalog.py")
CORE_GUARD_TEST_RELATIVE_PATH = Path("tests/test_core_guard.py")
MIGRATED_BASELINE_CONSTANTS = (
    (AUTHZ_CATALOG_RELATIVE_PATH, "ORACLE_INPUT_BASELINE_COMMIT"),
    (MUTATION_COMPOSITION_RELATIVE_PATH, "STEP2_BASE_REVISION"),
    (AUTHZ_CATALOG_TEST_RELATIVE_PATH, "AUTHZ_STEP2_BASE_REVISION"),
    (CORE_GUARD_TEST_RELATIVE_PATH, "AUTHZ_GUARD_BASE_REVISION"),
)
SCRIPT_PATH = REPOSITORY_ROOT / SCRIPT_RELATIVE_PATH
CATALOG_PATH = REPOSITORY_ROOT / CATALOG_RELATIVE_PATH
ALLOWLIST_PATH = REPOSITORY_ROOT / ALLOWLIST_RELATIVE_PATH
AUTHZ_CATALOG_PATH = REPOSITORY_ROOT / AUTHZ_CATALOG_RELATIVE_PATH


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
    for relative_path in (
        SCRIPT_RELATIVE_PATH,
        CATALOG_RELATIVE_PATH,
        ALLOWLIST_RELATIVE_PATH,
        CORPUS_RELATIVE_PATH,
        *DERIVED_CORPUS_RELATIVE_PATHS,
    ):
        destination = root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPOSITORY_ROOT / relative_path, destination)


def _restore_tracked_assets(root: Path) -> None:
    _git(
        root,
        "restore",
        "--",
        SCRIPT_RELATIVE_PATH.as_posix(),
        CATALOG_RELATIVE_PATH.as_posix(),
        ALLOWLIST_RELATIVE_PATH.as_posix(),
        AUTHZ_CATALOG_RELATIVE_PATH.as_posix(),
        MUTATION_COMPOSITION_RELATIVE_PATH.as_posix(),
        AUTHZ_CATALOG_TEST_RELATIVE_PATH.as_posix(),
        CORE_GUARD_TEST_RELATIVE_PATH.as_posix(),
    )


def _remove_migrated_baseline_constants(root: Path) -> None:
    for relative_path, constant_name in MIGRATED_BASELINE_CONSTANTS:
        path = root / relative_path
        text = path.read_text(encoding="utf-8")
        pattern = re.compile(
            rf'^{re.escape(constant_name)}\s*=\s*"[0-9a-f]{{40}}"\n?',
            re.MULTILINE,
        )
        replaced, count = pattern.subn("", text)
        assert count in {0, 1}
        assert pattern.search(replaced) is None
        path.write_text(replaced, encoding="utf-8")


@pytest.fixture
def cloned_repository(tmp_path: Path) -> Iterator[Path]:
    """Git objectを共有する一時cloneへ検査器と台帳の現物を配置する。"""
    originals = {
        SCRIPT_PATH: SCRIPT_PATH.read_bytes(),
        CATALOG_PATH: CATALOG_PATH.read_bytes(),
        ALLOWLIST_PATH: ALLOWLIST_PATH.read_bytes(),
        AUTHZ_CATALOG_PATH: AUTHZ_CATALOG_PATH.read_bytes(),
        REPOSITORY_ROOT / CORPUS_RELATIVE_PATH: (
            REPOSITORY_ROOT / CORPUS_RELATIVE_PATH
        ).read_bytes(),
        **{
            REPOSITORY_ROOT / path: (REPOSITORY_ROOT / path).read_bytes()
            for path in DERIVED_CORPUS_RELATIVE_PATHS
        },
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
    _remove_migrated_baseline_constants(root)
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


def _read_json_object(root: Path, relative_path: Path) -> dict[str, Any]:
    loaded = json.loads((root / relative_path).read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _write_json_object(
    root: Path,
    relative_path: Path,
    value: dict[str, Any],
) -> None:
    (root / relative_path).write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _canonical_sha256(value: object) -> str:
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _read_allowlist(root: Path) -> dict[str, Any]:
    loaded = json.loads((root / ALLOWLIST_RELATIVE_PATH).read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _write_allowlist(root: Path, allowlist: dict[str, Any]) -> None:
    (root / ALLOWLIST_RELATIVE_PATH).write_text(
        json.dumps(allowlist, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _allowlist_entries(allowlist: dict[str, Any]) -> list[dict[str, Any]]:
    entries = allowlist["entries"]
    assert isinstance(entries, list)
    assert all(isinstance(entry, dict) for entry in entries)
    return entries


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
    """実リポジトリの4系列とcorpus版参照がすべて一致する。"""
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
    assert "scan_occurrences=10" in result.stdout
    assert "scan_pairs=6" in result.stdout
    assert "scan_values=4" in result.stdout
    assert "pending_removal=0" in result.stdout
    catalog = _read_catalog(REPOSITORY_ROOT)
    version_record = _history(catalog, "corpus_versions")[0]
    assert set(version_record) == {
        "version",
        "canonical_sha256",
        "approved_by",
        "approved_at",
        "reason",
    }
    assert "supersedes" not in version_record


def test_g1_corpus_version_must_match_ledger(cloned_repository: Path) -> None:
    """G-1: 母集合の版だけを進めた状態を拒否する。"""
    root = cloned_repository
    corpus = _read_json_object(root, CORPUS_RELATIVE_PATH)
    corpus["corpus_version"] = 2
    _write_json_object(root, CORPUS_RELATIVE_PATH, corpus)

    result = _run_cli(root)

    assert result.returncode == 1
    assert "G-1" in result.stderr


def test_f3_corpus_version_requires_approval(cloned_repository: Path) -> None:
    """F-3: version型にも承認3項目の非空条件を適用する。"""
    root = cloned_repository
    catalog = _read_catalog(root)
    _history(catalog, "corpus_versions")[0]["approved_by"] = ""
    _write_catalog(root, catalog)

    result = _run_cli(root)

    assert result.returncode == 1
    assert "F-3" in result.stderr


def test_g3_corpus_version_history_is_append_only(cloned_repository: Path) -> None:
    """G-3: baseに存在する版記録の書き換えを拒否する。"""
    root = cloned_repository
    base = _commit_all(root, "test: corpus version 基準をbaseへ追加")
    catalog = _read_catalog(root)
    _history(catalog, "corpus_versions")[0]["approved_by"] = "別の承認者"
    _write_catalog(root, catalog)
    _commit_all(root, "test: corpus version の既存承認者を書き換え")

    result = _run_cli(root, base)

    assert result.returncode == 1
    assert "G-3/F-4" in result.stderr


def test_g4_corpus_versions_are_sequential(cloned_repository: Path) -> None:
    """G-4: version 1の次に3を追記する飛び番を拒否する。"""
    root = cloned_repository
    catalog = _read_catalog(root)
    history = _history(catalog, "corpus_versions")
    history.append(
        {
            "version": 3,
            "canonical_sha256": history[-1]["canonical_sha256"],
            "approved_by": "山田正輝",
            "approved_at": "2026-09-15",
            "reason": "G-4 負例テスト用の飛び番",
        }
    )
    _write_catalog(root, catalog)

    result = _run_cli(root)

    assert result.returncode == 1
    assert "G-4" in result.stderr


def test_n7_changed_corpus_without_version_advance_is_red(
    cloned_repository: Path,
) -> None:
    """N7: 版と派生を据え置いた母集合変更をG-2だけで拒否する。"""
    root = cloned_repository
    corpus = _read_json_object(root, CORPUS_RELATIVE_PATH)
    corpus["n7_content_probe"] = True
    _write_json_object(root, CORPUS_RELATIVE_PATH, corpus)

    result = _run_cli(root)

    assert result.returncode == 1
    assert "G-2" in result.stderr
    assert "G-5" not in result.stderr


@pytest.mark.parametrize(
    "lagging_path",
    DERIVED_CORPUS_RELATIVE_PATHS,
    ids=lambda path: path.stem,
)
def test_n8_derived_assets_must_follow_corpus_version(
    cloned_repository: Path,
    lagging_path: Path,
) -> None:
    """N8: G-1/G-2を満たして派生だけ未追随の状態をG-5で拒否する。"""
    root = cloned_repository
    corpus = _read_json_object(root, CORPUS_RELATIVE_PATH)
    corpus["corpus_version"] = 2
    _write_json_object(root, CORPUS_RELATIVE_PATH, corpus)
    for relative_path in DERIVED_CORPUS_RELATIVE_PATHS:
        derived = _read_json_object(root, relative_path)
        if relative_path != lagging_path:
            derived["corpus_version"] = 2
            _write_json_object(root, relative_path, derived)
    catalog = _read_catalog(root)
    history = _history(catalog, "corpus_versions")
    history.append(
        {
            "version": 2,
            "canonical_sha256": _canonical_sha256(corpus),
            "approved_by": "山田正輝",
            "approved_at": "2026-09-15",
            "reason": "N8 負例テスト用の版追記",
        }
    )
    _write_catalog(root, catalog)

    assert history[-1]["version"] == corpus["corpus_version"]
    assert history[-1]["canonical_sha256"] == _canonical_sha256(corpus)
    result = _run_cli(root)

    assert result.returncode == 1
    assert "G-5" in result.stderr
    assert "G-2" not in result.stderr
    assert lagging_path.as_posix() in result.stderr


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
    _restore_tracked_assets(root)
    _git(root, "checkout", "--quiet", "--detach", _base_without_catalog(root))
    _copy_current_assets(root)
    _remove_migrated_baseline_constants(root)
    allowlist = _read_allowlist(root)
    for entry in _allowlist_entries(allowlist):
        entry["pending_removal"] = False
    _write_allowlist(root, allowlist)
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
    _restore_tracked_assets(root)
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
    _remove_migrated_baseline_constants(root)
    _commit_all(root, "test: 台帳を新設")

    result = _run_cli(root, changed_base)

    assert result.returncode == 1
    assert "F-7" in result.stderr


def test_n11_unlisted_source_pair_is_red(cloned_repository: Path) -> None:
    """N11: 未登録パスにある既存OIDを拒否する。"""
    root = cloned_repository
    allowlist = _read_allowlist(root)
    value = _allowlist_entries(allowlist)[0]["value"]
    assert isinstance(value, str)
    relative_path = Path("tests/fixtures/unregistered_frozen_baseline.py")
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'UNLISTED_OID = "{value}"\n', encoding="utf-8")

    result = _run_cli(root)

    assert result.returncode == 1
    assert "allow-list にない" in result.stderr
    assert relative_path.as_posix() in result.stderr


def test_n12_stale_allowlist_pair_is_red(cloned_repository: Path) -> None:
    """N12: ソースに存在しない登録済み組を拒否する。"""
    root = cloned_repository
    allowlist = _read_allowlist(root)
    entries = _allowlist_entries(allowlist)
    value = entries[0]["value"]
    assert isinstance(value, str)
    relative_path = "tests/fixtures/stale_frozen_baseline.py"
    entries.append(
        {
            "path": relative_path,
            "value": value,
            "reason": "N12 の孤立した allow-list 登録",
            "pending_removal": False,
        }
    )
    _write_allowlist(root, allowlist)

    result = _run_cli(root)

    assert result.returncode == 1
    assert "走査で見つからない" in result.stderr
    assert relative_path in result.stderr
