"""定義の穴9件を追跡するgap registerの骨格と状態述語を検証する。"""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY_ROOT / "scripts" / "check_gap_register.py"
DESCRIPTOR_SCRIPT = REPOSITORY_ROOT / "scripts" / "check_input_axes_descriptor.py"
PARITY_SCRIPT = (
    REPOSITORY_ROOT / "scripts" / "check_input_axes_three_way_parity.py"
)
FREEZE_SCRIPT = REPOSITORY_ROOT / "scripts" / "state_transition_freeze.py"


def _load_module(name: str, path: Path) -> Any:
    """テスト対象をsys.path変更なしでモジュールとして読む。"""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_load_module("state_transition_freeze", FREEZE_SCRIPT)
_load_module("check_input_axes_descriptor", DESCRIPTOR_SCRIPT)
_load_module("check_input_axes_three_way_parity", PARITY_SCRIPT)
checker = _load_module("check_gap_register_under_test", SCRIPT)
REGISTER_PATH = REPOSITORY_ROOT / checker.REGISTER_PATH


def _register() -> dict[str, Any]:
    """リポジトリのgap registerを読む。"""
    value = json.loads(REGISTER_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _criteria() -> Any:
    """資産側宣言からgap register検査基準を読む。"""
    descriptor = json.loads(
        (
            REPOSITORY_ROOT
            / checker.clause_id_source.DESCRIPTOR_PATH
        ).read_text(encoding="utf-8")
    )
    assert isinstance(descriptor, dict)
    return checker.load_gap_criteria(descriptor)


def _validate(document: dict[str, Any]) -> None:
    """要件書から抽出した実在条文IDで文書を検証する。"""
    checker.validate_gap_register_document(
        document,
        checker.load_requirement_clause_ids(REPOSITORY_ROOT),
        _criteria(),
    )


def test_repository_gap_register_is_green() -> None:
    """実資産が配置・命名・骨格・条文参照の検査を通る。"""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(REPOSITORY_ROOT)],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "gap-register: OK\n"
    assert result.stderr == ""


def test_nine_open_gaps_have_only_the_clause_stage_filled() -> None:
    """全9件がclauseIdsだけを持つopenの連続prefixである。"""
    document = _register()
    expected_clauses = {
        "GAP-01": ["FR-020"],
        "GAP-02": ["E-1"],
        "GAP-03": ["F-1"],
        "GAP-04": ["F-1"],
        "GAP-05": ["FR-020", "FR-005"],
        "GAP-06": ["A-1", "FR-003"],
        "GAP-07": ["E-1", "FR-004"],
        "GAP-08": ["E-2", "A-2"],
        "GAP-09": ["A-3"],
    }

    assert len(document["gaps"]) == 9
    assert {gap["gapId"]: gap["clauseIds"] for gap in document["gaps"]} == (
        expected_clauses
    )
    assert all(gap["state"] == "open" for gap in document["gaps"])
    assert all(
        gap["branchIds"] == []
        and gap["rowIds"] == []
        and gap["fixtureCaseIds"] == []
        and gap["generatedCaseSelector"] is None
        for gap in document["gaps"]
    )
    _validate(document)


def test_requirement_clause_extractor_is_reused_and_requirement_scoped() -> None:
    """既存抽出器を要件書だけへ適用しADRだけの決定IDを混入させない。"""
    clause_ids = checker.load_requirement_clause_ids(REPOSITORY_ROOT)

    assert {"FR-020", "A-1", "A-2", "A-3", "E-1", "E-2", "F-1"} <= (
        clause_ids
    )
    assert "D-11" not in clause_ids


def test_skipping_clause_stage_before_branch_stage_is_red() -> None:
    """clauseIdsを空にしてbranchIdsだけ埋めた途中段の飛ばしを拒否する。"""
    document = copy.deepcopy(_register())
    gap = document["gaps"][0]
    gap["clauseIds"] = []
    gap["branchIds"] = ["XMARK-01"]

    with pytest.raises(checker.GapRegisterError, match="連続したprefix"):
        _validate(document)


def test_unknown_requirement_clause_id_is_red() -> None:
    """文字列形式が妥当でも要件書に実在しないclauseIdを拒否する。"""
    document = copy.deepcopy(_register())
    document["gaps"][0]["clauseIds"] = ["FR-999"]

    with pytest.raises(checker.GapRegisterError, match="要件書に実在しない"):
        _validate(document)


def test_resolved_without_all_five_stages_is_red() -> None:
    """clauseIdsしか持たないentryをresolvedへ変えても受理しない。"""
    document = copy.deepcopy(_register())
    document["gaps"][0]["state"] = "resolved"

    with pytest.raises(checker.GapRegisterError, match="resolvedは5段すべて"):
        _validate(document)


def test_state_progression_is_one_way() -> None:
    """openからresolvedだけを許しresolvedからopenへの逆遷移を拒否する。"""
    open_document = _register()
    resolved_document = copy.deepcopy(open_document)
    resolved_document["gaps"][0]["state"] = "resolved"

    checker.validate_state_progression(
        open_document, resolved_document, _criteria()
    )
    with pytest.raises(checker.GapRegisterError, match="resolvedからopenへの逆遷移"):
        checker.validate_state_progression(
            resolved_document, open_document, _criteria()
        )


def test_register_path_and_version_follow_d12_naming() -> None:
    """1階層のstate-transition領域と<対象>_v<N>.json命名を固定する。"""
    document = _register()

    assert checker.REGISTER_PATH.parts == (
        "contracts",
        "state-transition",
        "gap_register_v1.json",
    )
    assert checker.parity_checker.CONTRACT_FILENAME_PATTERN.fullmatch(
        checker.REGISTER_PATH.name
    )
    assert document["version"] == checker.REGISTER_PATH.stem
    assert document["schemaVersion"] == 1
