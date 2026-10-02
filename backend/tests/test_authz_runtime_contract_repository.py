"""ランタイム契約の製品状態を試験用複製へ組み立てる。"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import replace
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

from pitchlog.authz.asset_spec import PRODUCT_SPEC, AuthzAssetSpec
from pitchlog.authz.runtime_contract_state import (
    GENERATED_MODULE,
    PRODUCT_ASSET,
    RUNTIME_CONTRACT_ASSET,
    STAGED_PRODUCT_ASSET,
    RuntimeContractState,
    asset_digest,
    derive_runtime_contract_fields,
    evaluate_repository,
    product_asset_path_for_state,
    render_runtime_contract,
)

PRODUCT_STATE_TEST_FILES = (
    Path("backend/tests/test_authz_product_staging.py"),
    Path("backend/tests/test_authz_product_function_acls.py"),
    Path("backend/tests/test_authz_product_control_access.py"),
    Path("backend/tests/test_authz_product_classification.py"),
    Path("backend/tests/test_authz_runtime_contract.py"),
)


@lru_cache(maxsize=None)
def provisional_reference_revision(repository_root: Path) -> str:
    """未発効の変異試験に使う直近の staged 存在コミットを選ぶ。

    Args:
        repository_root: 履歴を持つ実リポジトリのルート。

    Returns:
        staged 製品資産が存在した比較元の commit SHA。
    """
    history = subprocess.run(
        [
            "git",
            "rev-list",
            "HEAD",
            "--",
            STAGED_PRODUCT_ASSET.as_posix(),
        ],
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    )
    for revision in history.stdout.splitlines():
        exists = subprocess.run(
            [
                "git",
                "cat-file",
                "-e",
                f"{revision}:{STAGED_PRODUCT_ASSET.as_posix()}",
            ],
            cwd=repository_root,
            check=False,
            capture_output=True,
        )
        if exists.returncode == 0:
            return revision
    raise AssertionError("HEAD の履歴に staged 製品資産がありません")


def product_spec_for_repository(repository_root: Path) -> AuthzAssetSpec:
    """共有 API が選んだ製品資産のパスを持つ試験用 spec を返す。

    Args:
        repository_root: 状態を判定するリポジトリのルート。

    Returns:
        現在の状態に対応する製品 DDL 資産の spec。
    """
    state, violations = evaluate_repository(repository_root)
    if violations:
        raise AssertionError(f"ランタイム契約違反: {sorted(violations)}")
    product_path = product_asset_path_for_state(state)
    if product_path is None:
        raise AssertionError("製品 DDL 資産が存在する状態ではない")
    return replace(PRODUCT_SPEC, ddl_elements_path=product_path)


def copy_product_repository(source_root: Path, destination_root: Path) -> Path:
    """正しい製品状態にした最小リポジトリを複製する。

    Args:
        source_root: 未発効状態にある実リポジトリのルート。
        destination_root: 試験用リポジトリを作るディレクトリ。

    Returns:
        製品状態にした試験用リポジトリのルート。
    """
    state, violations = evaluate_repository(source_root)
    if violations:
        raise AssertionError(f"複製元のランタイム契約が不正: {sorted(violations)}")
    if state not in (RuntimeContractState.PENDING, RuntimeContractState.PRODUCT):
        raise AssertionError(f"製品状態へ複製できない状態: {state.value}")

    runtime_target = destination_root / RUNTIME_CONTRACT_ASSET
    module_target = destination_root / GENERATED_MODULE
    runtime_target.parent.mkdir(parents=True, exist_ok=True)
    module_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_root / RUNTIME_CONTRACT_ASSET, runtime_target)
    shutil.copy2(source_root / GENERATED_MODULE, module_target)
    (destination_root / ".git").write_text(
        "gitdir: test-worktree\n",
        encoding="utf-8",
    )

    if state is RuntimeContractState.PRODUCT:
        product_target = destination_root / PRODUCT_ASSET
        product_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_root / PRODUCT_ASSET, product_target)
        return destination_root

    staged_target = destination_root / STAGED_PRODUCT_ASSET
    staged_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_root / STAGED_PRODUCT_ASSET, staged_target)
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


def copy_product_test_repository(
    source_root: Path,
    destination_root: Path,
) -> Path:
    """状態別試験を再実行できる製品状態の複製を作る。

    Args:
        source_root: 現在の実リポジトリのルート。
        destination_root: 試験用リポジトリを作るディレクトリ。

    Returns:
        対象試験と静的入力を備えた製品状態の試験用リポジトリ。
    """
    shutil.copytree(source_root / "contracts", destination_root / "contracts")
    shutil.copytree(source_root / "scripts", destination_root / "scripts")
    shutil.copytree(source_root / "backend/src", destination_root / "backend/src")
    shutil.copytree(
        source_root / "backend/migrations",
        destination_root / "backend/migrations",
    )
    data_model = Path("docs/design/data-model.md")
    (destination_root / data_model).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_root / data_model, destination_root / data_model)
    shutil.copy2(
        source_root / "backend/pyproject.toml",
        destination_root / "backend/pyproject.toml",
    )
    for relative_path in (
        Path("backend/tests/conftest.py"),
        Path("backend/tests/test_authz_runtime_contract_repository.py"),
        *PRODUCT_STATE_TEST_FILES,
    ):
        target = destination_root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_root / relative_path, target)

    repository = copy_product_repository(source_root, destination_root)
    if evaluate_repository(source_root)[0] is RuntimeContractState.PENDING:
        _activate_product_asset_spec(repository)
    return repository


def _activate_product_asset_spec(repository_root: Path) -> None:
    """製品状態の複製で資産指定を最終パスへ切り替える。"""
    spec_path = repository_root / "backend/src/pitchlog/authz/asset_spec.py"
    source = spec_path.read_text(encoding="utf-8")
    staged = f'ddl_elements_path=PurePosixPath("{STAGED_PRODUCT_ASSET.as_posix()}")'
    final = f'ddl_elements_path=PurePosixPath("{PRODUCT_ASSET.as_posix()}")'
    if source.count(staged) != 1:
        raise AssertionError("製品資産の staged パスを一意に置換できない")
    spec_path.write_text(source.replace(staged, final), encoding="utf-8")


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
