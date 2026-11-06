"""v3申告敬遠GETの公開行だけを非投球閉型へ接ぐ。"""

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from pitchlog.api.schemas.started_games import (
    LineupNonPitchPlayRow,
    LineupPrefixPageItem,
    RecordedPrefixPlayRow,
)

ROOT = Path(__file__).resolve().parents[2]


def _item() -> dict[str, Any]:
    """既保存v3 DTOの構造を非投球行へ限定置換する。数学期待は作らない。"""
    fixture = json.loads(
        (
            ROOT / "frontend/src/api/fixtures/lineupPrefixGame.recorded.v3.json"
        ).read_text()
    )
    item = copy.deepcopy(fixture["value"]["page"]["items"][0])
    item["play_row"].update(
        event_kind="non_pitch",
        batting_result_key="batting-result.intentional-walk",
        course=None,
        pitch_type_key=None,
    )
    return item


def test_only_v3_page_accepts_exact_intentional_walk_nonpitch_row():
    """旧pitch公開型は不変、v3 itemだけ識別値を厳格受理する。"""
    item = _item()
    with pytest.raises(ValidationError):
        RecordedPrefixPlayRow.model_validate(item["play_row"])
    value = LineupPrefixPageItem.model_validate(item)
    assert type(value.play_row) is LineupNonPitchPlayRow
    assert value.play_row.course is None
    assert value.play_row.pitch_type_key is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("course", {"unit": "1/263", "x": "132", "y": "131"}),
        ("pitch_type_key", "fastball"),
        ("pitch_speed", 100.0),
        ("stance", "1"),
        ("batting_side", "右"),
        ("batted_ball_type", "line"),
        ("event_kind", "pitch"),
        ("batting_result_key", "batting-result.unknown"),
        ("unknown", True),
    ],
)
def test_nonpitch_page_rejects_pitch_observation_unknown_or_wrong_tag(field, value):
    """申告敬遠に偽投球や未知非投球を混ぜて公開しない。"""
    item = _item()
    item["play_row"][field] = value
    with pytest.raises(ValidationError):
        LineupPrefixPageItem.model_validate(item)
