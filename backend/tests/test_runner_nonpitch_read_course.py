"""非投球の未観測courseをnormal/P3共通の公開射影へ写す。"""

import json
from types import SimpleNamespace

import pytest
from test_runner_nonpitch_row_operations import _OPERATIONS, _fixture
from test_terminal_pitch_payload import values

from pitchlog.repositories.ordinary_prefix_read import (
    OrdinaryPrefixError,
    _play_observation_course,
    _public_play,
)
from pitchlog.sync.nonpitch_payload import IntentionalWalkObservations
from pitchlog.sync.terminal_pitch_payload import LineupPitchPlayPayload


@pytest.mark.parametrize("operation", _OPERATIONS)
def test_closed_runner_nonpitch_is_inapplicable_without_inventing_course(operation):
    """既閉payloadを使い、保存6列と公開courseの非該当を確認する。"""
    row, raw = _fixture(operation)
    payload = LineupPitchPlayPayload.model_validate_json(json.dumps(raw))
    assert not hasattr(payload.observations, "course")
    course = _play_observation_course(payload.observations)
    assert course is None
    shown = _public_play(row, course)
    assert shown["course"] is None
    assert shown["event_kind"] == "non_pitch"
    assert shown["batting_result_key"] is None
    assert "course_x" not in shown and "course_y" not in shown


def test_existing_pitch_and_intentional_walk_keep_original_observations():
    """投球の元courseと申告敬遠非該当を変更しない。"""
    observed, _, _ = values()
    assert _play_observation_course(observed) is observed.course
    walk = IntentionalWalkObservations.model_validate({"kind": "intentional-walk"})
    assert _play_observation_course(walk) is None


@pytest.mark.parametrize(
    "unknown", [None, {}, {"kind": "non-pitch-event"}, SimpleNamespace(course=None)]
)
def test_unknown_observation_never_becomes_inapplicable(unknown):
    """未知・duck typeを非該当として補完しない。"""
    with pytest.raises(OrdinaryPrefixError):
        _play_observation_course(unknown)
