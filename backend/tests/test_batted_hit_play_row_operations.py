"""閉4安打の物理観測だけを既41列INSERTへ通す。実DB資格とは別。"""

import json
from uuid import UUID

import pytest
from test_ordinary_pitch_operations import _row, _token

from pitchlog.repositories.ordinary_pitch_operations import (
    ORDINARY_PLAY_OPERATIONS,
    OrdinaryPlayRowError,
)
from pitchlog.sync.terminal_pitch_tokens import PlayPrefixPlayRowInsertToken

_RESULTS = ("single", "double", "triple", "home-run")
_BATTED = {
    "raw_fielder_position": "9",
    "resolved_fielder_id": str(UUID(int=9)),
    "batted_ball_type": "batted.fixture.line",
    "batted_ball_strength": "batted.fixture.hard",
    "hit_x": 0.25,
    "hit_y": 0.75,
}


def _hit(result="single", values=None):
    """採用済原観測の保存型を静的に置き、runtime出力から期待を作らない。"""
    return {
        **_row(),
        "batting_result_key": f"batting-result.{result}",
        **(_BATTED if values is None else values),
    }


def _prefix(row):
    """同形の旧tokenをprefix型へ閉じ、真正資格発行は模倣しない。"""
    old = _token(row)
    return PlayPrefixPlayRowInsertToken(
        old.game_id,
        old.generation,
        old.d1,
        old.d2,
        old.d5,
        old.source_fingerprint,
        json.dumps(row),
    )


@pytest.mark.parametrize("result", _RESULTS)
@pytest.mark.parametrize("nullable", [False, True])
def test_closed_hit_preserves_all_columns(result, nullable):
    """4安打の全観測/未観測を補完せず全41列束縛と照合する。"""
    row = _hit(result, dict.fromkeys(_BATTED) if nullable else None)
    _, actual = ORDINARY_PLAY_OPERATIONS[0].prepare(_prefix(row))
    expected = {k: v for k, v in row.items() if k != "tenant_id"}
    for key in (
        "id",
        "game_id",
        "source_event_id",
        "batter_id",
        "pitcher_id",
        "catcher_id",
        "resolved_fielder_id",
    ):
        if expected[key] is not None:
            expected[key] = UUID(expected[key])
    assert actual == expected


@pytest.mark.parametrize("result", _RESULTS)
def test_old_ordinary_token_still_refuses_batted_observations(result):
    """旧tokenへ閉4安打の観測を混入しても解放しない。"""
    with pytest.raises(OrdinaryPlayRowError):
        ORDINARY_PLAY_OPERATIONS[0].prepare(_token(_hit(result)))


@pytest.mark.parametrize("result", ["ball", "called-pitch", "unknown-hit"])
def test_non_hit_and_unknown_result_keep_all_null_boundary(result):
    """prefix型だけで任意の新観測を許可しない。"""
    with pytest.raises(OrdinaryPlayRowError):
        ORDINARY_PLAY_OPERATIONS[0].prepare(_prefix(_hit(result)))


@pytest.mark.parametrize(
    "key,value",
    [
        ("hit_x", -0.001),
        ("hit_y", 1.001),
        ("hit_x", float("inf")),
        ("hit_y", float("nan")),
        ("hit_x", 1),
        ("hit_y", True),
        ("resolved_fielder_id", "invalid"),
        ("raw_fielder_position", ""),
        ("batted_ball_type", ""),
        ("batted_ball_strength", ""),
        ("strategy_key", "unsupported"),
        ("error_type", "unsupported"),
        ("course_x", -0.1),
        ("event_kind", "non_pitch"),
        ("version", 2),
    ],
)
def test_invalid_hit_or_other_unsupported_column_is_refused(key, value):
    """有限範囲/型/旧禁止列/基本列の拒否条件を維持する。"""
    row = _hit()
    row[key] = value
    with pytest.raises(OrdinaryPlayRowError):
        ORDINARY_PLAY_OPERATIONS[0].prepare(_prefix(row))
