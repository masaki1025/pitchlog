"""tenant 生成モジュールの再導出スクリプトを検査する。"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY_ROOT / "scripts" / "rederive_tenant_generated_modules.py"


def _load_script():
    """検査対象のスクリプトをファイルから読み込む。

    Returns:
        読み込み済みモジュール。
    """
    spec = importlib.util.spec_from_file_location(SCRIPT.stem, SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


rederive = _load_script()


def _copy_inputs(tmp_path: Path, spec: rederive.GeneratedModule) -> Path:
    """資産とモジュールを一時リポジトリへ複製する。

    Args:
        tmp_path: 複製先のルート。
        spec: 対象の生成モジュール定義。

    Returns:
        複製先のリポジトリルート。
    """
    for relative in (spec.asset, spec.module):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPOSITORY_ROOT / relative, target)
    return tmp_path


@pytest.mark.parametrize("spec", rederive.GENERATED_MODULES, ids=lambda s: s.module)
def test_rederive_is_idempotent(tmp_path: Path, spec: rederive.GeneratedModule) -> None:
    """実資産から描画した結果が現行モジュールと一致する。"""
    root = _copy_inputs(tmp_path, spec)
    assert rederive.rederive(root, check=True, specs=[spec]) == []


@pytest.mark.parametrize("spec", rederive.GENERATED_MODULES, ids=lambda s: s.module)
def test_rederive_restores_tampered_constant(
    tmp_path: Path, spec: rederive.GeneratedModule
) -> None:
    """改変された定数だけを資産の値へ戻す。"""
    root = _copy_inputs(tmp_path, spec)
    module = root / spec.module
    original = module.read_text(encoding="utf-8")
    module.write_text(
        original.replace("SCHEMA_VERSION = 1", "SCHEMA_VERSION = 99", 1),
        encoding="utf-8",
    )
    assert rederive.rederive(root, check=True, specs=[spec]) == [spec.module]
    assert rederive.rederive(root, specs=[spec]) == [spec.module]
    assert module.read_text(encoding="utf-8") == original


@pytest.mark.parametrize("spec", rederive.GENERATED_MODULES, ids=lambda s: s.module)
def test_rederive_follows_asset_revision(
    tmp_path: Path, spec: rederive.GeneratedModule
) -> None:
    """資産の revision 変更をモジュールへ伝播する。"""
    root = _copy_inputs(tmp_path, spec)
    asset_path = root / spec.asset
    asset = json.loads(asset_path.read_text(encoding="utf-8"))
    asset["contract_revision"] += 1
    asset_path.write_text(
        json.dumps(asset, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    assert rederive.rederive(root, specs=[spec]) == [spec.module]
    text = (root / spec.module).read_text(encoding="utf-8")
    assert f"CONTRACT_REVISION = {asset['contract_revision']}" in text


def test_rederive_rejects_unknown_asset_field(tmp_path: Path) -> None:
    """資産から対応値を解決できない場合は書き換えない。"""
    spec = rederive.REPOSITORY_CONTRACT
    root = _copy_inputs(tmp_path, spec)
    asset_path = root / spec.asset
    asset = json.loads(asset_path.read_text(encoding="utf-8"))
    del asset["product_function_operation_ids"]
    asset_path.write_text(
        json.dumps(asset, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with pytest.raises(KeyError):
        rederive.rederive(root, specs=[spec])
