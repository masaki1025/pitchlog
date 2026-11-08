"""凡打追加が既走者の固定親と旧4安打の閉条件を保持することを確認する。"""

import copy
import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from pitchlog.authz import first_ball_product
from pitchlog.authz import runner_physical_evidence_sql as runner
from pitchlog.authz.batted_out_evidence_sql import (
    FUNCTION_ID,
    PARENT_SHA256,
    overlay_prepared_parent,
)

_ROOT = Path(__file__).resolve().parents[2]


def test_batted_out_overlay_keeps_pinned_runner_and_all_other_functions():
    """既親を改変せず有限接合し、owner/本文の同時差替えを拒否する。"""
    declaration = next(
        row
        for row in first_ball_product.ADDITIONS["functions"]
        if row["function_id"] == FUNCTION_ID
    )
    raw = first_ball_product._D03_BASELINE_BODIES["function|" + FUNCTION_ID]
    parent = runner.overlay_prepared_parent(raw, declaration)
    assert hashlib.sha256(parent.encode()).hexdigest() == PARENT_SHA256
    result = overlay_prepared_parent(parent, declaration)
    assert result == first_ball_product.BODIES["function|" + FUNCTION_ID]
    assert result.count("runner physical evidence rejected") == parent.count(
        "runner physical evidence rejected"
    )
    assert "batter-before-first" in result
    start = parent.index(" -- 新安打だけの閉分岐。")
    end_marker = "  THEN RAISE EXCEPTION 'batted hit physical source rejected'"
    assert result[:start] == parent[:start]
    assert result[result.index(end_marker) :] == parent[parent.index(end_marker) :]
    with pytest.raises(ValueError, match="親本文"):
        overlay_prepared_parent(parent + "\n", declaration)
    wrong = {**declaration, "owner_role_id": "pitchlog_app"}
    with pytest.raises(ValueError, match="宣言"):
        overlay_prepared_parent(parent, wrong)


@pytest.mark.parametrize(
    "filename",
    ["lineup_play_prefix_schema_v1.json", "lineup_play_prefix_payload_schema_v1.json"],
)
def test_batted_out_schema_preserves_hit_none_and_requires_explicit_third(filename):
    """旧安打へ第三アウトを漏らさず、凡打の前状態と明示入力を照合する。"""
    base = _ROOT / "contracts/state-transition"
    schema = json.loads((base / filename).read_text())
    validator = Draft202012Validator(
        {"$ref": "#/$defs/BattedHitT1Input", "$defs": schema["$defs"]}
    )
    case = json.loads((base / "batted_hit_cases_v1.json").read_text())["cases"][0]
    value = copy.deepcopy(case["request"])
    value.pop("history")
    value["before"]["battingOrderBySide"] = {"away": "1", "home": "1"}
    assert validator.is_valid(value)
    for result in ("single", "double", "triple", "home-run"):
        value["resultId"] = "batting-result." + result
        value["thirdOutObservation"] = "batter-before-first"
        assert not validator.is_valid(value)
    value["resultId"] = "batting-result.batted-out"
    for outs in ("0", "1", "2"):
        value["before"]["stateFields"]["state.outs"] = outs
        value["thirdOutObservation"] = "batter-before-first" if outs == "2" else "none"
        assert validator.is_valid(value)
        value["thirdOutObservation"] = "none" if outs == "2" else "batter-before-first"
        assert not validator.is_valid(value)
    value["before"]["stateFields"]["state.runners"] = "first"
    assert not validator.is_valid(value)
