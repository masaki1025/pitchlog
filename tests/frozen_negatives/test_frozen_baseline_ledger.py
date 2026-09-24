"""凍結基準台帳のfail-closed不変条件を固定する負例。"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
LEDGER_PATH = REPOSITORY_ROOT / "contracts/authz/frozen-baselines.json"
CHECKER_PATH = REPOSITORY_ROOT / "scripts/check_frozen_baselines.py"


@pytest.fixture
def copied_ledger(tmp_path: Path) -> Iterator[Path]:
    """台帳の一時複製を渡し、終了時に元の生bytesへ復元して一致を検査する。"""
    original_bytes = LEDGER_PATH.read_bytes()
    path = tmp_path / "frozen-baselines.json"
    path.write_bytes(original_bytes)

    yield path

    path.write_bytes(original_bytes)
    assert path.read_bytes() == original_bytes
    assert LEDGER_PATH.read_bytes() == original_bytes


def _run_checker(path: Path) -> subprocess.CompletedProcess[str]:
    """一時台帳に対してgit非依存の検査器を実行する。"""
    return subprocess.run(
        [
            sys.executable,
            str(CHECKER_PATH),
            "--invariants-only",
            "--root",
            str(REPOSITORY_ROOT),
            "--ledger",
            str(path),
        ],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _assert_baseline_green(path: Path) -> None:
    """変異前の一時台帳が正常終了することを表明する。"""
    result = _run_checker(path)
    assert result.returncode == 0
    assert result.stdout == "frozen-baselines: OK\n"
    assert result.stderr == ""


def _read_ledger(path: Path) -> dict[str, Any]:
    """一時台帳をobjectとして読む。"""
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _write_ledger(path: Path, value: dict[str, Any]) -> None:
    """変異した一時台帳をJSONとして書く。"""
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _assert_red(path: Path, expected_message: str) -> None:
    """検査器が期待エラー文だけを出して非0終了することを表明する。"""
    result = _run_checker(path)
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == f"frozen-baselines: ERROR: {expected_message}\n"


@pytest.mark.frozen_negative
def test_unknown_top_level_key_is_red(copied_ledger: Path) -> None:
    """N1: トップレベルの未知キーを拒否する。"""
    _assert_baseline_green(copied_ledger)
    ledger = _read_ledger(copied_ledger)
    ledger["unexpected"] = True
    _write_ledger(copied_ledger, ledger)

    _assert_red(
        copied_ledger,
        "トップレベル のキーがexact-set不一致: 不足=[]; 過剰=['unexpected']",
    )


@pytest.mark.frozen_negative
def test_missing_top_level_key_is_red(copied_ledger: Path) -> None:
    """N2: トップレベルの必須キー欠落を拒否する。"""
    _assert_baseline_green(copied_ledger)
    ledger = _read_ledger(copied_ledger)
    del ledger["asset_kind"]
    _write_ledger(copied_ledger, ledger)

    _assert_red(
        copied_ledger,
        "トップレベル のキーがexact-set不一致: 不足=['asset_kind']; 過剰=[]",
    )


@pytest.mark.frozen_negative
def test_unknown_change_aspect_is_red(copied_ledger: Path) -> None:
    """N3: changesの未知aspectを拒否する。"""
    _assert_baseline_green(copied_ledger)
    ledger = _read_ledger(copied_ledger)
    ledger["history"][0]["changes"][0]["aspect"] = "unknown"
    _write_ledger(copied_ledger, ledger)

    _assert_red(
        copied_ledger,
        "未知の changes[].aspect: history[0].changes[0]=unknown",
    )


@pytest.mark.frozen_negative
def test_identity_without_registered_strategy_is_red(copied_ledger: Path) -> None:
    """N4: registryに存在しないidentityを拒否する。"""
    _assert_baseline_green(copied_ledger)
    ledger = _read_ledger(copied_ledger)
    ledger["declarations"]["oracle_input"]["identity"] = "unknown_identity"
    _write_ledger(copied_ledger, ledger)

    _assert_red(
        copied_ledger,
        "declarations.oracle_input の identity/granularity に戦略がない: "
        "unknown_identity/json_pointer_value",
    )


@pytest.mark.frozen_negative
def test_removed_movement_trigger_is_red(copied_ledger: Path) -> None:
    """N5: movement triggerの縮小を拒否する。"""
    _assert_baseline_green(copied_ledger)
    ledger = _read_ledger(copied_ledger)
    ledger["movement_rules"]["triggers"].remove("value_change")
    _write_ledger(copied_ledger, ledger)

    _assert_red(
        copied_ledger,
        "schema: $.movement_rules.triggers: 配列要素数が下限未満: 6 < 7",
    )


@pytest.mark.frozen_negative
def test_reduced_universal_lower_bound_is_red(copied_ledger: Path) -> None:
    """N6: universal lower boundの5軸からの縮小を拒否する。"""
    _assert_baseline_green(copied_ledger)
    ledger = _read_ledger(copied_ledger)
    ledger["movement_rules"]["universal_lower_bound"].remove("set")
    _write_ledger(copied_ledger, ledger)

    _assert_red(
        copied_ledger,
        "schema: $.movement_rules.universal_lower_bound: 配列要素数が下限未満: 4 < 5",
    )


@pytest.mark.frozen_negative
def test_additional_target_for_unknown_trigger_is_red(copied_ledger: Path) -> None:
    """N7: triggers外のadditional targetキーを拒否する。"""
    _assert_baseline_green(copied_ledger)
    ledger = _read_ledger(copied_ledger)
    ledger["movement_rules"]["additional_targets"]["unknown_trigger"] = [
        "oracle_input"
    ]
    _write_ledger(copied_ledger, ledger)

    _assert_red(
        copied_ledger,
        "schema: $.movement_rules.additional_targets.<key>: "
        "enum外の値: 'unknown_trigger'",
    )


@pytest.mark.frozen_negative
def test_missing_self_change_rule_is_red(copied_ledger: Path) -> None:
    """N8: movement rulesからself_changeを削れない。"""
    _assert_baseline_green(copied_ledger)
    ledger = _read_ledger(copied_ledger)
    del ledger["movement_rules"]["self_change"]
    _write_ledger(copied_ledger, ledger)

    _assert_red(
        copied_ledger,
        "schema: $.movement_rules: 必須キー不足: ['self_change']",
    )


@pytest.mark.frozen_negative
def test_changed_code_asset_digest_is_red(copied_ledger: Path) -> None:
    """N9: code assetの申告digest改ざんを拒否する。"""
    _assert_baseline_green(copied_ledger)
    ledger = _read_ledger(copied_ledger)
    ledger["implementation_bindings"]["code_assets"][0]["sha256"] = "0" * 64
    _write_ledger(copied_ledger, ledger)

    _assert_red(
        copied_ledger,
        "implementation_bindings.code_assets の sha256 が不一致: "
        "scripts/check_frozen_baselines.py",
    )


@pytest.mark.frozen_negative
def test_before_locator_with_missing_symbol_is_red(copied_ledger: Path) -> None:
    """N10: placement beforeの実在しないsymbolを拒否する。"""
    _assert_baseline_green(copied_ledger)
    ledger = _read_ledger(copied_ledger)
    before = ledger["history"][0]["placement_change"]["before"][0]
    before["symbol"] = "MISSING_FROZEN_BASELINE"
    _write_ledger(copied_ledger, ledger)

    _assert_red(
        copied_ledger,
        "history.oracle_input.placement_change.before が導出値と不一致",
    )


@pytest.mark.frozen_negative
def test_missing_placement_change_is_red(copied_ledger: Path) -> None:
    """N11: placement_changeなしでplacementsを復元する経路を拒否する。"""
    _assert_baseline_green(copied_ledger)
    ledger = _read_ledger(copied_ledger)
    del ledger["history"][0]["placement_change"]
    _write_ledger(copied_ledger, ledger)

    _assert_red(
        copied_ledger,
        "replay: history[0].placement_change がなく placements を復元できない",
    )


@pytest.mark.frozen_negative
def test_absent_prior_identity_with_values_is_red(copied_ledger: Path) -> None:
    """N12: absent申告と値ありを混同できない。"""
    _assert_baseline_green(copied_ledger)
    ledger = _read_ledger(copied_ledger)
    ledger["history"][0]["prior_identity"]["present"] = False
    _write_ledger(copied_ledger, ledger)

    _assert_red(
        copied_ledger,
        "history[0].prior_identity: present=false なら "
        "values は空配列でなければならない",
    )


@pytest.mark.frozen_negative
def test_new_identity_different_from_derived_value_is_red(copied_ledger: Path) -> None:
    """N13: new identityの1文字改ざんを導出照合で拒否する。"""
    _assert_baseline_green(copied_ledger)
    ledger = _read_ledger(copied_ledger)
    value = ledger["history"][0]["new_identity"]["values"][0]["value"]
    ledger["history"][0]["new_identity"]["values"][0]["value"] = "0" + value[1:]
    _write_ledger(copied_ledger, ledger)

    _assert_red(
        copied_ledger,
        "history.oracle_input.new_identity が戦略の導出値と不一致",
    )


@pytest.mark.frozen_negative
def test_impossible_approval_date_is_red(copied_ledger: Path) -> None:
    """N14: ISO形式でも実在しない承認日を拒否する。"""
    _assert_baseline_green(copied_ledger)
    ledger = _read_ledger(copied_ledger)
    ledger["history"][0]["approved_at"] = "2026-02-30"
    _write_ledger(copied_ledger, ledger)

    _assert_red(
        copied_ledger,
        "schema: $.history[0].approved_at: 実在する日付でない: 2026-02-30",
    )
