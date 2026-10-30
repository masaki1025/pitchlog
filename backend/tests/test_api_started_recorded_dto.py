"""記録後DTOの公開列・閉じた語彙・座標の形を、物理41列との差分で固定する。

実DB・実HTTP・実artifactの受入ではない（それらは別の受入試験の範囲）。
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

import pytest
from pydantic import ValidationError

from pitchlog.api.schemas.started_games import (
    PressWire,
    StartedPlayRow,
    StartedRecordedGameRead,
)
from pitchlog.repositories.recorded_snapshot_operations import (
    RECORDED_PLAY_ROW_COLUMNS,
)

_EXCLUDED = (
    "tenant_id",
    "hidden_at",
    "import_batch_id",
    "legacy_row_identifier",
    "migration_unverified",
)
# 公開する36列のうち座標2列は物理Doubleを出さず、payloadの正準整数kを
# `course` 1値へまとめる（DTOのfield数は35）。
_COORDINATES = ("course_x", "course_y")
_EXPOSED_COLUMNS = tuple(
    name for name in RECORDED_PLAY_ROW_COLUMNS if name not in _EXCLUDED
)
_PUBLIC_FIELDS = tuple(
    name for name in _EXPOSED_COLUMNS if name not in _COORDINATES
) + ("course",)
_REQUIRED = (
    "id",
    "game_id",
    "source_event_id",
    "play_number",
    "batting_order",
    "batter_id",
    "pitcher_id",
    "catcher_id",
    "event_kind",
    "course",
    "pitch_type_key",
    "batting_result_key",
    "version",
)


def _row(**changes: object) -> dict[str, object]:
    """照合済み初球の閉値を合成し、指定keyだけを差し替える。"""
    value: dict[str, object] = {
        "id": UUID(int=1),
        "game_id": UUID(int=2),
        "source_event_id": UUID(int=3),
        "play_number": 1,
        "batting_order": 1,
        "batter_id": UUID(int=110),
        "pitcher_id": UUID(int=201),
        "catcher_id": UUID(int=202),
        "batting_side": "右",
        "stance": "1",
        "strategy_key": None,
        "strategy_detail_key": None,
        "strategy_result_key": None,
        "batter_status": None,
        "event_kind": "pitch",
        "course": {"unit": "1/263", "x": "132", "y": "131"},
        "pitch_type_key": "u06-first-ball-fastball",
        "batting_result_key": "batting-result.ball",
        "secondary_batting_result_key": None,
        "raw_fielder_position": None,
        "resolved_fielder_id": None,
        "batted_ball_type": None,
        "batted_ball_strength": None,
        "hit_x": None,
        "hit_y": None,
        "pickoff_type": None,
        "pickoff_detail": None,
        "error_type": None,
        "raw_error_position": None,
        "resolved_error_player_id": None,
        "pitch_speed": None,
        "press": None,
        "fake_run": None,
        "comment": None,
        "version": 1,
    }
    value.update(changes)
    return value


def test_physical_columns_minus_excluded_five_are_the_public_set() -> None:
    """公開列は41−5=36で、うち座標2列はcourse 1値へまとまる。"""
    assert len(RECORDED_PLAY_ROW_COLUMNS) == 41
    assert len(_EXPOSED_COLUMNS) == 36
    assert set(RECORDED_PLAY_ROW_COLUMNS) - set(_EXPOSED_COLUMNS) == set(_EXCLUDED)
    assert set(StartedPlayRow.model_fields) == set(_PUBLIC_FIELDS)
    assert len(StartedPlayRow.model_fields) == 35
    assert set(_COORDINATES) - set(StartedPlayRow.model_fields) == set(_COORDINATES)
    for excluded in _EXCLUDED:
        assert excluded not in StartedPlayRow.model_fields


def test_dto_is_frozen_and_rejects_unknown_keys() -> None:
    """未知key（とくに除外列）を持つ応答を採用しない。"""
    assert StartedPlayRow.model_config["extra"] == "forbid"
    assert StartedPlayRow.model_config["frozen"] is True
    assert StartedRecordedGameRead.model_config["extra"] == "forbid"
    for leaked in _EXCLUDED:
        with pytest.raises(ValidationError):
            StartedPlayRow.model_validate(_row(**{leaked: None}))


@pytest.mark.parametrize("state", ["0", "1プレス", "3プレス", "両プレス"])
def test_press_and_fake_run_keep_the_four_text_states(state: str) -> None:
    """DB textの4状態をbool化せず、そのまま区別して返す。"""
    row = StartedPlayRow.model_validate(_row(press=state, fake_run=state))
    dumped = row.model_dump(mode="json")
    assert dumped["press"] == state and dumped["fake_run"] == state
    assert isinstance(dumped["press"], str)
    assert set(PressWire.__args__) == {"0", "1プレス", "3プレス", "両プレス"}


@pytest.mark.parametrize("value", [True, False, 0, 1, "1", "プレス", ""])
def test_non_closed_press_values_are_rejected(value: object) -> None:
    """bool・数値・閉集合外の文言を、成功値へ写さない。"""
    with pytest.raises(ValidationError):
        StartedPlayRow.model_validate(_row(press=value))
    with pytest.raises(ValidationError):
        StartedPlayRow.model_validate(_row(fake_run=value))


def test_course_is_the_canonical_integer_pair_not_a_physical_double() -> None:
    """座標はpayloadの正準整数kをunit付きで返し、小数を受け付けない。"""
    dumped = StartedPlayRow.model_validate(_row()).model_dump(mode="json")
    assert dumped["course"] == {"unit": "1/263", "x": "132", "y": "131"}
    assert "course_x" not in dumped and "course_y" not in dumped
    for bad in (
        {"unit": "1/263", "x": 132, "y": "131"},
        {"unit": "1/263", "x": "0132", "y": "131"},
        {"unit": "1/263", "x": "132", "y": "264"},
        {"unit": "1/263", "x": "132", "y": "-1"},
        {"unit": "1/100", "x": "132", "y": "131"},
    ):
        with pytest.raises(ValidationError):
            StartedPlayRow.model_validate(_row(course=bad))


@pytest.mark.parametrize("name", _REQUIRED)
def test_verified_columns_are_required(name: str) -> None:
    """全値照合済みの列はNULLを許さず、値の欠落を503へ閉じる。"""
    value = _row()
    del value[name]
    with pytest.raises(ValidationError):
        StartedPlayRow.model_validate(value)
    with pytest.raises(ValidationError):
        StartedPlayRow.model_validate(_row(**{name: None}))


_PAYLOAD_NULLABLE = ("stance", "batting_side", "pitch_speed")


def test_nullable_columns_are_payload_values_or_fixed_null() -> None:
    """nullable列は payload値3列と、writerがNULL固定する19列へ分かれる。

    19列は reader が NULL を照合し、非NULLは破損（503）として公開しない。
    DTO が `| None` なのはその NULL を表すためである。
    """
    from pitchlog.repositories.recorded_snapshot import _FIXED_NULL_COLUMNS

    assert set(_FIXED_NULL_COLUMNS) | set(_PAYLOAD_NULLABLE) | set(_REQUIRED) == set(
        StartedPlayRow.model_fields
    )
    assert not set(_FIXED_NULL_COLUMNS) & set(_REQUIRED)
    assert not set(_FIXED_NULL_COLUMNS) & set(_PAYLOAD_NULLABLE)


@pytest.mark.parametrize(
    "name", [name for name in _PUBLIC_FIELDS if name not in _REQUIRED]
)
def test_nullable_columns_accept_null(name: str) -> None:
    """NULLで保存された列を、NULLのまま表現できる。"""
    assert StartedPlayRow.model_validate(_row(**{name: None}))


@pytest.mark.parametrize(
    "name,value",
    [
        ("play_number", 2),
        ("play_number", True),
        ("batting_order", 2),
        ("event_kind", "non_pitch"),
        ("version", 2),
        ("pitch_speed", float("inf")),
        ("hit_x", 1.5),
        ("batting_side", "switch"),
    ],
)
def test_closed_columns_reject_out_of_scope_values(name: str, value: object) -> None:
    """初球の閉じた範囲（1球目/pitch/版1）と有限小数だけを受ける。"""
    with pytest.raises(ValidationError):
        StartedPlayRow.model_validate(_row(**{name: value}))


def test_recorded_dto_keeps_state_meaning_and_separates_after() -> None:
    """`state` はbeforeのまま、記録後は `after` に分ける（意味を反転しない）。"""
    assert "after" in StartedRecordedGameRead.model_fields
    assert "state" in StartedRecordedGameRead.model_fields
    annotation = str(StartedRecordedGameRead.model_fields["state"].annotation)
    after = str(StartedRecordedGameRead.model_fields["after"].annotation)
    assert "StateSnapshot" in annotation and "StateSnapshot" in after
    assert (
        StartedRecordedGameRead.model_fields["read_kind"].annotation
        == Literal["recorded"]
    )

    def max_lengths(name: str) -> list[int]:
        return [
            value.max_length
            for value in StartedRecordedGameRead.model_fields[name].metadata
            if hasattr(value, "max_length")
        ]

    assert max_lengths("play_rows") == [1]
    assert max_lengths("history") == [1]
