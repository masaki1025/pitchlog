"""毎球CSV球数・回別表示の専用D-1 SQL生成を固定する。"""

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

from pitchlog.domaingen.play_export_score import (
    generate_play_export_score_bundle,
)
from pitchlog.exports.generated.play_export_completion import saved_half_completed

_ROOT = Path(__file__).resolve().parents[2]
_MODEL = "backend/domain/play-export-score.model.json"
_TARGET = "backend/src/pitchlog/exports/generated/play_export_score.sql"
_MANIFEST = "backend/domain/play-export-score.manifest.json"


def test_score_generation_is_exact_and_does_not_change_t5_model():
    """既T5の全byteと専用D-1 target/台帳を相互照合する。"""
    query, manifest = generate_play_export_score_bundle()
    assert (_ROOT / _TARGET).read_text() == query
    assert json.loads((_ROOT / _MANIFEST).read_text()) == manifest
    assert manifest["t5ModelUnchanged"] is True
    assert set(manifest["generatedFiles"]) == {
        _TARGET,
        "backend/src/pitchlog/exports/generated/play_export_completion.py",
    }
    assert "canonical_s" in query
    assert "c.source_state='included'" in query
    assert "sync_fence.stats_primitive_facts" in query
    assert "SUM(CASE WHEN half='top' THEN away_runs ELSE home_runs END)" in query
    assert "pg_catalog.generate_series(1,12)" in query
    assert "LEAST(inning,12)" in query
    assert "'unplayed'" in query and "'in-progress'" in query


@pytest.mark.parametrize(
    "field,value",
    [
        ("legacyInningSlots", 9),
        ("legacyOverflow", "truncate"),
        ("startedZero", "zero"),
        ("completeProfiles", "client-guess"),
    ],
)
def test_score_declaration_rejects_unknown_coverage(field, value):
    """12回超の切捨て・未完0補完・端末推測を許可しない。"""
    model = copy.deepcopy(json.loads((_ROOT / _MODEL).read_text()))
    model["scoreboard"][field] = value
    schema = json.loads(
        (_ROOT / "backend/domain/play-export-score.schema.json").read_text()
    )
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(model)


def test_independent_saved_t1_counter_example_is_nonzero():
    """既保存契約の三振例はscoreboard差分1と球数1である。"""
    cases = json.loads(
        (
            _ROOT
            / "contracts/state-transition/lineup_play_prefix_payload_vectors_v1.json"
        ).read_text()
    )["cases"]
    case = next(item for item in cases if item["caseId"] == "V3-STRIKEOUT-1-B0-O0")
    source = case["V7"]["calculation"]
    before = source["request"]["t1"]["before"]["scoreboard"]
    after = source["response"]["value"]["t1"]["after"]["scoreboard"]
    assert (before["strikeouts"], after["strikeouts"]) == ("11", "12")


def test_saved_completion_profiles_are_finite_and_do_not_guess_missing_values():
    """初球・通常・v3の既T2差異と欠測拒否を同じ生成器で照合する。"""
    first_cases = json.loads(
        (
            _ROOT / "backend/tests/fixtures/first_ball_payload_vectors_v1.json"
        ).read_text()
    )["cases"]
    first = json.loads(next(row["v7Json"] for row in first_cases if "v7Json" in row))
    assert saved_half_completed(first) is False
    ordinary = copy.deepcopy(first)
    ordinary["formatVersion"] = "ordinary-pitch-play-v1"
    ordinary["calculation"]["formatVersion"] = "ordinary-pitch-calculation-v1"
    ordinary["calculation"]["response"]["value"]["t2"] = {
        "kind": "evaluated-no-end-condition",
        "scope": "ordinary37",
        "basis": {"halfCompleted": False},
    }
    assert saved_half_completed(ordinary) is False
    ordinary["calculation"]["response"]["value"]["t2"]["basis"]["halfCompleted"] = True
    with pytest.raises(ValueError):
        saved_half_completed(ordinary)
    v3 = copy.deepcopy(ordinary)
    v3["formatVersion"] = "play-prefix-play-v3"
    v3["calculation"]["formatVersion"] = "play-prefix-calculation-v3"
    v3["calculation"]["response"]["value"]["t2"] = {
        "kind": "evaluated-end-condition",
        "scope": "play-prefix-v3",
        "facts": {"halfCompleted": True},
    }
    assert saved_half_completed(v3) is True
    del v3["calculation"]["response"]["value"]["t2"]["facts"]
    with pytest.raises(ValueError):
        saved_half_completed(v3)
