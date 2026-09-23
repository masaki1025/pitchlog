"""BOOT-SEAL の固定集合、4 拘束、既存封印機構との接続を検査する。"""

from __future__ import annotations

import ast
import copy
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC = ROOT / "backend/src"
ASSET_PATH = ROOT / "backend/domain/boot-seal.json"
RECORD_PATH = ROOT / "backend/domain/boot-seal.sealed.json"
CHECK_SETS_PATH = ROOT / "backend/domain/check-sets.json"
MANIFEST_SCHEMA_PATH = ROOT / "backend/domain/manifest.schema.json"
REQUIREMENTS_PATH = ROOT / "docs/requirements/requirements-pitchlog-2026-07-22.md"
BOOT_SEAL_SOURCE = BACKEND_SRC / "pitchlog/domaincheck/boot_seal.py"
BASE_COMMIT = "50501ebeea70cee77a9ff4ca8e6c0951015d517a"

_SET_CHECK_SCRIPT = """
import json
import sys
from pathlib import Path

from pitchlog.domaincheck.boot_seal import assert_sealed_set_matches
from pitchlog.domaincheck.cli import CheckerExecutionError, CheckerViolation

derived = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
sealed = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
try:
    assert_sealed_set_matches(derived, sealed)
except CheckerViolation as error:
    print(f"不適合: {error}", file=sys.stderr)
    raise SystemExit(1)
except CheckerExecutionError as error:
    print(f"判定不能: {error}", file=sys.stderr)
    raise SystemExit(2)
"""


def _read_json(path: Path) -> dict[str, Any]:
    """JSON object 資産を読み込む。"""
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _write_json(path: Path, value: object) -> None:
    """合成資産を 2 空白インデントで書く。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _environment() -> dict[str, str]:
    """既存テストと同じ backend import 経路を持つ環境を返す。"""
    return {**os.environ, "PYTHONPATH": str(BACKEND_SRC)}


def _run_module(module: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    """Backend のモジュールを独立プロセスで実行する。"""
    return subprocess.run(
        [sys.executable, "-m", module, *arguments],
        cwd=ROOT,
        env=_environment(),
        capture_output=True,
        text=True,
        check=False,
    )


def _derive(root: Path) -> dict[str, Any]:
    """指定ルートから封印集合を独立導出する。"""
    result = _run_module(
        "pitchlog.domaincheck.boot_seal_derive",
        "--root",
        str(root),
    )
    assert result.returncode == 0, result.stderr
    value = json.loads(result.stdout)
    assert isinstance(value, dict)
    return value


def _run_set_check(
    directory: Path,
    derived: dict[str, Any],
    sealed_asset: dict[str, Any],
) -> subprocess.CompletedProcess[str]:
    """2 集合を一時ファイルへ置き、製品の集合差検査を実行する。"""
    derived_path = directory / "derived.json"
    sealed_path = directory / "sealed-asset.json"
    _write_json(derived_path, derived)
    _write_json(sealed_path, sealed_asset)
    return subprocess.run(
        [
            sys.executable,
            "-c",
            _SET_CHECK_SCRIPT,
            str(derived_path),
            str(sealed_path),
        ],
        cwd=ROOT,
        env=_environment(),
        capture_output=True,
        text=True,
        check=False,
    )


def _derive_with_requirements(root: Path, requirements: str) -> dict[str, Any]:
    """要件書だけを差し替えた一時入力から封印集合を導出する。"""
    requirements_path = root / REQUIREMENTS_PATH.relative_to(ROOT)
    requirements_path.parent.mkdir(parents=True, exist_ok=True)
    requirements_path.write_text(requirements, encoding="utf-8")
    _write_json(
        root / CHECK_SETS_PATH.relative_to(ROOT),
        _read_json(CHECK_SETS_PATH),
    )
    _write_json(
        root / MANIFEST_SCHEMA_PATH.relative_to(ROOT),
        _read_json(MANIFEST_SCHEMA_PATH),
    )
    return _derive(root)


def test_measured_and_sealed_sets_have_no_difference(tmp_path: Path) -> None:
    """実測集合と封印対象集合の双方向差が空であることを検査する。"""
    measured = _derive(ROOT)
    sealed_asset = _read_json(ASSET_PATH)

    result = _run_set_check(tmp_path, measured, sealed_asset)

    assert result.returncode == 0, result.stderr
    assert len(measured["elements"]) == 136


def test_constraint_one_rename_preserves_sealed_identifiers(tmp_path: Path) -> None:
    """拘束①として対象名の改名が別の封印要素を生まないことを検査する。"""
    requirements = REQUIREMENTS_PATH.read_text(encoding="utf-8")
    renamed = requirements.replace(
        ": 状況判定・**入力と表示のための座標変換**",
        ": 状況評価・**入力と表示のための座標変換**",
        1,
    )
    assert renamed != requirements
    measured = _derive_with_requirements(tmp_path / "source", renamed)

    result = _run_set_check(
        tmp_path / "check",
        measured,
        _read_json(ASSET_PATH),
    )

    assert result.returncode == 0, result.stderr


def test_constraint_two_addition_and_deletion_are_rejected(tmp_path: Path) -> None:
    """拘束②として封印後の 1 件追加と 1 件削除を個別に拒否する。"""
    measured = _derive(ROOT)
    added = copy.deepcopy(_read_json(ASSET_PATH))
    added["elements"].append(
        {
            "id": "added-after-seal",
            "canonicalKey": "mechanism_absence(added-after-seal)",
        }
    )
    deleted = copy.deepcopy(_read_json(ASSET_PATH))
    deleted["elements"].pop()

    added_result = _run_set_check(tmp_path / "added", measured, added)
    deleted_result = _run_set_check(tmp_path / "deleted", measured, deleted)

    assert added_result.returncode == 1
    assert deleted_result.returncode == 1


def test_constraint_three_collapsed_calculations_are_rejected(
    tmp_path: Path,
) -> None:
    """拘束③として対象別の宣言全体を 13 要素へ潰した集合を拒否する。"""
    measured = _derive(ROOT)
    collapsed = copy.deepcopy(_read_json(ASSET_PATH))
    collapsed["elements"] = [
        {
            "id": f"{target['id']}/all-declarations",
            "canonicalKey": (
                f"declaration_absence({target['id']},all-declarations)"
            ),
        }
        for target in collapsed["derivedInputs"]["targets"]
    ]
    assert len(collapsed["elements"]) == 13

    result = _run_set_check(tmp_path, measured, collapsed)

    assert result.returncode == 1


def test_constraint_four_split_matter_is_rejected(tmp_path: Path) -> None:
    """拘束④として同じ事項を異なる ID の 2 要素へ分けた集合を拒否する。"""
    measured = _derive(ROOT)
    split = copy.deepcopy(_read_json(ASSET_PATH))
    duplicate = copy.deepcopy(split["elements"][0])
    duplicate["id"] = f"{duplicate['id']}-split"
    split["elements"].append(duplicate)

    result = _run_set_check(tmp_path, measured, split)

    assert result.returncode == 1
    assert "拘束④" in result.stderr


def test_correct_set_is_sealed_and_repeated_verification_exits_zero() -> None:
    """正しい集合の既存封印機構による検証が繰り返し exit 0 になることを示す。"""
    record = _read_json(RECORD_PATH)
    before = RECORD_PATH.read_bytes()
    first = _run_module(
        "pitchlog.domaincheck.boot_seal",
        "--root",
        str(ROOT),
    )
    second = _run_module(
        "pitchlog.domaincheck.boot_seal",
        "--root",
        str(ROOT),
    )

    assert record["baseCommitOid"] == BASE_COMMIT
    assert record["assetPath"] == "backend/domain/boot-seal.json"
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert RECORD_PATH.read_bytes() == before


def test_boot_seal_delegates_history_and_digest_checks_to_existing_seal() -> None:
    """固定 SHA と履歴規律を再実装せず seal.main へ委譲することを静的検査する。"""
    tree = ast.parse(BOOT_SEAL_SOURCE.read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "seal"
        and node.func.attr == "main"
    ]
    defined_functions = {
        node.name for node in tree.body if isinstance(node, ast.FunctionDef)
    }

    assert len(calls) == 1
    assert defined_functions.isdisjoint(
        {"_run_git", "_verify_commit_oid", "_assert_history_immutable"}
    )
