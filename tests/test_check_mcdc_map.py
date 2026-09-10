"""認可 MC/DC 写像の独立検査器と負例を検証する。"""

from __future__ import annotations

import copy
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
SCRIPT = REPOSITORY_ROOT / "scripts" / "check_mcdc_map.py"
CATALOG_SCRIPT = REPOSITORY_ROOT / "scripts" / "check_authz_catalog.py"
BODY_SCRIPT = REPOSITORY_ROOT / "scripts" / "check_authz_function_bodies.py"


def _load_module(name: str, path: Path) -> Any:
    """検査器を sys.path の変更なしでモジュールとして読む。"""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_load_module("check_authz_catalog", CATALOG_SCRIPT)
_load_module("check_authz_function_bodies", BODY_SCRIPT)
checker = _load_module("check_mcdc_map_under_test", SCRIPT)

ASSET_PATH = REPOSITORY_ROOT / checker.ASSET_PATH
BODY_DIRECTORY = REPOSITORY_ROOT / checker.BODY_MANIFEST_PATH.parent
CLAIM_MUTANT_MAP_PATH = REPOSITORY_ROOT / checker.CLAIM_MUTANT_MAP_PATH
DDL_ELEMENTS_PATH = REPOSITORY_ROOT / "contracts/authz/ddl-elements.json"
CASE_BODY_PATH = (
    REPOSITORY_ROOT
    / "contracts/authz/function-bodies/functions/read_control_resources.sql"
)


def _asset_snapshot() -> dict[str, bytes]:
    """試験が読む本物の資産を生バイトで採取する。"""
    paths = [ASSET_PATH, CLAIM_MUTANT_MAP_PATH, DDL_ELEMENTS_PATH]
    paths.extend(path for path in BODY_DIRECTORY.rglob("*") if path.is_file())
    return {
        path.relative_to(REPOSITORY_ROOT).as_posix(): path.read_bytes()
        for path in sorted(paths)
    }


@pytest.fixture
def copied_repository(tmp_path: Path) -> Iterator[Path]:
    """Git object を共有する一時コピーを作り、本物の資産を事後照合する。"""
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
    shutil.copytree(BODY_DIRECTORY, root / checker.BODY_MANIFEST_PATH.parent)
    for path in (ASSET_PATH, CLAIM_MUTANT_MAP_PATH, DDL_ELEMENTS_PATH):
        destination = root / path.relative_to(REPOSITORY_ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)

    yield root

    assert _asset_snapshot() == original_assets


def _read_asset(root: Path) -> dict[str, Any]:
    """一時コピーの MC/DC 写像を読む。"""
    raw = json.loads((root / checker.ASSET_PATH).read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return raw


def _write_asset(root: Path, asset: dict[str, Any]) -> None:
    """一時コピーの MC/DC 写像を書く。"""
    (root / checker.ASSET_PATH).write_text(
        json.dumps(asset, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _run_cli(root: Path) -> subprocess.CompletedProcess[str]:
    """指定リポジトリに対して独立検査 CLI を実行する。"""
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root)],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )


def _decisions(asset: dict[str, Any]) -> list[dict[str, Any]]:
    """型を検査して判定行を返す。"""
    decisions = asset["decisions"]
    assert isinstance(decisions, list) and decisions
    assert all(isinstance(decision, dict) for decision in decisions)
    return decisions


def _decision_with_form(
    asset: dict[str, Any],
    decision_form: str,
) -> dict[str, Any]:
    """指定した判定形の最初の行を返す。"""
    decision = next(
        row for row in _decisions(asset) if row["decision_form"] == decision_form
    )
    assert isinstance(decision, dict)
    return decision


def test_repository_mcdc_map_is_valid() -> None:
    """リポジトリ上の MC/DC 写像が body 由来の集合と一致する。"""
    result = _run_cli(REPOSITORY_ROOT)

    assert result.returncode == 0, result.stderr
    validation = checker.validate_repository(REPOSITORY_ROOT)
    assert validation.decision_count == len(validation.locations)
    assert "authz-mcdc-map: OK" in result.stdout


def test_table_driven_case_is_derived_without_case_keyword() -> None:
    """表駆動の要求分岐を literal CASE なしでも CASE 形として導出する。"""
    body_text = CASE_BODY_PATH.read_text(encoding="utf-8")
    asset = _read_asset(REPOSITORY_ROOT)
    decision = next(
        row
        for row in _decisions(asset)
        if row["decision_id"] == "CONTROL_ADMIN_ONLY_ACCESS"
    )

    assert "CASE" not in body_text.upper()
    assert decision["decision_form"] == "CASE"
    assert checker.validate_repository(REPOSITORY_ROOT).findings == ()


def test_fictitious_decision_id_is_red(copied_repository: Path) -> None:
    """body にない架空の判定 ID を足すと exact-set 不一致で red になる。"""
    root = copied_repository
    asset = _read_asset(root)
    fictitious = copy.deepcopy(_decisions(asset)[0])
    fictitious["decision_id"] = "FICTITIOUS_DECISION"
    _decisions(asset).append(fictitious)
    _write_asset(root, asset)

    result = _run_cli(root)

    assert result.returncode == 1
    assert "判定ID集合がbody由来の集合とexact-set不一致" in result.stderr
    assert "FICTITIOUS_DECISION" in result.stderr


def test_removed_decision_id_is_red(copied_repository: Path) -> None:
    """body 由来の判定 ID を一つ削ると exact-set 不一致で red になる。"""
    root = copied_repository
    asset = _read_asset(root)
    removed = _decisions(asset).pop()
    _write_asset(root, asset)

    result = _run_cli(root)

    assert result.returncode == 1
    assert "判定ID集合がbody由来の集合とexact-set不一致" in result.stderr
    assert removed["decision_id"] in result.stderr


def test_shared_business_row_tenant_match_cannot_be_removed(
    copied_repository: Path,
) -> None:
    """業務行と認可済みテナントを結ぶ判定を写像から外すと red になる。"""
    root = copied_repository
    asset = _read_asset(root)
    decision_id = "SHARED_BUSINESS_ROW_TENANT_MATCH"
    decisions = _decisions(asset)
    decisions[:] = [
        decision for decision in decisions if decision["decision_id"] != decision_id
    ]
    _write_asset(root, asset)

    result = _run_cli(root)

    assert result.returncode == 1
    assert "判定ID集合がbody由来の集合とexact-set不一致" in result.stderr
    assert decision_id in result.stderr


def test_identical_test_ids_are_red(copied_repository: Path) -> None:
    """独立影響対の二つのテスト ID を同一にすると red になる。"""
    root = copied_repository
    asset = _read_asset(root)
    pair = _decisions(asset)[0]["independence_pairs"][0]
    pair["test_ids"][1] = pair["test_ids"][0]
    _write_asset(root, asset)

    result = _run_cli(root)

    assert result.returncode == 1
    assert "テスト対の2つのIDが同一" in result.stderr


def test_non_target_input_change_is_red(copied_repository: Path) -> None:
    """対象条件以外の入力も変えたテスト対は red になる。"""
    root = copied_repository
    asset = _read_asset(root)
    decision = _decision_with_form(asset, "AND")
    pair = decision["independence_pairs"][0]
    pair["input_b"][1] = not pair["input_a"][1]
    _write_asset(root, asset)

    result = _run_cli(root)

    assert result.returncode == 1
    assert "対象条件以外の入力も変化している" in result.stderr


def test_target_condition_without_flip_is_red(copied_repository: Path) -> None:
    """対象条件を反転させないテスト対は red になる。"""
    root = copied_repository
    asset = _read_asset(root)
    pair = _decision_with_form(asset, "ATOMIC")["independence_pairs"][0]
    pair["input_b"][0] = pair["input_a"][0]
    _write_asset(root, asset)

    result = _run_cli(root)

    assert result.returncode == 1
    assert "対象条件が反転していない" in result.stderr


def test_observed_result_without_flip_is_red(copied_repository: Path) -> None:
    """実測した判定結果が反転しないテスト対は red になる。"""
    root = copied_repository
    asset = _read_asset(root)
    pair = _decision_with_form(asset, "ATOMIC")["independence_pairs"][0]
    pair["observed_results"][1] = pair["observed_results"][0]
    _write_asset(root, asset)

    result = _run_cli(root)

    assert result.returncode == 1
    assert "実測した判定結果が反転していない" in result.stderr


def test_missing_required_decision_form_is_red(copied_repository: Path) -> None:
    """要求された判定形を写像上で覆わないと red になる。"""
    root = copied_repository
    asset = _read_asset(root)
    decision = _decision_with_form(asset, "OR")
    decision["decision_form"] = "AND"
    _write_asset(root, asset)

    result = _run_cli(root)

    assert result.returncode == 1
    assert "mcdc_decision_formsの判定形を覆っていない: OR" in result.stderr


def test_changed_body_without_manifest_update_is_red(
    copied_repository: Path,
) -> None:
    """body だけを変えて manifest を更新しなければ digest 照合で red になる。"""
    root = copied_repository
    body_path = (
        root
        / "contracts/authz/function-bodies/functions/authorized_shared_rows.sql"
    )
    body_path.write_bytes(body_path.read_bytes() + b"\n-- negative mutation\n")

    result = _run_cli(root)

    assert result.returncode == 1
    assert "現bodyのblob digestが不一致" in result.stderr


def test_changed_manifest_breaks_mcdc_digest_chain(
    copied_repository: Path,
) -> None:
    """body manifest のバイト列変更は MC/DC 資産への digest 連鎖を切る。"""
    root = copied_repository
    manifest_path = root / checker.BODY_MANIFEST_PATH
    manifest_path.write_bytes(manifest_path.read_bytes() + b"\n")

    result = _run_cli(root)

    assert result.returncode == 1
    assert "body manifestのdigest連鎖が不一致" in result.stderr
