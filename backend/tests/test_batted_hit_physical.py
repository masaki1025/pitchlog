"""明示された打球観測だけを全41物理列へ写す境界の回帰。"""

import copy
import json
from uuid import UUID

import pytest

from pitchlog.sync.ordinary_pitch_payload import OrdinaryPitchParticipants
from pitchlog.sync.ordinary_pitch_physical import pitch_physical_row
from pitchlog.sync.terminal_pitch_payload import BattedHitPlayObservations

IDS = [str(UUID(int=i)) for i in range(1, 8)]
RESULTS = [
    "batting-result.single",
    "batting-result.double",
    "batting-result.triple",
    "batting-result.home-run",
]


def raw_observed(result, *, nullable=False):
    """試験記録者の全明示観測。所属確認や保存資格を与えない。"""
    return {
        "pitchTypeKey": "fixture.fastball",
        "course": {"unit": "1/263", "x": "0", "y": "263"},
        "pitchSpeed": {"kmh": "125.5", "outsideRangeConfirmed": False},
        "stance": "3",
        "battingSide": "右",
        "resultId": result,
        "battedBall": {
            "typeKey": None if nullable else "batted.line",
            "strengthKey": None if nullable else "batted.hard",
            "hitX": None if nullable else "0.25",
            "hitY": None if nullable else "0.75",
            "rawFielderPosition": None if nullable else "9",
            "resolvedFielderId": None if nullable else IDS[6],
        },
        "officialScoringPayload": {
            "kind": "no-error",
            "errorCount": "0",
            "fielders": [],
        },
        "interferenceRuling": {"kind": "not-required"},
        "runnerAdvanceOverridesByRunner": {"kind": "not-applied", "overrides": []},
        "thirdOutObservation": {"kind": "none"},
        "thirdOutTimingByRunner": {},
    }


def mapped(raw):
    """同じ製品mapperへ実型の観測と参加者を渡す。"""
    observed = BattedHitPlayObservations.model_validate_json(json.dumps(raw))
    people = OrdinaryPitchParticipants(
        batterId=IDS[3], pitcherId=IDS[4], catcherId=IDS[5], battingOrder="2"
    )
    return pitch_physical_row(
        observed,
        people,
        raw["resultId"],
        tenant_id=UUID(IDS[0]),
        game_id=UUID(IDS[1]),
        source_event_id=UUID(IDS[2]),
        row_id=UUID(IDS[6]),
        play_number=7,
    )


@pytest.mark.parametrize("result", RESULTS)
@pytest.mark.parametrize("nullable", [False, True])
def test_all_41_columns_keep_observations_and_pitch_event(result, nullable):
    """結果/nullable別に全列と原観測の不変を比較し、nullを0や推定野手にしない。"""
    raw = raw_observed(result, nullable=nullable)
    before = copy.deepcopy(raw)
    actual = mapped(raw)
    assert actual == {
        "tenant_id": IDS[0],
        "id": IDS[6],
        "game_id": IDS[1],
        "source_event_id": IDS[2],
        "play_number": 7,
        "batting_order": 2,
        "batter_id": IDS[3],
        "pitcher_id": IDS[4],
        "catcher_id": IDS[5],
        "batting_side": "右",
        "event_kind": "pitch",
        "stance": "3",
        "course_x": 0.0,
        "course_y": 1.0,
        "pitch_type_key": "fixture.fastball",
        "batting_result_key": result,
        "pitch_speed": 125.5,
        "raw_fielder_position": None if nullable else "9",
        "resolved_fielder_id": None if nullable else IDS[6],
        "batted_ball_type": None if nullable else "batted.line",
        "batted_ball_strength": None if nullable else "batted.hard",
        "hit_x": None if nullable else 0.25,
        "hit_y": None if nullable else 0.75,
        "strategy_key": None,
        "strategy_detail_key": None,
        "strategy_result_key": None,
        "batter_status": None,
        "secondary_batting_result_key": None,
        "pickoff_type": None,
        "pickoff_detail": None,
        "error_type": None,
        "raw_error_position": None,
        "resolved_error_player_id": None,
        "press": None,
        "fake_run": None,
        "comment": None,
        "version": 1,
        "hidden_at": None,
        "legacy_row_identifier": None,
        "migration_unverified": False,
        "import_batch_id": None,
    }
    assert len(actual) == 41
    assert raw == before
    assert type(actual["course_x"]) is float and type(actual["course_y"]) is float
    if not nullable:
        assert type(actual["hit_x"]) is float and type(actual["hit_y"]) is float


@pytest.mark.parametrize(
    "value",
    ["-0.1", "1.0001", "263", "NaN", "Infinity", "-Infinity", "-0." + "0" * 400 + "1"],
)
def test_hit_coordinates_do_not_convert_from_screen_units_or_underflow_negative(value):
    """既保存0..1以外はDouble変換前後に拒否し画面正規化を再実装しない。"""
    raw = raw_observed(RESULTS[0])
    raw["battedBall"]["hitX"] = value
    with pytest.raises(ValueError):
        mapped(raw)


def test_result_mismatch_does_not_write_a_different_outcome():
    """数学結果と観測結果を別の行へ変換しない。"""
    raw = raw_observed(RESULTS[0])
    observed = BattedHitPlayObservations.model_validate_json(json.dumps(raw))
    people = OrdinaryPitchParticipants(
        batterId=IDS[3], pitcherId=IDS[4], catcherId=IDS[5], battingOrder="2"
    )
    with pytest.raises(ValueError):
        pitch_physical_row(
            observed,
            people,
            RESULTS[1],
            tenant_id=UUID(IDS[0]),
            game_id=UUID(IDS[1]),
            source_event_id=UUID(IDS[2]),
            row_id=UUID(IDS[6]),
            play_number=7,
        )
