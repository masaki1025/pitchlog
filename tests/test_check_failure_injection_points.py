"""失敗注入点資産に対する静的検査の負例を検証する。"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY_ROOT / "scripts" / "check_failure_injection_points.py"
CATALOG_SCRIPT = REPOSITORY_ROOT / "scripts" / "check_authz_catalog.py"


def _load_module(name: str, path: Path) -> Any:
    """テスト対象と依存先を sys.path 変更なしでモジュールとして読む。"""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_load_module("check_authz_catalog", CATALOG_SCRIPT)
checker = _load_module("check_failure_injection_points_under_test", SCRIPT)


@pytest.fixture
def copied_repository(tmp_path: Path) -> Iterator[Path]:
    """検査に必要な実ファイルだけを一時リポジトリへ複製する。"""
    root = tmp_path / "repository"
    for relative_path in (checker.ASSET_PATH, checker.DDL_ELEMENTS_PATH):
        destination = root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPOSITORY_ROOT / relative_path, destination)
    yield root


def _read_asset(root: Path) -> dict[str, Any]:
    """一時コピーの失敗注入点資産を読む。"""
    raw = json.loads((root / checker.ASSET_PATH).read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return raw


def _write_asset(root: Path, asset: dict[str, Any]) -> None:
    """一時コピーの失敗注入点資産を書く。"""
    (root / checker.ASSET_PATH).write_text(
        json.dumps(asset, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _run_cli(root: Path) -> subprocess.CompletedProcess[str]:
    """指定ルートに対して検査 CLI を実行する。"""
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root)],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )


def _points(asset: dict[str, Any]) -> list[dict[str, Any]]:
    """資産の失敗注入点行を型確認して返す。"""
    points = asset["injection_points"]
    assert isinstance(points, list)
    assert all(isinstance(point, dict) for point in points)
    return points


def _mutate_remove_last(points: list[dict[str, Any]]) -> None:
    """末尾の注入点を除く。"""
    points.pop()


def _mutate_append_duplicate(points: list[dict[str, Any]]) -> None:
    """既存の注入点を追加して行数を増やす。"""
    points.append(dict(points[-1]))


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(_mutate_remove_last, id="four"),
        pytest.param(_mutate_append_duplicate, id="six"),
    ],
)
def test_invalid_injection_point_count_is_red(
    copied_repository: Path,
    mutate: Callable[[list[dict[str, Any]]], None],
) -> None:
    """閉じた ID 集合より 1 行少なくても多くても red になる。"""
    asset = _read_asset(copied_repository)
    mutate(_points(asset))
    _write_asset(copied_repository, asset)

    result = _run_cli(copied_repository)

    assert result.returncode == 1
    assert "injection_points件数が閉じたID集合と不一致" in result.stderr


def test_duplicate_checkpoint_id_is_red(copied_repository: Path) -> None:
    """2 行が同じ checkpoint ID を使うと red になる。"""
    asset = _read_asset(copied_repository)
    points = _points(asset)
    points[1]["checkpoint_id"] = points[0]["checkpoint_id"]
    _write_asset(copied_repository, asset)

    result = _run_cli(copied_repository)

    assert result.returncode == 1
    assert "checkpoint_idが相互に異ならない" in result.stderr


def test_unknown_operation_kind_is_red(copied_repository: Path) -> None:
    """Ordered steps にない operation kind は red になる。"""
    asset = _read_asset(copied_repository)
    _points(asset)[0]["operation_kind"] = "missing_operation_kind"
    _write_asset(copied_repository, asset)

    result = _run_cli(copied_repository)

    assert result.returncode == 1
    assert "operation_kindがordered_stepsのstep_idと不整合" in result.stderr


def test_changed_position_tuple_is_red(copied_repository: Path) -> None:
    """要素内コマンド序数を変えると所定位置との組照合で red になる。"""
    asset = _read_asset(copied_repository)
    rule = _points(asset)[1]["position_rule"]
    assert isinstance(rule, dict)
    rule["command_ordinal_within_element"] = 1
    _write_asset(copied_repository, asset)

    result = _run_cli(copied_repository)

    assert result.returncode == 1
    assert "(operation_kind, element_type, position_rule)が所定位置と不一致" in result.stderr


def test_function_point_before_public_revoke_without_rollback_is_red(
    copied_repository: Path,
) -> None:
    """関数作成と PUBLIC REVOKE の間を確定境界にすると red になる。"""
    asset = _read_asset(copied_repository)
    function_point = next(
        point
        for point in _points(asset)
        if point["injection_point_id"]
        == "FAILURE-INJECTION:AFTER-FUNCTION-BODY-REPLACEMENT"
    )
    rule = function_point["position_rule"]
    assert isinstance(rule, dict)
    rule["failure_boundary"] = "before_public_revoke"
    _write_asset(copied_repository, asset)

    result = _run_cli(copied_repository)

    assert result.returncode == 1
    assert "D-7違反" in result.stderr


def test_empty_comparison_targets_is_red(copied_repository: Path) -> None:
    """比較対象が空なら red になる。"""
    asset = _read_asset(copied_repository)
    _points(asset)[0]["comparison_targets"] = []
    _write_asset(copied_repository, asset)

    result = _run_cli(copied_repository)

    assert result.returncode == 1
    assert "comparison_targetsが空" in result.stderr


def test_unknown_comparison_target_is_red(copied_repository: Path) -> None:
    """閉じた比較対象語彙にない値を加えると red になる。"""
    asset = _read_asset(copied_repository)
    targets = _points(asset)[0]["comparison_targets"]
    assert isinstance(targets, list)
    targets.append("unknown_comparison_surface")
    _write_asset(copied_repository, asset)

    result = _run_cli(copied_repository)

    assert result.returncode == 1
    assert "comparison_targetsが閉じた語彙の外" in result.stderr


def test_changed_source_digest_is_red(copied_repository: Path) -> None:
    """DDL 要素資産の digest を書き換えると取り直しを促して red になる。"""
    asset = _read_asset(copied_repository)
    source_asset = asset["source_asset"]
    assert isinstance(source_asset, dict)
    digest = source_asset["git_blob_digest"]
    assert isinstance(digest, str)
    source_asset["git_blob_digest"] = "0" * len(digest)
    _write_asset(copied_repository, asset)

    result = _run_cli(copied_repository)

    assert result.returncode == 1
    assert "git_blob_digestが現ファイルと不一致" in result.stderr
    assert "digest の取り直しが必要" in result.stderr


def test_malformed_asset_is_input_error(copied_repository: Path) -> None:
    """JSON として読めない資産は入力不正の終了コード 2 になる。"""
    (copied_repository / checker.ASSET_PATH).write_text("{", encoding="utf-8")

    result = _run_cli(copied_repository)

    assert result.returncode == 2
    assert "入力不正" in result.stderr


def test_repository_failure_injection_points_are_valid() -> None:
    """リポジトリ実物の失敗注入点資産が正常に照合できる。"""
    result = _run_cli(REPOSITORY_ROOT)

    assert result.returncode == 0, result.stderr
    assert "authz-failure-injection-points: OK" in result.stdout
