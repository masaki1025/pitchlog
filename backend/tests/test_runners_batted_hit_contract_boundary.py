"""複数走者の明示観測とbefore物理行を、正式pin更新前に閉検査する。"""

import copy
import json
from pathlib import Path
from uuid import UUID

import pytest

from pitchlog.domainrt.lineup_play_prefix_continuation import (
    T1,
    BattedHitT1Input,
    Runner,
    T1Input,
)
from pitchlog.domainrt.lineup_prefix_source import require_batted_hit_observations
from pitchlog.sync.ordinary_pitch_execution import OrdinaryPitchExecutionError
from pitchlog.sync.terminal_pitch_payload import BattedHitPlayObservations
from pitchlog.sync.terminal_pitch_projection import runner_physical_rows

ROOT = Path(__file__).resolve().parents[2]
CASE = json.loads(
    (ROOT / "contracts/state-transition/batted_hit_prefix_cases_v1.json").read_text()
)["cases"][0]
RUNNER = {
    "runnerId": "10000000-0000-0000-0000-000000000065",
    "responsiblePitcherId": "10000000-0000-0000-0000-0000000000d2",
    "base": "1",
    "status": "継続",
    "statusSource": "auto",
}


def _t1_input(override):
    """固定caseの数学入力だけを変更し、真正DB資格を作らない。"""
    raw = copy.deepcopy(CASE["request"]["t1"])
    raw["before"]["stateFields"]["state.runners"] = "first-second"
    raw["runnerAdvanceOverrides"] = override
    return BattedHitT1Input.model_validate_json(json.dumps(raw))


def _observations(override):
    """V7観測の全必須欄を記録者の原値として供給する。"""
    raw = {
        "pitchTypeKey": "fixture.fastball",
        "course": {"unit": "1/263", "x": "132", "y": "131"},
        "pitchSpeed": {"kmh": None, "outsideRangeConfirmed": False},
        "stance": None,
        "battingSide": None,
        "resultId": CASE["request"]["t1"]["resultId"],
        "battedBall": {
            "typeKey": None,
            "strengthKey": None,
            "hitX": None,
            "hitY": None,
            "rawFielderPosition": None,
            "resolvedFielderId": None,
        },
        "officialScoringPayload": {
            "kind": "no-error",
            "errorCount": "0",
            "fielders": [],
        },
        "interferenceRuling": {"kind": "not-required"},
        "runnerAdvanceOverridesByRunner": override,
        "thirdOutObservation": {"kind": "none"},
        "thirdOutTimingByRunner": {},
    }
    return BattedHitPlayObservations.model_validate_json(json.dumps(raw))


def test_applied_two_runner_observation_matches_t1_exactly():
    """走者別到達の原値が数学/V7間で一致した場合だけ受け付ける。"""
    applied = {
        "kind": "applied",
        "overrides": [
            {"runnerBase": "1", "destination": "3"},
            {"runnerBase": "2", "destination": "4"},
        ],
    }
    t1 = _t1_input(applied)
    require_batted_hit_observations(t1, _observations(applied))
    mismatched = {
        "kind": "applied",
        "overrides": [
            {"runnerBase": "1", "destination": "2"},
            {"runnerBase": "2", "destination": "4"},
        ],
    }
    with pytest.raises(ValueError):
        require_batted_hit_observations(t1, _observations(mismatched))


@pytest.mark.parametrize(
    "override",
    [
        {"kind": "applied", "overrides": []},
        {"kind": "applied", "overrides": [{"runnerBase": "4", "destination": "4"}]},
        {"kind": "applied", "overrides": [{"runnerBase": "1", "destination": "1"}]},
    ],
)
def test_applied_runner_wire_rejects_empty_and_out_of_range(override):
    """未確認の空配列・不在塁番号・後退値を型境界で受け付けない。"""
    with pytest.raises(ValueError):
        _t1_input(override)


def test_physical_runner_row_keeps_before_base_when_t1_moves():
    """after進塁をbeforeのplay_runners列へ転記しない。"""
    raw = copy.deepcopy(CASE["expected"]["value"]["t1"])
    raw["runnerDefaultAdvance"]["first"] = {
        "modality": "forced",
        "destination": "3",
    }
    t1 = T1.model_validate_json(json.dumps(raw))
    tenant = UUID("10000000-0000-0000-0000-000000000001")
    play = UUID("10000000-0000-0000-0000-000000000002")
    rows = runner_physical_rows(
        (Runner.model_validate_json(json.dumps(RUNNER)),),
        t1=t1,
        t1_input=_t1_input(
            {"kind": "applied", "overrides": [{"runnerBase": "1", "destination": "3"}]}
        ),
        tenant_id=tenant,
        play_id=play,
    )
    assert len(rows) == 1
    assert rows[0]["base"] == 1
    assert rows[0]["runner_id"] == RUNNER["runnerId"]
    assert rows[0]["responsible_pitcher_id"] == RUNNER["responsiblePitcherId"]
    assert (rows[0]["status"], rows[0]["status_source"]) == ("三進", "manual")
    with pytest.raises(OrdinaryPitchExecutionError):
        runner_physical_rows(
            (Runner.model_validate_json(json.dumps(RUNNER)),),
            t1=t1,
            t1_input=_t1_input(
                {
                    "kind": "applied",
                    "overrides": [{"runnerBase": "1", "destination": "2"}],
                }
            ),
            tenant_id=tenant,
            play_id=play,
        )
    raw["runnerDefaultAdvance"]["first"] = {
        "modality": "not-applicable",
        "destination": None,
    }
    with pytest.raises(OrdinaryPitchExecutionError):
        runner_physical_rows(
            (Runner.model_validate_json(json.dumps(RUNNER)),),
            t1=T1.model_validate_json(json.dumps(raw)),
            t1_input=_t1_input(
                {
                    "kind": "applied",
                    "overrides": [{"runnerBase": "1", "destination": "3"}],
                }
            ),
            tenant_id=tenant,
            play_id=play,
        )


def test_so05_two_out_wire_is_exact_batter_and_first_runner():
    """一死一塁代表行の2アウト以外を閉wireへ混ぜない。"""
    raw = copy.deepcopy(CASE["expected"]["value"]["t1"])
    raw["outEffect"] = {"count": "2", "targets": ["batter", {"runner": "1"}]}
    result = T1.model_validate_json(json.dumps(raw))
    assert result.out_effect.count == "2"
    input_raw = copy.deepcopy(CASE["request"]["t1"])
    input_raw["resultId"] = "batting-result.strikeout-double-play"
    input_raw = {
        key: input_raw[key]
        for key in ("eventKind", "resultId", "pitchEventKind", "before")
    }
    with pytest.raises(OrdinaryPitchExecutionError):
        runner_physical_rows(
            (Runner.model_validate_json(json.dumps(RUNNER)),),
            t1=result,
            t1_input=T1Input.model_validate_json(json.dumps(input_raw)),
            tenant_id=UUID("10000000-0000-0000-0000-000000000001"),
            play_id=UUID("10000000-0000-0000-0000-000000000002"),
        )
    for effect in (
        {"count": "2", "targets": ["batter"]},
        {"count": "2", "targets": ["batter", {"runner": "2"}]},
        {"count": "3", "targets": ["batter", {"runner": "1"}]},
    ):
        damaged = copy.deepcopy(raw)
        damaged["outEffect"] = effect
        with pytest.raises(ValueError):
            T1.model_validate_json(json.dumps(damaged))


def test_loaded_forced_reach_keeps_all_three_before_physical_rows():
    """満塁押し出しはT1の強制進塁後も3走者の起点物理行を保つ。"""
    raw = copy.deepcopy(CASE["expected"]["value"]["t1"])
    for base, slot, destination in (
        ("1", "first", "2"),
        ("2", "second", "3"),
        ("3", "third", "4"),
    ):
        raw["runnerDefaultAdvance"][slot] = {
            "modality": "forced",
            "destination": destination,
        }
    t1 = T1.model_validate_json(json.dumps(raw))
    runners = tuple(
        Runner.model_validate_json(
            json.dumps(
                {
                    **RUNNER,
                    "runnerId": f"10000000-0000-0000-0000-{base:012d}",
                    "base": str(base),
                }
            )
        )
        for base in (2, 1, 3)
    )
    tenant = UUID("10000000-0000-0000-0000-000000000001")
    play = UUID("10000000-0000-0000-0000-000000000002")
    rows = runner_physical_rows(
        runners,
        t1=t1,
        t1_input=_t1_input(
            {
                "kind": "applied",
                "overrides": [
                    {"runnerBase": "1", "destination": "2"},
                    {"runnerBase": "2", "destination": "3"},
                    {"runnerBase": "3", "destination": "4"},
                ],
            }
        ),
        tenant_id=tenant,
        play_id=play,
    )
    assert len(rows) == 3
    assert [row["base"] for row in rows] == [1, 2, 3]
    assert [(row["status"], row["status_source"]) for row in rows] == [
        ("二進", "manual"),
        ("三進", "manual"),
        ("本進", "manual"),
    ]
    assert {row["base"]: row["runner_id"] for row in rows} == {
        1: runners[1].runner_id,
        2: runners[0].runner_id,
        3: runners[2].runner_id,
    }


def test_forced_reach_without_manual_override_keeps_auto_origin():
    """四死球型のT1強制進塁は手動上書きと混同しない。"""
    raw = copy.deepcopy(CASE["expected"]["value"]["t1"])
    raw["runnerDefaultAdvance"]["first"] = {
        "modality": "forced",
        "destination": "2",
    }
    input_raw = copy.deepcopy(CASE["request"]["t1"])
    input_raw["resultId"] = "batting-result.walk"
    input_raw = {
        key: input_raw[key]
        for key in ("eventKind", "resultId", "pitchEventKind", "before")
    }
    row = runner_physical_rows(
        (Runner.model_validate_json(json.dumps(RUNNER)),),
        t1=T1.model_validate_json(json.dumps(raw)),
        t1_input=T1Input.model_validate_json(json.dumps(input_raw)),
        tenant_id=UUID("10000000-0000-0000-0000-000000000001"),
        play_id=UUID("10000000-0000-0000-0000-000000000002"),
    )[0]
    assert (row["base"], row["status"], row["status_source"]) == (1, "二進", "auto")
