"""RunnerPitch WP/PBの41列を受理原観測へ結ぶ純検査。実frame/DB資格ではない。"""

import copy
from uuid import UUID

import pytest
from test_runner_event_play_export_identity import _source
from test_runner_nonpitch_row_operations import _results, _token

from pitchlog.db.game_state.models import PlayRow
from pitchlog.repositories.ordinary_pitch_operations import (
    PLAY_PREFIX_PLAY_OPERATIONS,
    OrdinaryPlayRowError,
    _runner_pitch_secondary_shape,
)
from pitchlog.sync.ordinary_pitch_tokens import OrdinaryPlayRowInsertToken


def _fixture(index):
    """既候補の唯一mapper行と元payloadを変更せず有限位置だけ合わせる。"""
    payload, row = _source(index)
    row["play_number"] = 101
    assert set(row) == set(PlayRow.__table__.c.keys()) and len(row) == 41
    return row, payload


def _preflight(row, payload):
    """構造tokenのprepareと受理原event/ledgerの純照合を連続実行する。"""
    token = _token(row)
    operation = PLAY_PREFIX_PLAY_OPERATIONS[0]
    _, params = operation.prepare(token)
    assert operation.preflight is not None
    gate = operation.preflight(
        token, {**params, "tenant_id": UUID(row["tenant_id"])}
    )
    gate.validate(_results(row, payload))
    return params


@pytest.mark.parametrize("index", (3, 4))
def test_wp_pb_keep_secondary_and_full_original_before_insert(index):
    """唯一mapperのWP/PB副結果を欠落させず全41列で元イベントに束縛する。"""
    row, payload = _fixture(index)
    params = _preflight(row, payload)
    assert params["secondary_batting_result_key"] == row[
        "secondary_batting_result_key"
    ]
    assert params["batting_result_key"] == "batting-result.ball"
    assert params["event_kind"] == "pitch"


@pytest.mark.parametrize("index", (2, 6))
def test_other_existing_runner_pitch_keeps_full_original_check(index):
    """K併殺/通常ballの既経路を閉じず、原参加者差替えは拒否する。"""
    row, payload = _fixture(index)
    _preflight(row, payload)
    altered = copy.deepcopy(row)
    altered["batter_id"] = str(UUID(int=77))
    with pytest.raises(OrdinaryPlayRowError):
        _preflight(altered, payload)


@pytest.mark.parametrize(
    "mutation",
    (
        "missing-secondary",
        "other-secondary",
        "wrong-primary",
        "wrong-participant",
        "wrong-source-event",
        "wrong-play-id",
        "wrong-d5",
        "wrong-tenant",
        "missing-observation",
        "different-observation",
        "extra-payload",
    ),
)
def test_wp_pb_row_or_original_difference_cannot_pass_preflight(mutation):
    """元eventの副結果・識別子・観測を欠落/差替えで成功化しない。"""
    row, payload = _fixture(3)
    if mutation == "missing-secondary":
        row["secondary_batting_result_key"] = None
    elif mutation == "other-secondary":
        row["secondary_batting_result_key"] = "secondary-result.passed-ball"
    elif mutation == "wrong-primary":
        row["batting_result_key"] = "batting-result.called-pitch"
    elif mutation == "wrong-participant":
        row["batter_id"] = str(UUID(int=77))
    elif mutation == "wrong-source-event":
        payload["calculation"]["request"]["playIdentity"]["eventId"] = str(
            UUID(int=77)
        )
    elif mutation == "wrong-play-id":
        payload["calculation"]["request"]["playIdentity"]["playId"] = str(
            UUID(int=77)
        )
    elif mutation == "wrong-d5":
        payload["calculation"]["request"]["playIdentity"]["d5"] = str(
            UUID(int=77)
        )
    elif mutation == "wrong-tenant":
        payload["calculation"]["request"]["prefixRef"]["tenantId"] = str(
            UUID(int=77)
        )
    elif mutation == "missing-observation":
        del payload["observations"]["runnerObservation"]
    elif mutation == "different-observation":
        payload["observations"]["runnerObservation"]["primaryResultId"] = (
            "batting-result.called-pitch"
        )
    else:
        payload["extra"] = True
    with pytest.raises(OrdinaryPlayRowError):
        _preflight(row, payload)


@pytest.mark.parametrize(
    ("primary", "accepted"),
    (
        ("batting-result.ball", True),
        ("batting-result.called-pitch", True),
        ("batting-result.swinging-strike", True),
        ("batting-result.foul", False),
        ("batting-result.unknown", False),
        (None, False),
    ),
)
def test_wp_pb_primary_shape_uses_existing_count_rule_finite_set(primary, accepted):
    """既核の特殊プレイ許可3語だけを形判定し、カウントは再計算しない。"""
    row, _ = _fixture(3)
    row["batting_result_key"] = primary
    assert _runner_pitch_secondary_shape(_token(row), row) is accepted
    if not accepted:
        with pytest.raises(OrdinaryPlayRowError):
            PLAY_PREFIX_PLAY_OPERATIONS[0].prepare(_token(row))


@pytest.mark.parametrize("secondary", ("secondary-result.unknown", "", None))
def test_unknown_secondary_or_ordinary_token_never_opens_wp_pb(secondary):
    """有限副結果をOrdinary tokenや未知語彙へ横展開しない。"""
    row, _ = _fixture(3)
    row["secondary_batting_result_key"] = secondary
    if secondary is None:
        # 行形だけは旧通常として通るが、元event全値照合で必ず拒否する。
        with pytest.raises(OrdinaryPlayRowError):
            _preflight(row, _fixture(3)[1])
    else:
        with pytest.raises(OrdinaryPlayRowError):
            PLAY_PREFIX_PLAY_OPERATIONS[0].prepare(_token(row))
    valid, _ = _fixture(3)
    with pytest.raises(OrdinaryPlayRowError):
        PLAY_PREFIX_PLAY_OPERATIONS[0].prepare(
            _token(valid, OrdinaryPlayRowInsertToken)
        )
