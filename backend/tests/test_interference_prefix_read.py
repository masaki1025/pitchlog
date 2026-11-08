"""妨害の実保存観測と唯一物理mapperを閉じたv3公開行へ接ぐ。"""

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from test_interference_play_row import _actual

from pitchlog.api.schemas.started_games import (
    LineupInterferencePlayRow,
    LineupPrefixPageItem,
    RecordedPrefixPlayRow,
)
from pitchlog.repositories.ordinary_prefix_read import (
    OrdinaryPrefixError,
    _play_observation_course,
    _public_play,
)
from pitchlog.sync.first_ball_payload import FirstBallObservations
from pitchlog.sync.terminal_pitch_payload import LineupPitchPlayPayload

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("case", ("penalty", "play", "obstruction", "offensive"))
def test_actual_interference_observation_keeps_only_original_course(case):
    """実859評価の4形から原courseだけを公開し、原41列の他値は維持する。"""
    row, raw = copy.deepcopy(_actual(case))
    payload = LineupPitchPlayPayload.model_validate_json(json.dumps(raw))
    assert isinstance(payload.observations, FirstBallObservations)
    course = _play_observation_course(payload.observations)
    assert course == payload.observations.course
    value = _public_play(row, course)
    assert value["secondary_batting_result_key"] == row["secondary_batting_result_key"]
    if case == "play":
        assert (
            type(RecordedPrefixPlayRow.model_validate(value)) is RecordedPrefixPlayRow
        )
        with pytest.raises(ValidationError):
            LineupInterferencePlayRow.model_validate(value)
    else:
        assert value["batting_result_key"] is None
        assert (
            type(LineupInterferencePlayRow.model_validate(value))
            is LineupInterferencePlayRow
        )
        fixture = json.loads(
            (
                ROOT / "frontend/src/api/fixtures/lineupPrefixGame.recorded.v3.json"
            ).read_text()
        )["value"]["page"]["items"][0]
        fixture["play_row"] = value
        assert type(LineupPrefixPageItem.model_validate(fixture).play_row) is (
            LineupInterferencePlayRow
        )
        with pytest.raises(ValidationError):
            RecordedPrefixPlayRow.model_validate(value)


@pytest.mark.parametrize(
    "field,value",
    (
        ("batting_result_key", "batting-result.ball"),
        ("secondary_batting_result_key", "secondary-result.unknown"),
        ("course", None),
        ("pitch_type_key", None),
        ("batted_ball_type", "line"),
    ),
)
def test_interference_public_row_rejects_mutated_source(field, value):
    """主結果・副結果・course・無関係打球列の差替えを拒否する。"""
    row, raw = copy.deepcopy(_actual("penalty"))
    payload = LineupPitchPlayPayload.model_validate_json(json.dumps(raw))
    public = _public_play(row, _play_observation_course(payload.observations))
    public[field] = value
    with pytest.raises(ValidationError):
        LineupInterferencePlayRow.model_validate(public)
    if field in {"batting_result_key", "secondary_batting_result_key"}:
        with pytest.raises(ValidationError):
            RecordedPrefixPlayRow.model_validate(public)


def test_unknown_observation_and_missing_course_do_not_become_success():
    """未知実型と欠測courseを既初球へ読み替えない。"""
    with pytest.raises(OrdinaryPrefixError):
        _play_observation_course(object())
    _, raw = copy.deepcopy(_actual("penalty"))
    del raw["observations"]["course"]
    with pytest.raises(ValidationError):
        LineupPitchPlayPayload.model_validate_json(json.dumps(raw))
