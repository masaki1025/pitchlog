"""認可静的検査の資産指定と probe 固有分岐を検査する。"""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path, PurePosixPath
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY_ROOT / "scripts" / "check_authz_catalog.py"
DDL_ELEMENTS = REPOSITORY_ROOT / "contracts" / "authz" / "ddl-elements.json"
EXPECTED_PROBE_ONLY_CHECKS = (
    "ddl_scope_exact",
    "ddl_elements_closed_world",
    "rejected_configs_closed_world",
    "claim_mutant_map_closed_world",
    "attack_tree_closed_world",
    "boundary_proposal_closed_world",
    "verification_evidence_closed_world",
    "oracle_asset_multiplicity",
    "oracle_commit_and_seal",
)


def _load_checker() -> Any:
    """テスト対象を独立したモジュール名で読み込む。"""
    spec = importlib.util.spec_from_file_location(
        "check_authz_catalog_spec_under_test",
        SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


checker = _load_checker()
TEST_SPEC = replace(
    checker.PROBE_SPEC,
    asset_root=PurePosixPath("test-authz"),
    ddl_elements_path=PurePosixPath("test-authz/ddl-elements.json"),
    body_manifest_path=PurePosixPath("test-authz/function-bodies/manifest.json"),
    body_directory=PurePosixPath("test-authz/function-bodies"),
    allowed_scope_status="product_configuration",
    asset_kind="product",
)


def _ddl_elements() -> dict[str, Any]:
    """現行 probe の DDL 要素資産を新しいオブジェクトとして読む。"""
    value = json.loads(DDL_ELEMENTS.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _run_checker(*arguments: str) -> subprocess.CompletedProcess[bytes]:
    """静的検査 CLI を生バイト出力で実行する。"""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *arguments],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        check=False,
    )


def _complete_probe_tracker() -> Any:
    """全 probe 固有検査を実行済みにした追跡器を返す。"""
    tracker = checker._ProbeOnlyCheckTracker(checker.PROBE_SPEC)
    for check_id in EXPECTED_PROBE_ONLY_CHECKS:
        tracker.run(check_id, lambda: None)
    tracker.require(frozenset(EXPECTED_PROBE_ONLY_CHECKS))
    return tracker


def test_default_and_explicit_probe_cli_outputs_are_byte_identical() -> None:
    """既定値と明示した probe の結果・違反出力が byte 一致する。"""
    default = _run_checker()
    explicit = _run_checker("--asset-spec", "probe")

    assert default.returncode == explicit.returncode == 0
    assert default.stdout == explicit.stdout
    assert default.stderr == explicit.stderr


def test_scope_mismatches_are_rejected_in_both_directions() -> None:
    """Probe 資産と非 probe scope の spec 取り違えを双方向で拒否する。"""
    probe_asset = _ddl_elements()
    checker.validate_ddl_elements(
        probe_asset,
        REPOSITORY_ROOT,
        checker.PROBE_SPEC,
    )

    with pytest.raises(checker.CatalogError, match="資産指定と一致しない"):
        checker.validate_ddl_elements(probe_asset, REPOSITORY_ROOT, TEST_SPEC)

    non_probe_scope_asset = copy.deepcopy(probe_asset)
    non_probe_scope_asset["scope"]["status"] = TEST_SPEC.allowed_scope_status
    with pytest.raises(checker.CatalogError, match="資産指定と一致しない"):
        checker.validate_ddl_elements(
            non_probe_scope_asset,
            REPOSITORY_ROOT,
            checker.PROBE_SPEC,
        )

    assert checker.validate_ddl_elements(
        non_probe_scope_asset,
        REPOSITORY_ROOT,
        TEST_SPEC,
    ) == {"scope_status": TEST_SPEC.allowed_scope_status}


def test_repository_probe_executes_every_listed_probe_only_check(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """通常の probe 検査が一覧の全分岐を実際に通ることを固定する。"""
    observed: list[str] = []
    original_run = checker._ProbeOnlyCheckTracker.run

    def recording_run(
        tracker: Any,
        check_id: str,
        check: Any,
    ) -> object | None:
        """分岐 ID を記録して本来の検査を呼ぶ。"""
        observed.append(check_id)
        return original_run(tracker, check_id, check)

    monkeypatch.setattr(checker._ProbeOnlyCheckTracker, "run", recording_run)

    assert checker.main(["--root", str(REPOSITORY_ROOT)]) == 0
    capsys.readouterr()
    assert tuple(dict.fromkeys(observed)) == EXPECTED_PROBE_ONLY_CHECKS
    assert checker.PROBE_ONLY_CHECKS == EXPECTED_PROBE_ONLY_CHECKS


@pytest.mark.parametrize("disabled_check_id", EXPECTED_PROBE_ONLY_CHECKS)
def test_probe_only_check_condition_inversion_is_red(
    disabled_check_id: str,
) -> None:
    """Probe 条件を反転して1検査を無効にする変異を実行集合で拒否する。"""
    _complete_probe_tracker()
    mutated_tracker = checker._ProbeOnlyCheckTracker(checker.PROBE_SPEC)
    for check_id in EXPECTED_PROBE_ONLY_CHECKS:
        if check_id != disabled_check_id:
            mutated_tracker.run(check_id, lambda: None)

    with pytest.raises(checker.CatalogError, match="実行集合が不完全"):
        mutated_tracker.require(frozenset(EXPECTED_PROBE_ONLY_CHECKS))


@pytest.mark.parametrize("removed_check_id", EXPECTED_PROBE_ONLY_CHECKS)
def test_removing_probe_only_check_from_registry_is_red(
    removed_check_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """一覧から1検査を削る変異を、分岐から一覧への参照検査で拒否する。"""
    _complete_probe_tracker()
    monkeypatch.setattr(
        checker,
        "PROBE_ONLY_CHECKS",
        tuple(
            check_id
            for check_id in EXPECTED_PROBE_ONLY_CHECKS
            if check_id != removed_check_id
        ),
    )
    mutated_tracker = checker._ProbeOnlyCheckTracker(checker.PROBE_SPEC)

    with pytest.raises(checker.CatalogError, match="一覧にない"):
        mutated_tracker.run(removed_check_id, lambda: None)
