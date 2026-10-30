"""通常全41物理列と同TX原本照合のSQL境界を検査する。実DB成功とは別。"""

import copy
import json
from uuid import UUID

import pytest
from sqlalchemy import Insert
from sqlalchemy.dialects import postgresql

from pitchlog.db.game_state.models import PlayRow
from pitchlog.db.sync_protocol.models import IdempotencyLedger, OperationEvent
from pitchlog.repositories.first_ball_operations import _NULL_COLUMNS
from pitchlog.repositories.ordinary_pitch_operations import (
    ORDINARY_PLAY_OPERATIONS,
    OrdinaryPlayRowError,
)
from pitchlog.repositories.tokens import TenantOperationResult
from pitchlog.sync.ordinary_pitch_execution import (
    OrdinaryPitchExecutionError,
    OrdinaryPitchFrame,
    _consume_ordinary_pitch_frame,
)
from pitchlog.sync.ordinary_pitch_tokens import OrdinaryPlayRowInsertToken


def _row():
    """全物理列の比較用静的入力。資格や既存DB投入の証拠ではない。"""
    return {
        **dict.fromkeys(_NULL_COLUMNS),
        "tenant_id": str(UUID(int=1)),
        "id": str(UUID(int=2)),
        "game_id": str(UUID(int=3)),
        "source_event_id": str(UUID(int=4)),
        "play_number": 8,
        "batting_order": 4,
        "event_kind": "pitch",
        "batting_result_key": "batting-result.called-pitch",
        "version": 1,
        "migration_unverified": False,
        "batter_id": str(UUID(int=5)),
        "pitcher_id": str(UUID(int=6)),
        "catcher_id": str(UUID(int=7)),
        "pitch_type_key": "fastball",
        "course_x": 0.5,
        "course_y": 0.5,
        "pitch_speed": None,
        "stance": None,
        "batting_side": None,
    }


def _token(row=None):
    """prefix長/D2をplay_numberに読み替えないメタ値を作る。"""
    return OrdinaryPlayRowInsertToken(
        UUID(int=3),
        2,
        7,
        6001,
        UUID(int=8),
        "wire-v1:" + "a" * 64,
        json.dumps(_row() if row is None else row),
    )


def test_exact_full_row_and_metadata_are_retained():
    """D1=7/D2=6001/play8/batting4を別々の値のまま保持する。"""
    operation = ORDINARY_PLAY_OPERATIONS[0]
    statement, params = operation.prepare(_token())
    assert set(_row()) == set(PlayRow.__table__.c.keys())
    expected = {k: v for k, v in _row().items() if k != "tenant_id"}
    for name in (
        "id",
        "game_id",
        "source_event_id",
        "batter_id",
        "pitcher_id",
        "catcher_id",
    ):
        expected[name] = UUID(expected[name])
    assert params == expected
    assert isinstance(statement, Insert)
    assert statement.table is PlayRow.__table__
    assert "INSERT INTO play_rows (" in str(
        statement.compile(dialect=postgresql.dialect())
    )
    assert "tenant_id" not in params


@pytest.mark.parametrize(
    "field,value",
    [
        ("play_number", True),
        ("course_x", 1),
        ("course_x", float("inf")),
        ("batting_order", 0),
        ("version", 2),
        ("migration_unverified", True),
        ("strategy_key", "forbidden"),
        ("batter_id", None),
        ("id", str(UUID(int=2)) + "\n"),
        ("stance", "01"),
    ],
)
def test_invalid_physical_input_is_rejected(field, value):
    """型・未支持観測・移行経路・正準形を補修せず拒否する。"""
    row = _row()
    row[field] = value
    with pytest.raises(OrdinaryPlayRowError):
        ORDINARY_PLAY_OPERATIONS[0].prepare(_token(row))


def test_preflight_requires_actual_event_ledger_and_empty_prior_row():
    """同じSQL入力/原イベント/台帳/投影一意を全値照合する。"""
    operation = ORDINARY_PLAY_OPERATIONS[0]
    token = _token()
    _, params = operation.prepare(token)
    params = {**params, "tenant_id": UUID(int=1)}
    prepare_preflight = operation.preflight
    assert prepare_preflight is not None
    preflight = prepare_preflight(token, params)
    event = {name: None for name in OperationEvent.__table__.c.keys()}
    event.update(
        tenant_id=UUID(int=1),
        id=UUID(int=4),
        game_id=UUID(int=3),
        generation=2,
        d1=7,
        d2=6001,
        d5=UUID(int=8),
        event_kind="play_input",
        ledger_kind="accepted",
        is_tombstone=False,
        migration_unverified=False,
    )
    ledger = {name: None for name in IdempotencyLedger.__table__.c.keys()}
    ledger.update(
        tenant_id=UUID(int=1),
        d5=UUID(int=8),
        kind="accepted",
        source_fingerprint="wire-v1:" + "a" * 64,
    )
    result = (
        TenantOperationResult(
            (tuple(event[k] for k in OperationEvent.__table__.c.keys()),)
        ),
        TenantOperationResult(
            (tuple(ledger[k] for k in IdempotencyLedger.__table__.c.keys()),)
        ),
        TenantOperationResult(()),
    )
    preflight.validate(result)
    bad = copy.deepcopy(params)
    bad["tenant_id"] = UUID(int=99)
    with pytest.raises(OrdinaryPlayRowError):
        prepare_preflight(token, bad)
    for field in ("d2", "d5", "source_fingerprint"):
        changed_event = event.copy()
        changed_ledger = ledger.copy()
        if field == "d2":
            changed_event[field] = 6002
        elif field == "d5":
            changed_event[field] = UUID(int=99)
        else:
            changed_ledger[field] = "wire-v1:" + "b" * 64
        changed = (
            TenantOperationResult(
                (tuple(changed_event[k] for k in OperationEvent.__table__.c.keys()),)
            ),
            TenantOperationResult(
                (
                    tuple(
                        changed_ledger[k] for k in IdempotencyLedger.__table__.c.keys()
                    ),
                )
            ),
            TenantOperationResult(()),
        )
        with pytest.raises(OrdinaryPlayRowError):
            preflight.validate(changed)


def test_free_frame_or_foreign_handle_cannot_issue_projection():
    """実DB/frame資格を自由recordや呼出者のtrueから作れない。"""
    with pytest.raises(OrdinaryPitchExecutionError):
        OrdinaryPitchFrame()
    with pytest.raises(OrdinaryPitchExecutionError):
        _consume_ordinary_pitch_frame(object(), object(), object())
