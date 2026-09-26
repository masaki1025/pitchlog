"""ランタイム契約の製品状態を試験用複製へ組み立てる。"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, cast

from pitchlog.authz.runtime_contract_state import (
    GENERATED_MODULE,
    PRODUCT_ASSET,
    RUNTIME_CONTRACT_ASSET,
    STAGED_PRODUCT_ASSET,
    asset_digest,
    derive_runtime_contract_fields,
    render_runtime_contract,
)


def copy_product_repository(source_root: Path, destination_root: Path) -> Path:
    """正しい製品状態にした最小リポジトリを複製する。

    Args:
        source_root: 未発効状態にある実リポジトリのルート。
        destination_root: 試験用リポジトリを作るディレクトリ。

    Returns:
        製品状態にした試験用リポジトリのルート。
    """
    runtime_target = destination_root / RUNTIME_CONTRACT_ASSET
    module_target = destination_root / GENERATED_MODULE
    staged_target = destination_root / STAGED_PRODUCT_ASSET
    runtime_target.parent.mkdir(parents=True, exist_ok=True)
    module_target.parent.mkdir(parents=True, exist_ok=True)
    staged_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_root / RUNTIME_CONTRACT_ASSET, runtime_target)
    shutil.copy2(source_root / GENERATED_MODULE, module_target)
    shutil.copy2(source_root / STAGED_PRODUCT_ASSET, staged_target)
    (destination_root / ".git").write_text(
        "gitdir: test-worktree\n",
        encoding="utf-8",
    )

    product_asset = _read_json(source_root / STAGED_PRODUCT_ASSET)
    product_asset.pop("pending_switch")
    product_asset.pop("provisional_contract_additions")
    _write_json(destination_root / PRODUCT_ASSET, product_asset)
    staged_target.unlink()

    runtime_asset = _read_json(runtime_target)
    revision = runtime_asset["runtime_contract_revision"]
    assert isinstance(revision, int) and not isinstance(revision, bool)
    runtime_asset["runtime_contract_revision"] = revision + 1
    baseline = cast(dict[str, Any], runtime_asset["baseline_control"])
    identity = cast(dict[str, Any], baseline["identity"])
    identity["current_identifiers"] = [f"runtime_contract_revision:{revision + 1}"]
    runtime_asset["provisional"] = False
    runtime_asset.pop("superseded_by")
    runtime_asset["derived_from"] = PRODUCT_ASSET.as_posix()
    derived = derive_runtime_contract_fields(product_asset, runtime_asset)
    application_role = cast(dict[str, Any], runtime_asset["application_role"])
    application_role["attributes"] = derived["application_role"]["attributes"]
    runtime_asset["protected_objects"] = derived["protected_objects"]
    runtime_asset["source_digest"] = asset_digest(runtime_asset)
    _write_json(runtime_target, runtime_asset)
    module_target.write_text(
        render_runtime_contract(runtime_asset),
        encoding="utf-8",
    )
    return destination_root


def _read_json(path: Path) -> dict[str, Any]:
    """試験入力の JSON object を読む。"""
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def _write_json(path: Path, value: dict[str, Any]) -> None:
    """試験用 JSON object を所定の体裁で書く。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
