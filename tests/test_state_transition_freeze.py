"""状態遷移契約の凍結基準と追記専用受理履歴を検証する。"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FREEZE_SCRIPT = REPOSITORY_ROOT / "scripts" / "state_transition_freeze.py"
DESCRIPTOR_SCRIPT = REPOSITORY_ROOT / "scripts" / "check_input_axes_descriptor.py"


def _load_module(name: str, path: Path) -> Any:
    """テスト対象をsys.path変更なしでモジュールとして読む。"""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


freeze_checker = _load_module("state_transition_freeze", FREEZE_SCRIPT)
descriptor_checker = _load_module(
    "freeze_test_descriptor_checker", DESCRIPTOR_SCRIPT
)


def _descriptor() -> dict[str, Any]:
    """リポジトリの入力軸descriptorを読む。"""
    path = REPOSITORY_ROOT / descriptor_checker.DESCRIPTOR_PATH
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _declaration() -> dict[str, Any]:
    """descriptorの凍結基準宣言を返す。"""
    value = _descriptor()[freeze_checker.FREEZE_FIELD]
    assert isinstance(value, dict)
    return value


def test_repository_history_is_one_append_from_origin_develop() -> None:
    """PR比較元で基準が無かった状態から受理記録1件だけを追記している。"""
    freeze_checker.validate_repository_history(
        REPOSITORY_ROOT,
        descriptor_checker.DESCRIPTOR_PATH,
        _declaration(),
    )


def test_current_identities_are_derived_from_all_asset_side_criteria() -> None:
    """現行3基準の識別値は検査器定数でなく資産側宣言から導出する。"""
    declaration = freeze_checker.validate_declaration(_declaration())

    assert declaration["history"][-1]["newIdentity"] == {
        "present": True,
        "values": freeze_checker.current_identities(declaration["criteria"]),
    }


def test_missing_declaration_is_fail_closed() -> None:
    """凍結基準宣言を取得できなければdescriptor検査を開始できない。"""
    descriptor = _descriptor()
    descriptor.pop(freeze_checker.FREEZE_FIELD)

    with pytest.raises(
        descriptor_checker.DescriptorCheckError,
        match="凍結基準宣言を検証できない",
    ):
        descriptor_checker.load_descriptor_criteria(descriptor)


def test_empty_criteria_is_fail_closed() -> None:
    """判断元が空なら中立扱いせず拒否する。"""
    declaration = copy.deepcopy(_declaration())
    declaration["criteria"]["threeWayParity"] = {}

    with pytest.raises(
        freeze_checker.FreezeBaselineError,
        match="空でないobject",
    ):
        freeze_checker.validate_declaration(declaration)


def test_unresolvable_comparison_source_is_fail_closed() -> None:
    """比較元refを解決できない場合は直前基準なしと推定せず拒否する。"""
    declaration = copy.deepcopy(_declaration())
    declaration["acceptance"]["baseRef"] = "refs/heads/not-existing-freeze-base"

    with pytest.raises(
        freeze_checker.FreezeBaselineError,
        match="rev-parse.*実行できない",
    ):
        freeze_checker.validate_repository_history(
            REPOSITORY_ROOT,
            descriptor_checker.DESCRIPTOR_PATH,
            declaration,
        )


def test_existing_history_record_rewrite_is_red() -> None:
    """受理済み履歴の事実欄を書き換えても追記として扱わない。"""
    base = _declaration()
    current = copy.deepcopy(base)
    current["history"][0]["fact"] = "書き換えた事実"

    with pytest.raises(
        freeze_checker.FreezeBaselineError,
        match="書き換えまたは削除",
    ):
        freeze_checker.validate_append_only_transition(current, base)


def test_existing_history_record_deletion_is_red() -> None:
    """受理済み履歴を削除しても追記専用検査が拒否する。"""
    base = _declaration()
    current = copy.deepcopy(base)
    current["history"] = []

    with pytest.raises(
        freeze_checker.FreezeBaselineError,
        match="historyは空でない配列",
    ):
        freeze_checker.validate_append_only_transition(current, base)


def test_criteria_change_without_acceptance_record_is_red() -> None:
    """基準値だけを追随させて受理履歴を増やさない変更を拒否する。"""
    declaration = copy.deepcopy(_declaration())
    exclusions = declaration["criteria"]["threeWayParity"][
        "branchCoverageExclusions"
    ]
    exclusions["DRAW-04"] = "受理記録なしの変更"

    with pytest.raises(
        freeze_checker.FreezeBaselineError,
        match="newIdentityが現行基準の識別値と一致しない",
    ):
        freeze_checker.validate_declaration(declaration)
