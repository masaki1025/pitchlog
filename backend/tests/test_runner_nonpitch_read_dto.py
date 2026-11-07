"""唯一物理mapperのRunner NP八形をv3公開行の閉型へ照合する。"""

import copy
import json
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError
from test_runner_event_play_export_identity import _source

from pitchlog.api.schemas.started_games import (
    LineupNonPitchPlayRow,
    LineupPrefixPageItem,
    LineupRunnerNonPitchPlayRow,
    RecordedPrefixPlayRow,
)
from pitchlog.sync.ordinary_pitch_payload import OrdinaryPitchParticipants
from pitchlog.sync.ordinary_pitch_physical import pitch_physical_row
from pitchlog.sync.terminal_pitch_payload import RunnerNonpitchPlayObservations

_FIXTURE = Path(__file__).parent / "fixtures/runner_nonpitch_public_rows_v1.json"
_EVENTS = (
    "strategy-category.steal",
    "pitcher-pickoff-destination.first",
    "pitcher-pickoff-destination.second",
    "pitcher-pickoff-destination.third",
    "catcher-pickoff-destination.first",
    "catcher-pickoff-destination.second",
    "catcher-pickoff-destination.third",
    "secondary-result.balk",
)
_PRIVATE_COLUMNS = (
    "tenant_id",
    "hidden_at",
    "import_batch_id",
    "legacy_row_identifier",
    "migration_unverified",
    "course_x",
    "course_y",
)


def _mapper_rows():
    """既観測と唯一mapperだけで公開列を供給し、数学を再計算しない。"""
    pickoff, _ = _source(0)
    balk, _ = _source(5)
    request = pickoff["calculation"]["request"]
    participants = OrdinaryPitchParticipants.model_validate(pickoff["participants"])
    rows = []
    for event in _EVENTS:
        observation = copy.deepcopy(
            balk["observations"]
            if event == "secondary-result.balk"
            else pickoff["observations"]
        )
        if event != "secondary-result.balk":
            per_pitch = observation["runnerObservation"]["perPitch"]
            per_pitch["resultId"] = event
            per_pitch["runnerEventPayload"]["event_kind"] = event
        row = pitch_physical_row(
            RunnerNonpitchPlayObservations.model_validate(observation),
            participants,
            event,
            tenant_id=UUID(request["prefixRef"]["tenantId"]),
            game_id=UUID(request["prefixRef"]["gameId"]),
            source_event_id=UUID(request["playIdentity"]["eventId"]),
            row_id=UUID(request["playIdentity"]["playId"]),
            play_number=1,
        )
        for key in _PRIVATE_COLUMNS:
            del row[key]
        row["course"] = None
        rows.append({"event": event, "play_row": row})
    return rows


def test_shared_eight_rows_match_only_mapper_at_all_public_columns():
    """BE/FE共有fixtureの全8行を唯一mapper出力の35key全値と比較する。"""
    saved = json.loads(_FIXTURE.read_text())
    assert set(saved) == {"source", "rows"}
    assert saved["source"] == "existing-runner-wire-and-pitch_physical_row"
    assert saved["rows"] == _mapper_rows()
    assert [row["event"] for row in saved["rows"]] == list(_EVENTS)
    assert all(len(row["play_row"]) == 35 for row in saved["rows"])


@pytest.mark.parametrize("case", json.loads(_FIXTURE.read_text())["rows"])
def test_only_v3_page_accepts_runner_np_shape(case):
    """旧投球/IW行型を広げず、v3 page itemだけ別variantで受ける。"""
    row = case["play_row"]
    with pytest.raises(ValidationError):
        RecordedPrefixPlayRow.model_validate(row)
    with pytest.raises(ValidationError):
        LineupNonPitchPlayRow.model_validate(row)
    value = LineupRunnerNonPitchPlayRow.model_validate(row)
    assert value.model_dump(mode="json") == row
    original = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "frontend/src/api/fixtures/lineupPrefixGame.recorded.v3.json"
        ).read_text()
    )["value"]["page"]["items"][0]
    original["play_row"] = row
    item = LineupPrefixPageItem.model_validate(original)
    assert type(item.play_row) is LineupRunnerNonPitchPlayRow


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("batting_result_key", "batting-result.ball"),
        ("course", {"unit": "1/263", "x": "1", "y": "1"}),
        ("pitch_type_key", "pitch-type.straight"),
        ("pitch_speed", 0.0),
        ("batted_ball_type", "batted-ball.ground"),
        ("secondary_batting_result_key", "secondary-result.unknown"),
        ("pickoff_type", "unknown"),
        ("pickoff_detail", "unknown"),
        ("unknown", True),
    ),
)
def test_runner_np_unknown_or_observed_pitch_is_closed(field, value):
    """余剰/偽投球/未知語彙をNULL正規化して公開しない。"""
    row = copy.deepcopy(_mapper_rows()[0]["play_row"])
    row[field] = value
    with pytest.raises(ValidationError):
        LineupRunnerNonPitchPlayRow.model_validate(row)


@pytest.mark.parametrize(
    "changes",
    (
        {"pickoff_type": "pitcher"},
        {"pickoff_detail": "first"},
        {
            "pickoff_type": "pitcher",
            "secondary_batting_result_key": "secondary-result.balk",
        },
        {
            "pickoff_detail": "first",
            "secondary_batting_result_key": "secondary-result.balk",
        },
    ),
)
def test_runner_np_never_accepts_half_pickoff_or_mixed_balk(changes):
    """盗塁行から片側牽制や牽制＋ボークを偽造できない。"""
    row = copy.deepcopy(_mapper_rows()[0]["play_row"])
    row.update(changes)
    with pytest.raises(ValidationError):
        LineupRunnerNonPitchPlayRow.model_validate(row)
