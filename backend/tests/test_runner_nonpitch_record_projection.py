"""Runner NP の同TX原本をCSV直接列へ写す有限純対向。実認可・実保存ではない。"""

import copy
import json
from dataclasses import replace
from uuid import UUID

import pytest
from test_record_export_direct_projection import _identity
from test_runner_event_play_export_identity import _source

from pitchlog.exports.play_rows import CSV_HEADERS
from pitchlog.exports.record_projection import (
    RecordedExportProjectionUnavailable,
    project_recorded_direct,
)


def _recorded_runner_np(index):
    """既固定Runner観測・唯一物理mapperと保存時表示参照だけを接ぐ。"""
    payload, row = _source(index)
    row = dict(row)
    for field in (
        "tenant_id",
        "game_id",
        "source_event_id",
        "id",
        "batter_id",
        "pitcher_id",
        "catcher_id",
    ):
        row[field] = UUID(row[field])
    source = payload["calculation"]["request"]["source"]["lineup"]
    original = _identity()
    game = dict(original.game)
    game.update(
        tenant_id=row["tenant_id"],
        id=row["game_id"],
        away_team_record_id=UUID(source["away"]["teamId"]),
        home_team_record_id=UUID(source["home"]["teamId"]),
    )
    lineups = []
    players = {}
    for side in ("away", "home"):
        entries = []
        for order, identifier in source[side]["battingOrder"].items():
            player_id = UUID(identifier)
            players[player_id] = {
                "id": player_id,
                "name": f"保存選手{identifier}",
                "uniform_number": order,
                "bats": "右",
                "throws": "右",
            }
            entries.append(
                {
                    "player_id": identifier,
                    "batting_order": int(order),
                    "fielding_position": {"kind": "fielding", "position": int(order)},
                    "uniform_number_snapshot": order,
                }
            )
        pitcher_id = source[side]["pitcherId"]
        if UUID(pitcher_id) not in players:
            players[UUID(pitcher_id)] = {
                "id": UUID(pitcher_id),
                "name": f"保存投手{pitcher_id}",
                "uniform_number": "11",
                "bats": "右",
                "throws": "右",
            }
            entries.append(
                {
                    "player_id": pitcher_id,
                    "batting_order": None,
                    "fielding_position": {"kind": "fielding", "position": 1},
                    "uniform_number_snapshot": "11",
                }
            )
        lineups.append(
            {
                "team_record_id": UUID(source[side]["teamId"]),
                "entries_with_uniform_number_snapshot": entries,
            }
        )
    admin_vocabularies = tuple(
        {"key": key, "display_name": key}
        for key in (row["batting_result_key"], row["secondary_batting_result_key"])
        if key is not None
    )
    return replace(
        original,
        source=replace(
            original.source,
            tenant_id=row["tenant_id"],
            game_id=row["game_id"],
            source_event_id=row["source_event_id"],
        ),
        game=game,
        play=row,
        lineups=tuple(lineups),
        players=tuple(players.values()),
        teams=(
            {"id": UUID(source["away"]["teamId"]), "name": "保存先攻"},
            {"id": UUID(source["home"]["teamId"]), "name": "保存後攻"},
        ),
        admin_vocabularies=admin_vocabularies,
        payload=payload,
        course_screen=(None, None),
    )


@pytest.mark.parametrize(
    ("index", "plate_display"), ((0, None), (1, None), (5, "打席継続"))
)
def test_runner_np_direct_projection_uses_accepted_original_without_pitch_fill(
    index, plate_display
):
    """牽制・ボークの未観測球速と後続display/originを同原本で確認する。"""
    identity = _recorded_runner_np(index)
    before = copy.deepcopy(identity.payload)
    values = project_recorded_direct(identity)
    assert len(values) == 85
    assert set(values) == set(CSV_HEADERS["plays.csv"]) - {
        CSV_HEADERS["plays.csv"][index] for index in (34, 86, 87)
    }
    assert values["プレイの種類"] == "非投球"
    assert values["球速"] is None
    assert values["球種"] is None
    assert values["コースX"] is None and values["コースY"] is None
    assert values["打席の継続"] == plate_display
    assert values["打席結果"] is None and values["Result_col"] is None
    assert values["先攻チーム"] == "保存先攻"
    assert isinstance(values["入力項目"], str)
    origin = json.loads(values["入力項目"])
    assert origin["sourceEventId"] == str(identity.source.source_event_id)
    assert origin["calculationFormat"] == "play-prefix-calculation-v3"
    assert identity.payload == before


@pytest.mark.parametrize(
    "tamper",
    (
        "speed-zero",
        "pitch-type",
        "batted",
        "course",
        "wrong-observation",
        "extra-observation",
        "fake-result",
        "unknown-kind",
        "wrong-origin",
    ),
)
def test_runner_np_cannot_be_repaired_into_success(tamper):
    """未観測の埋め草や本文・物理行の差替えを直接射影で拒否する。"""
    identity = _recorded_runner_np(0)
    payload, row = identity.payload, identity.play
    if tamper == "speed-zero":
        row["pitch_speed"] = 0.0
    elif tamper == "pitch-type":
        row["pitch_type_key"] = "pitch-type.straight"
    elif tamper == "batted":
        row["batted_ball_type"] = "batted-ball.ground"
    elif tamper == "course":
        row["course_x"] = 0.5
    elif tamper == "wrong-observation":
        payload["observations"]["runnerObservation"]["primaryResultId"] = (
            "batting-result.ball"
        )
    elif tamper == "extra-observation":
        payload["observations"]["course"] = None
    elif tamper == "fake-result":
        row["batting_result_key"] = "batting-result.ball"
    elif tamper == "unknown-kind":
        payload["observations"]["kind"] = "unknown"
    else:
        payload["calculation"]["request"]["source"]["kind"] = "unknown"
    with pytest.raises(RecordedExportProjectionUnavailable):
        project_recorded_direct(identity)


@pytest.mark.parametrize(
    "field",
    (
        "pitch_speed",
        "pitch_type_key",
        "course_x",
        "course_y",
        "stance",
        "batting_side",
        "batted_ball_type",
        "batted_ball_strength",
        "hit_x",
        "hit_y",
        "raw_fielder_position",
        "resolved_fielder_id",
    ),
)
def test_intentional_walk_preserves_twelve_null_physical_fields(field):
    """申告敬遠を Runner NP 分岐に広げず、旧12列NULLを維持する。"""
    original = _identity()
    play = dict(original.play)
    play.update(
        event_kind="non_pitch",
        batting_result_key="batting-result.intentional-walk",
        raw_error_position=None,
    )
    payload = copy.deepcopy(original.payload)
    payload["observations"] = {"kind": "intentional-walk"}
    payload["calculation"]["request"]["t1"].update(
        pitchEventKind="non-pitch-event", resultId="batting-result.intentional-walk"
    )
    identity = replace(
        original,
        play=play,
        payload=payload,
        course_screen=(None, None),
        admin_vocabularies=original.admin_vocabularies
        + ({"key": "batting-result.intentional-walk", "display_name": "申告敬遠"},),
    )
    assert project_recorded_direct(identity)["球速"] is None
    play[field] = (
        0.0
        if field in ("pitch_speed", "course_x", "course_y", "hit_x", "hit_y")
        else "偽値"
    )
    with pytest.raises(RecordedExportProjectionUnavailable):
        project_recorded_direct(identity)


def test_intentional_walk_does_not_accept_batted_observation():
    """申告敬遠の原観測に打球欄を足しても非投球成功にしない。"""
    original = _identity()
    play = dict(original.play)
    play.update(
        event_kind="non_pitch", batting_result_key="batting-result.intentional-walk"
    )
    payload = copy.deepcopy(original.payload)
    payload["observations"] = {"kind": "intentional-walk"}
    payload["calculation"]["request"]["t1"].update(
        pitchEventKind="non-pitch-event", resultId="batting-result.intentional-walk"
    )
    identity = replace(original, play=play, payload=payload, course_screen=(None, None))
    payload["observations"]["battedBall"] = None
    with pytest.raises(RecordedExportProjectionUnavailable):
        project_recorded_direct(identity)
