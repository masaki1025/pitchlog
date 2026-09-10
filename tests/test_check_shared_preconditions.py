"""共有関数の前提条件資産に対する静的検査の負例を検証する。"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY_ROOT / "scripts" / "check_shared_preconditions.py"
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
checker = _load_module("check_shared_preconditions_under_test", SCRIPT)

ASSET_PATH = REPOSITORY_ROOT / checker.ASSET_PATH
ROUTE_REGISTRY_PATH = REPOSITORY_ROOT / checker.ROUTE_REGISTRY_PATH


@pytest.fixture
def copied_repository(tmp_path: Path) -> Iterator[Path]:
    """検査に必要な実ファイルだけを一時リポジトリへ複製する。"""
    root = tmp_path / "repository"
    relative_paths = {
        checker.ASSET_PATH,
        checker.ROUTE_REGISTRY_PATH,
        *checker.SOURCE_PATH_BY_ROLE.values(),
    }
    for relative_path in relative_paths:
        destination = root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPOSITORY_ROOT / relative_path, destination)
    yield root


def _read_asset(root: Path) -> dict[str, Any]:
    """一時コピーの共有前提資産を読む。"""
    raw = json.loads((root / checker.ASSET_PATH).read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return raw


def _write_asset(root: Path, asset: dict[str, Any]) -> None:
    """一時コピーの共有前提資産を書く。"""
    (root / checker.ASSET_PATH).write_text(
        json.dumps(asset, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _run_cli(root: Path) -> subprocess.CompletedProcess[str]:
    """指定ルートに対して検査CLIを実行する。"""
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root)],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )


def _preconditions(asset: dict[str, Any]) -> list[dict[str, Any]]:
    """資産の前提条件行を型確認して返す。"""
    preconditions = asset["preconditions"]
    assert isinstance(preconditions, list)
    assert all(isinstance(item, dict) for item in preconditions)
    return preconditions


def _source_document(asset: dict[str, Any], role: str) -> dict[str, Any]:
    """指定した役割の出典文書宣言を返す。"""
    documents = asset["source_documents"]
    assert isinstance(documents, list)
    document = next(item for item in documents if item["document_role"] == role)
    assert isinstance(document, dict)
    return document


def test_repository_shared_preconditions_are_valid() -> None:
    """リポジトリ実物の共有前提資産が正常に照合できる。"""
    result = _run_cli(REPOSITORY_ROOT)

    assert result.returncode == 0, result.stderr
    assert "authz-shared-preconditions: OK" in result.stdout


def test_changed_verbatim_text_is_red(copied_repository: Path) -> None:
    """逐語本文を1文字変えると要件書本文との突合でredになる。"""
    root = copied_repository
    asset = _read_asset(root)
    entry = _preconditions(asset)[0]
    entry["verbatim_text"] += "改"
    _write_asset(root, asset)

    result = _run_cli(root)

    assert result.returncode == 1
    assert "要件書本文と逐語不一致" in result.stderr


@pytest.mark.parametrize("document_role", ["normative_source", "mapping_target"])
def test_changed_source_digest_is_red(
    copied_repository: Path,
    document_role: str,
) -> None:
    """各出典digestを書き換えると取り直しを促してredになる。"""
    root = copied_repository
    asset = _read_asset(root)
    document = _source_document(asset, document_role)
    current_digest = document["git_blob_digest"]
    assert isinstance(current_digest, str)
    document["git_blob_digest"] = "0" * len(current_digest)
    _write_asset(root, asset)

    result = _run_cli(root)

    assert result.returncode == 1
    assert "git_blob_digestが現ファイルと不一致" in result.stderr
    assert "digest の取り直しが必要" in result.stderr


def test_registry_id_reuse_is_red(copied_repository: Path) -> None:
    """共有側IDを管理操作用registry IDと同名にするとredになる。"""
    root = copied_repository
    asset = _read_asset(root)
    registry = json.loads(
        (root / checker.ROUTE_REGISTRY_PATH).read_text(encoding="utf-8")
    )
    registry_id = registry["enums"]["precondition_ids"][0]
    _preconditions(asset)[0]["precondition_id"] = registry_id
    _write_asset(root, asset)

    result = _run_cli(root)

    assert result.returncode == 1
    assert "管理操作用IDと交差" in result.stderr


@pytest.mark.parametrize(
    "exception_indexes",
    [pytest.param((), id="zero"), pytest.param((0, 1), id="two")],
)
def test_invalid_exception_row_count_is_red(
    copied_repository: Path,
    exception_indexes: tuple[int, ...],
) -> None:
    """例外を0行または2行にすると閉じた行種別検査でredになる。"""
    root = copied_repository
    asset = _read_asset(root)
    preconditions = _preconditions(asset)
    for entry in preconditions:
        entry["kind"] = "通常"
    for index in exception_indexes:
        preconditions[index]["kind"] = "例外"
    _write_asset(root, asset)

    result = _run_cli(root)

    assert result.returncode == 1
    assert "kindが「例外」の行数が不正" in result.stderr


def test_unknown_equivalent_registry_id_is_red(copied_repository: Path) -> None:
    """対応先に実在しない管理操作用IDを書くとredになる。"""
    root = copied_repository
    asset = _read_asset(root)
    _preconditions(asset)[0]["equivalent_registry_precondition_id"] = (
        "missing_registry_precondition"
    )
    _write_asset(root, asset)

    result = _run_cli(root)

    assert result.returncode == 1
    assert "実在しないroute-registry IDを参照" in result.stderr


def test_malformed_asset_is_input_error(copied_repository: Path) -> None:
    """JSONとして読めない資産は入力不正の終了コード2になる。"""
    root = copied_repository
    (root / checker.ASSET_PATH).write_text("{", encoding="utf-8")

    result = _run_cli(root)

    assert result.returncode == 2
    assert "入力不正" in result.stderr
