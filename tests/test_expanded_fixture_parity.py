"""規範行展開と手作業fixtureの完全照合を検証する。"""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
ASSETS = ROOT / "contracts/state-transition"


def _load_module(name: str, path: Path) -> Any:
    """検査器と依存モジュールを読み込む。"""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_load_module("state_transition_freeze", SCRIPTS / "state_transition_freeze.py")
_load_module("check_input_axes_descriptor", SCRIPTS / "check_input_axes_descriptor.py")
_load_module("check_deriver_dependencies", SCRIPTS / "check_deriver_dependencies.py")
_load_module("check_expander_dependencies", SCRIPTS / "check_expander_dependencies.py")
_load_module("representative_selection", SCRIPTS / "representative_selection.py")
_load_module("state_transition_normalization", SCRIPTS / "state_transition_normalization.py")
_load_module("expand_state_transition_cases", SCRIPTS / "expand_state_transition_cases.py")
_load_module("expand_game_end_cases", SCRIPTS / "expand_game_end_cases.py")
_load_module("check_branch_row_mapping", SCRIPTS / "check_branch_row_mapping.py")
checker = _load_module(
    "check_expanded_fixture_parity", SCRIPTS / "check_expanded_fixture_parity.py"
)


def _read(name: str) -> dict[str, Any]:
    """検査用の資産を変更可能な形で読む。"""
    return json.loads((ASSETS / name).read_text(encoding="utf-8"))


def _inputs() -> tuple[
    dict[str, Any], list[dict[str, Any]], dict[str, Any],
    list[dict[str, Any]], list[dict[str, Any]],
]:
    """全件展開結果と手作業fixtureを揃える。"""
    mapping = _read("branch_row_mapping_v1.json")
    fixtures = [
        *_read("state_transition_manual_fixtures_v1.json")["fixtures"],
        *_read("game_end_manual_fixtures_v1.json")["fixtures"],
    ]
    state = _read("state_transition_contract_v1.json")
    game_end = _read("game_end_contract_v1.json")
    expanded_state, _ = checker.expand_state_transition_cases.expand_traced(
        ROOT, limit=len(state["matrixRows"])
    )
    expanded_game_end, _ = checker.expand_game_end_cases.expand_traced(
        ROOT, limit=len(game_end["decisionRows"])
    )
    return mapping, fixtures, state, expanded_state, expanded_game_end


def _entry(mapping: dict[str, Any], branch_id: str) -> dict[str, Any]:
    """分岐IDに対応する宣言を得る。"""
    return next(entry for entry in mapping["mappings"] if entry["branchId"] == branch_id)


def test_repository_matches_all_twenty_positive_and_eleven_negative_branches() -> None:
    """20件の完全一致と11件の違反集合を確認する。"""
    mapping = _read("branch_row_mapping_v1.json")
    matched, violations = checker.check_repository(ROOT)
    assert matched == mapping["expectedPositiveMatches"]
    assert len(violations) == mapping["expectedNegativeMatches"]
    assert violations["XC-10"] == _entry(mapping, "XC-10")["expectedViolationIds"]


@pytest.mark.parametrize("change", ["missing", "zero", "duplicate", "input", "expected"])
def test_positive_comparison_fails_closed(change: str) -> None:
    """欠落・0件・重複・1フィールド不一致を拒否する。"""
    mapping, fixtures, state, expanded_state, expanded_game_end = _inputs()
    positive = next(item["case"] for item in fixtures if item["case"]["branchId"] == "SO-01")
    if change == "missing":
        expanded_state = [
            case for case in expanded_state
            if case["rowRef"] != _entry(mapping, "SO-01")["rowRef"]
        ]
    elif change == "zero":
        expanded_state = []
        expanded_game_end = []
    elif change == "duplicate":
        expanded_state.append(copy.deepcopy(expanded_state[0]))
    elif change == "input":
        positive["inputCoordinate"]["state.outs"] = 1
    else:
        positive["expected"]["outEffect"]["count"] = 2
    with pytest.raises(checker.FixtureParityError):
        checker.check_documents(mapping, fixtures, state, expanded_state, expanded_game_end)


def test_negative_candidate_is_absent_from_expansion() -> None:
    """負例候補が展開結果に混入したら拒否する。"""
    mapping, fixtures, state, expanded_state, expanded_game_end = _inputs()
    negative = next(item["case"] for item in fixtures if item["case"]["branchId"] == "XC-01")
    candidate = copy.deepcopy(expanded_state[0])
    candidate["rowRef"] = {"layer": "matrixRows", "coordinate": {"synthetic": True}}
    candidate["inputCoordinate"] = {
        key: value for key, value in negative["inputCoordinate"].items()
        if key != "candidateEffects"
    }
    candidate["expected"] = copy.deepcopy(negative["inputCoordinate"]["candidateEffects"])
    expanded_state.append(candidate)
    with pytest.raises(checker.FixtureParityError, match="展開器が負例候補を出力した"):
        checker.check_documents(mapping, fixtures, state, expanded_state, expanded_game_end)


def test_rejected_by_must_be_in_actual_violation_set() -> None:
    """宣言IDが違反集合に無い場合を拒否する。"""
    mapping, fixtures, state, expanded_state, expanded_game_end = _inputs()
    negative = next(item["case"] for item in fixtures if item["case"]["branchId"] == "XC-10")
    negative["inputCoordinate"]["candidateEffects"]["outEffect"]["targets"] = [
        "batter", "batter"
    ]
    with pytest.raises(checker.FixtureParityError, match="rejectedByが実際の違反集合にない"):
        checker.check_documents(mapping, fixtures, state, expanded_state, expanded_game_end)


def test_empty_violation_set_is_rejected() -> None:
    """候補がどの交差制約にも拒否されなければ赤にする。"""
    mapping, fixtures, state, expanded_state, expanded_game_end = _inputs()
    negative = next(item["case"] for item in fixtures if item["case"]["branchId"] == "XC-01")
    negative["inputCoordinate"]["candidateEffects"]["batterDestination"]["kind"] = (
        "not-applicable"
    )
    negative["inputCoordinate"]["state.outs"] = 1
    with pytest.raises(checker.FixtureParityError, match="負例候補が拒否されていない"):
        checker.check_documents(mapping, fixtures, state, expanded_state, expanded_game_end)


def test_exact_violation_set_rejects_missing_xc04() -> None:
    """XC-10の同時違反XC-04を宣言から抜くと赤にする。"""
    mapping, fixtures, state, expanded_state, expanded_game_end = _inputs()
    _entry(mapping, "XC-10")["expectedViolationIds"] = ["XC-10"]
    with pytest.raises(checker.FixtureParityError, match="違反集合が不一致"):
        checker.check_documents(mapping, fixtures, state, expanded_state, expanded_game_end)


@pytest.mark.parametrize(
    ("script", "contract", "rows"),
    [
        ("expand_state_transition_cases.py", "state_transition_contract_v1.json", "matrixRows"),
        ("expand_game_end_cases.py", "game_end_contract_v1.json", "decisionRows"),
    ],
)
def test_expansion_is_bit_identical_across_hash_seeds(
    script: str, contract: str, rows: str
) -> None:
    """異なるハッシュシードの別プロセスで全件展開のstdoutがbit一致する。"""
    limit = len(_read(contract)[rows])
    outputs: list[bytes] = []
    for seed in ("11", "97"):
        environment = {**os.environ, "PYTHONHASHSEED": seed}
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / script), "--limit", str(limit)],
            cwd=ROOT, env=environment, check=True, capture_output=True,
        )
        outputs.append(result.stdout)
    assert outputs[0] == outputs[1]
