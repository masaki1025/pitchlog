"""製品認可資産の未発効状態と資産指定の分離を検査する。"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from pitchlog.authz import runtime_contract
from pitchlog.authz.asset_spec import PROBE_SPEC, PRODUCT_SPEC, AuthzAssetSpec
from pitchlog.authz.ddl import AuthzDDLGenerationError, generate_authz_ddl

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_BODY_CHECKER = _REPOSITORY_ROOT / "scripts/check_authz_function_bodies.py"
_CATALOG_CHECKER = _REPOSITORY_ROOT / "scripts/check_authz_catalog.py"
_FINAL_PRODUCT_PATH = Path("contracts/authz/product/ddl-elements.json")
_TASK_ID_RE = re.compile(r"TSK-[0-9]+")


def _load_catalog_checker() -> Any:
    """静的検査を独立したモジュール名で読み込む。"""
    module_spec = importlib.util.spec_from_file_location(
        "check_authz_catalog_product_staging_under_test",
        _CATALOG_CHECKER,
    )
    assert module_spec is not None and module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    sys.modules[module_spec.name] = module
    module_spec.loader.exec_module(module)
    return module


_catalog_checker = _load_catalog_checker()


def _read_json_object(path: Path) -> dict[str, Any]:
    """JSON object を読み、試験入力の形を確定する。"""
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    assert all(isinstance(key, str) for key in value)
    return value


def _staged_asset(root: Path) -> dict[str, Any]:
    """二重正本を拒否して未発効資産を読む。"""
    staged_path = root / PRODUCT_SPEC.ddl_elements_path
    final_path = root / _FINAL_PRODUCT_PATH
    if staged_path.exists() and final_path.exists():
        raise AssertionError("stagedと最終パスが同時に存在する")
    if not staged_path.is_file() or final_path.exists():
        raise AssertionError("未発効状態のパス条件を満たさない")
    return _read_json_object(staged_path)


def _run_body_checker(
    root: Path,
    spec: AuthzAssetSpec,
) -> subprocess.CompletedProcess[str]:
    """指定資産について body 検査 CLI を実行する。"""
    return subprocess.run(
        [
            sys.executable,
            str(_BODY_CHECKER),
            "--root",
            str(root),
            "--asset-spec",
            spec.asset_kind,
        ],
        cwd=_REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _copy_asset_to_spec_paths(
    root: Path,
    source_spec: AuthzAssetSpec,
    destination_spec: AuthzAssetSpec,
) -> None:
    """資産のscopeを保ったまま別specの読取先へ複製する。"""
    source_ddl = _REPOSITORY_ROOT / source_spec.ddl_elements_path
    destination_ddl = root / destination_spec.ddl_elements_path
    destination_ddl.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_ddl, destination_ddl)

    source_manifest = _REPOSITORY_ROOT / source_spec.body_manifest_path
    destination_manifest = root / destination_spec.body_manifest_path
    destination_manifest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_manifest, destination_manifest)

    checker_destination = root / destination_spec.body_checker_path
    checker_destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(_BODY_CHECKER, checker_destination)
    shutil.copy2(_CATALOG_CHECKER, checker_destination.parent / _CATALOG_CHECKER.name)


def test_product_spec_and_unfrozen_empty_assets_are_explicit() -> None:
    """製品の配置・scope・空の操作集合と非凍結manifestを固定する。"""
    assert PRODUCT_SPEC.asset_root == Path("contracts/authz/product")
    assert PRODUCT_SPEC.ddl_elements_path == Path(
        "contracts/authz/product/ddl-elements.staged.json"
    )
    assert PRODUCT_SPEC.body_directory == Path(
        "contracts/authz/product/function-bodies"
    )
    assert PRODUCT_SPEC.body_manifest_path == Path(
        "contracts/authz/product/function-bodies/manifest.json"
    )
    assert PRODUCT_SPEC.allowed_scope_status == "product_configuration"
    assert PRODUCT_SPEC.allowed_scope_status != PROBE_SPEC.allowed_scope_status
    assert PRODUCT_SPEC.asset_kind == "product"
    assert PRODUCT_SPEC.operation_handlers == ()

    manifest = _read_json_object(_REPOSITORY_ROOT / PRODUCT_SPEC.body_manifest_path)
    assert set(manifest) == {"schema_version", "asset_kind", "entries"}
    assert manifest["entries"] == []


def test_repository_is_in_the_explicit_unactivated_product_state() -> None:
    """Stagedだけが存在し、暫定ランタイムと切替タスクを維持する。"""
    asset = _staged_asset(_REPOSITORY_ROOT)
    pending_switch = asset.get("pending_switch")

    assert runtime_contract.PROVISIONAL is True
    assert isinstance(pending_switch, str)
    assert _TASK_ID_RE.fullmatch(pending_switch)
    assert pending_switch == "TSK-443"


def test_staged_and_final_product_paths_cannot_coexist(tmp_path: Path) -> None:
    """Stagedと最終パスを同時に置く二重正本の変異を拒否する。"""
    staged_path = tmp_path / PRODUCT_SPEC.ddl_elements_path
    final_path = tmp_path / _FINAL_PRODUCT_PATH
    staged_path.parent.mkdir(parents=True)
    staged_path.write_text("{}\n", encoding="utf-8")
    final_path.write_text("{}\n", encoding="utf-8")

    with pytest.raises(AssertionError, match="同時に存在"):
        _staged_asset(tmp_path)


def test_product_empty_assets_are_accepted_by_all_three_readers() -> None:
    """製品の空の対応表を生成器・body検査器・静的検査が受理する。"""
    assert generate_authz_ddl(_REPOSITORY_ROOT, PRODUCT_SPEC) == ()

    body_result = _run_body_checker(_REPOSITORY_ROOT, PRODUCT_SPEC)
    assert body_result.returncode == 0, body_result.stderr

    product_asset = _read_json_object(_REPOSITORY_ROOT / PRODUCT_SPEC.ddl_elements_path)
    assert _catalog_checker.validate_ddl_elements(
        product_asset,
        _REPOSITORY_ROOT,
        PRODUCT_SPEC,
    ) == {"scope_status": PRODUCT_SPEC.allowed_scope_status}


@pytest.mark.parametrize(
    ("source_spec", "destination_spec"),
    [
        pytest.param(PRODUCT_SPEC, PROBE_SPEC, id="product-as-probe"),
        pytest.param(PROBE_SPEC, PRODUCT_SPEC, id="probe-as-product"),
    ],
)
def test_spec_swap_is_rejected_by_all_three_readers(
    tmp_path: Path,
    source_spec: AuthzAssetSpec,
    destination_spec: AuthzAssetSpec,
) -> None:
    """Probeと製品の資産取り違えを3読取経路で双方向に拒否する。"""
    root = tmp_path / source_spec.asset_kind
    _copy_asset_to_spec_paths(root, source_spec, destination_spec)

    with pytest.raises(AuthzDDLGenerationError, match="scope.status"):
        generate_authz_ddl(root, destination_spec)

    body_result = _run_body_checker(root, destination_spec)
    assert body_result.returncode == 2
    assert "scope.status" in body_result.stderr

    source_asset = _read_json_object(_REPOSITORY_ROOT / source_spec.ddl_elements_path)
    with pytest.raises(_catalog_checker.CatalogError, match="資産指定と一致しない"):
        _catalog_checker.validate_ddl_elements(
            source_asset,
            _REPOSITORY_ROOT,
            destination_spec,
        )


def test_product_manifest_rejects_source_commit(tmp_path: Path) -> None:
    """製品manifestへ凍結基準を持ち込む変異を両読取経路で拒否する。"""
    root = tmp_path / "source-commit-mutation"
    _copy_asset_to_spec_paths(root, PRODUCT_SPEC, PRODUCT_SPEC)
    assert generate_authz_ddl(root, PRODUCT_SPEC) == ()
    baseline = _run_body_checker(root, PRODUCT_SPEC)
    assert baseline.returncode == 0, baseline.stderr

    manifest_path = root / PRODUCT_SPEC.body_manifest_path
    manifest = _read_json_object(manifest_path)
    manifest["source_commit"] = "0" * 40
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(AuthzDDLGenerationError, match="source_commit"):
        generate_authz_ddl(root, PRODUCT_SPEC)
    mutated = _run_body_checker(root, PRODUCT_SPEC)
    assert mutated.returncode == 2
    assert "source_commit" in mutated.stderr
