"""88列の保存原本直写しを旧物理見出しと新しい表示証拠へ照合する。"""

import json
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, cast
from uuid import UUID

import pytest

from pitchlog.db.game_state.models import PlayRow
from pitchlog.exports.play_rows import CSV_HEADERS
from pitchlog.exports.record_projection import (
    RecordedExportProjectionUnavailable,
    _input_origin,
    _native_before,
    project_recorded_direct,
)
from pitchlog.sync.play_export_identity import RecordedPlayIdentity
from pitchlog.sync.stats_native_hook import _NativeStatsSource

TENANT = UUID(int=1)
GAME = UUID(int=2)
SOURCE = UUID(int=3)
PLAY = UUID(int=4)
BATTER = UUID(int=5)
PITCHER = UUID(int=6)
CATCHER = UUID(int=7)
AWAY = UUID(int=8)
HOME = UUID(int=9)


def _identity():
    """資格試験ではない有限表示入力を作る。"""
    source = _NativeStatsSource(
        TENANT,
        GAME,
        1,
        1,
        1,
        UUID(int=10),
        SOURCE,
        "a" * 64,
        "{}",
        "b" * 64,
        UUID(int=11),
        UUID(int=12),
        b"x" * 32,
    )
    game = {
        "tenant_id": TENANT,
        "id": GAME,
        "scheduled_at": datetime(2026, 11, 7, tzinfo=timezone.utc),
        "started_at": datetime(2026, 11, 7, 1, 2, 3, tzinfo=timezone.utc),
        "section_label": "秋季",
        "tournament_key": "tournament.league",
        "week_label": None,
        "day_label": None,
        "game_number_label": None,
        "plate_umpire": None,
        "home_team_record_id": HOME,
        "away_team_record_id": AWAY,
    }
    play = {
        column.name: None
        for column in PlayRow.__table__.c
        if column.info.get("legacy_source_columns")
    }
    play.update(
        {
            "tenant_id": TENANT,
            "source_event_id": SOURCE,
            "play_number": 1,
            "batting_order": 1,
            "batter_id": BATTER,
            "pitcher_id": PITCHER,
            "catcher_id": CATCHER,
            "event_kind": "pitch",
            "batting_result_key": "strikeout_looking",
            "raw_error_position": "7",
            "comment": "記録時コメント",
        }
    )
    away_ids = [BATTER, *(UUID(int=100 + index) for index in range(2, 10))]
    home_ids = [PITCHER, CATCHER, *(UUID(int=200 + index) for index in range(3, 10))]
    players = (
        {"id": BATTER, "name": "当時打者", "uniform_number": "007", "bats": "右"},
        {
            "id": PITCHER,
            "name": "当時投手",
            "uniform_number": "01",
            "throws": "左",
            "bats": "右",
        },
        {"id": CATCHER, "name": "当時捕手", "uniform_number": "02", "bats": "右"},
        *(
            {
                "id": identifier,
                "name": f"先攻{index}",
                "uniform_number": str(index),
                "bats": "右",
            }
            for index, identifier in enumerate(away_ids[1:], start=2)
        ),
        *(
            {
                "id": identifier,
                "name": f"後攻{index}",
                "uniform_number": str(index),
                "bats": "右",
            }
            for index, identifier in enumerate(home_ids[2:], start=3)
        ),
    )
    lineups = cast(
        tuple[dict[str, Any], dict[str, Any]],
        tuple(
            {
                "team_record_id": team,
                "entries_with_uniform_number_snapshot": [
                    {
                        "player_id": str(identifier),
                        "batting_order": index,
                        "fielding_position": {
                            "kind": "fielding",
                            "position": (
                                3
                                if side == "away" and index == 1
                                else 1
                                if side == "away" and index == 3
                                else index
                            ),
                        },
                        "uniform_number_snapshot": "007"
                        if identifier == BATTER
                        else "01"
                        if identifier == PITCHER
                        else "02"
                        if identifier == CATCHER
                        else str(index),
                    }
                    for index, identifier in enumerate(identifiers, start=1)
                ],
            }
            for side, team, identifiers in (
                ("away", AWAY, away_ids),
                ("home", HOME, home_ids),
            )
        ),
    )
    return RecordedPlayIdentity(
        source,
        game,
        play,
        lineups,
        players,
        ({"id": AWAY, "name": "先攻名"}, {"id": HOME, "name": "後攻名"}),
        ({"key": "tournament.league", "display_name": "リーグ戦"},),
        ({"key": "strikeout_looking", "display_name": "見逃し三振"},),
        {"display_name": "公式戦"},
        {
            "formatVersion": "play-prefix-play-v3",
            "observations": {"pitchSpeed": {"kmh": None}},
            "calculation": {
                "formatVersion": "play-prefix-calculation-v3",
                "artifactSha256": "c" * 64,
                "request": {
                    "source": {"kind": "evaluated-prefix-v3"},
                    "t1": {
                        "before": {
                            "battingOrderBySide": {"away": "1", "home": "5"},
                            "stateFields": {
                                "state.half": "top",
                                "state.inning": "1",
                                "state.score": {"away": "0", "home": "0"},
                                "state.count.strikes": "2",
                                "state.count.balls": "1",
                                "state.outs": "0",
                            },
                        }
                    },
                },
                "response": {
                    "value": {
                        "t1": {
                            "plateAppearanceEnded": True,
                            "after": {"stateFields": {"state.gameEnded": False}},
                        },
                        "t2": {
                            "kind": "evaluated-end-condition",
                            "scope": "play-prefix-v3",
                            "facts": {"halfCompleted": False},
                        },
                    }
                },
            },
        },
        ("132", "197"),
        datetime(2026, 11, 7, 1, 2, 4, tzinfo=timezone.utc),
    )


def test_recorded_direct_values_keep_old_header_and_real_meaning():
    """55/60の歴史見出しへ実値を置き、チーム7/8を取り違えない。"""
    values = project_recorded_direct(_identity())
    assert values["タイムの種類"] == "7"
    assert values["打席Id"] == "記録時コメント"
    assert values["後攻チーム"] == "後攻名"
    assert values["先攻チーム"] == "先攻名"
    assert values["コースX"] == "132"
    assert values["コースY"] == "197"
    assert values["打者番号"] == "007"
    assert values["投手番号"] == "01"
    assert values["Kind"] == "リーグ戦"
    assert (values["先攻打順"], values["後攻打順"]) == ("1", "5")
    assert values["投手左右"] == "左"
    assert values["打者位置"] == "1B"
    top_names, top_nums = values["top_names"], values["top_nums"]
    assert isinstance(top_names, str) and isinstance(top_nums, str)
    assert json.loads(top_names)[0] == "当時打者"
    assert json.loads(top_nums)[0] == "007"
    assert values["プレイの種類"] == "投球"
    assert (values["打席結果"], values["Result_col"]) == ("見三振", "見三振")
    assert values["経過時間"] == "0:00"
    assert values["現在時刻"] == "10:02:04"
    origin = values["入力項目"]
    assert isinstance(origin, str)
    assert json.loads(origin)["sourceEventId"] == str(SOURCE)
    assert values["打球位置X"] is None
    assert values["打球位置Y"] is None
    assert values["球速"] is None
    assert [values[key] for key in ("打席の継続", "イニング継続", "試合継続")] == [
        "打席完了",
        "イニング継続",
        "試合継続",
    ]
    assert [
        values[key]
        for key in ("回", "表.裏", "先攻得点", "後攻得点", "S", "B", "アウト")
    ] == ["1", "表", "0", "0", "2", "1", "0"]
    assert set(values) == {
        header
        for index, header in enumerate(CSV_HEADERS["plays.csv"])
        if index not in (34, 86, 87)
    }
    identity = _identity()
    identity.play["play_number"] = 2
    assert project_recorded_direct(identity)["top_names"] is None


def test_first_half_legacy_order_uses_saved_active_and_started_inactive_only():
    """旧初球・通常の表1回だけ開始済み裏打順を1へ束縛する。"""
    identity = _identity()
    payload = identity.payload
    payload["formatVersion"] = "first-ball-play-v1"
    before = payload["calculation"]["request"]["t1"]["before"]
    before.pop("battingOrderBySide")
    before["stateFields"]["state.battingOrder"] = "2"
    result = _native_before(payload)
    assert (result["先攻打順"], result["後攻打順"]) == ("2", "1")
    before["stateFields"]["state.half"] = "bottom"
    with pytest.raises(RecordedExportProjectionUnavailable):
        _native_before(payload)


def test_foreign_or_missing_historical_reference_is_rejected():
    """別試合sourceや名簿欠測を現在名で補わない。"""
    identity = _identity()
    identity.game["id"] = UUID(int=99)
    with pytest.raises(RecordedExportProjectionUnavailable):
        project_recorded_direct(identity)
    identity.game["id"] = GAME
    identity.play["batter_id"] = UUID(int=99)
    with pytest.raises(RecordedExportProjectionUnavailable):
        project_recorded_direct(identity)


def test_walkoff_finished_play_is_not_rejected_as_inning_guard():
    """裏攻撃中の終了は半回完了フラグを必須としない。"""
    identity = _identity()
    value = identity.payload["calculation"]["response"]["value"]
    value["t1"]["after"]["stateFields"]["state.gameEnded"] = True
    values = project_recorded_direct(identity)
    assert values["イニング継続"] == "試合終了"
    assert values["試合継続"] == "試合終了"


def test_batted_coordinate_keeps_accepted_normalized_decimal_and_storage_pair():
    """保存値0..1の原字面を残し、別値・片軸は拒否する。"""
    identity = _identity()
    identity.payload["observations"]["battedBall"] = {
        "hitX": "0.250",
        "hitY": "0.75",
    }
    identity.play["hit_x"] = 0.25
    identity.play["hit_y"] = 0.75
    values = project_recorded_direct(identity)
    assert (values["打球位置X"], values["打球位置Y"]) == ("0.250", "0.75")
    identity.play["hit_x"] = 0.5
    with pytest.raises(RecordedExportProjectionUnavailable):
        project_recorded_direct(identity)
    identity.play["hit_x"] = 0.25
    identity.payload["observations"]["battedBall"]["hitY"] = None
    with pytest.raises(RecordedExportProjectionUnavailable):
        project_recorded_direct(identity)


def test_origin_preserves_actual_first_and_v2_profile_without_request_guess():
    """旧正規wireのprofileを新規0flagへ偽装しない。"""
    identity = _identity()
    identity.payload["formatVersion"] = "first-ball-play-v1"
    identity.payload["calculation"]["formatVersion"] = "first-ball-calculation-v1"
    identity.payload["calculation"]["request"].pop("source")
    first = json.loads(_input_origin(identity))
    assert first["sourceFormat"] == "first-ball-play-v1"
    assert "sourceKind" not in first
    identity.payload["formatVersion"] = "play-prefix-play-v2"
    identity.payload["calculation"]["formatVersion"] = "play-prefix-calculation-v2"
    identity.payload["calculation"]["request"]["source"] = {"kind": "bridged-v1"}
    assert json.loads(_input_origin(identity))["sourceKind"] == "bridged-v1"


def test_runner_columns_use_qualified_play_runner_and_historical_name():
    """打順/名前/状況を別塁や現在名で補わない。"""
    identity = _identity()
    runner_id = UUID(int=102)
    identity.payload["calculation"]["request"]["source"]["lineup"] = {
        "away": {"battingOrder": {"2": str(runner_id)}}
    }
    identity = replace(
        identity,
        runners=(
            {
                "base": 1,
                "runner_id": runner_id,
                "status": "継続",
                "status_source": "auto",
            },
        ),
    )
    values = project_recorded_direct(identity)
    assert [
        values[key]
        for key in ("一走打順", "一走氏名", "一走状況", "一走登録名", "一走番号")
    ] == ["2", "先攻2", "継続", "先攻2", "2"]
    assert values["二走打順"] is None


def test_pitch_speed_keeps_accepted_decimal_only_when_physical_matches():
    """速度Doubleから原十進字面を丸め直さない。"""
    identity = _identity()
    identity.payload["observations"]["pitchSpeed"]["kmh"] = "142.50"
    identity.play["pitch_speed"] = 142.5
    assert project_recorded_direct(identity)["球速"] == "142.50"
    identity.play["pitch_speed"] = 141.5
    with pytest.raises(RecordedExportProjectionUnavailable):
        project_recorded_direct(identity)
