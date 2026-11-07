"""RunnerNPの閉41列形と受理原payloadの照合。実認可/保存とは別の純検査。"""

import copy
import json
from types import MappingProxyType
from uuid import UUID

import pytest
from test_runner_event_wire import _CASES, _payload

from pitchlog.db.game_state.models import PlayRow
from pitchlog.db.sync_protocol.models import IdempotencyLedger, OperationEvent
from pitchlog.repositories.ordinary_pitch_operations import (
    PLAY_PREFIX_PLAY_OPERATIONS,
    OrdinaryPlayRowError,
)
from pitchlog.repositories.tokens import TenantOperationResult
from pitchlog.sync.ordinary_pitch_physical import pitch_physical_row
from pitchlog.sync.ordinary_pitch_tokens import OrdinaryPlayRowInsertToken
from pitchlog.sync.terminal_pitch_tokens import PlayPrefixPlayRowInsertToken

_OPERATIONS = (
    *(
        f"{who}-pickoff-destination.{base}"
        for who in ("pitcher", "catcher")
        for base in ("first", "second", "third")
    ),
    "strategy-category.steal",
    "secondary-result.balk",
)


def _fixture(operation):
    """既候補の原観測/物理形を使う。新数学期待やDB資格は作らない。"""
    if operation == "secondary-result.balk":
        case = copy.deepcopy(_CASES[5])
    else:
        case = copy.deepcopy(_CASES[0])
        t1 = case["request"]["t1"]
        t1["resultId"] = operation
        per = t1["runnerObservation"]["perPitch"]
        per["resultId"] = operation
        per["runnerEventPayload"]["event_kind"] = operation
        per["runnerEventPayload"]["by_runner"]["first"]["out_kind"] = (
            "caught-stealing"
            if operation == "strategy-category.steal"
            else "catcher-pickoff-out"
            if operation.startswith("catcher")
            else "pitcher-pickoff-out"
        )
    raw, calculation = _payload(case)
    from pitchlog.sync.terminal_pitch_payload import LineupPitchPlayPayload

    payload = LineupPitchPlayPayload.model_validate_json(json.dumps(raw))
    q = calculation.request
    row = pitch_physical_row(
        payload.observations,
        payload.participants,
        q.t1.result_id,
        tenant_id=UUID(q.prefix_ref.tenant_id),
        game_id=UUID(q.prefix_ref.game_id),
        source_event_id=UUID(q.play_identity.event_id),
        row_id=UUID(q.play_identity.play_id),
        play_number=101,
    )
    return row, raw


def _token(row, kind=PlayPrefixPlayRowInsertToken):
    return kind(
        UUID(row["game_id"]),
        1,
        101,
        101,
        UUID(int=0x20000000000000000000000000000004),
        "wire-v1:" + "a" * 64,
        json.dumps(row),
    )


def _immutable(value):
    if type(value) is dict:
        return MappingProxyType({k: _immutable(v) for k, v in value.items()})
    if type(value) is list:
        return tuple(_immutable(v) for v in value)
    return value


def _preflight(row):
    token = _token(row)
    op = PLAY_PREFIX_PLAY_OPERATIONS[0]
    _, params = op.prepare(token)
    assert op.preflight is not None
    return op.preflight(token, {**params, "tenant_id": UUID(row["tenant_id"])})


def _results(row, payload):
    event = dict.fromkeys(OperationEvent.__table__.c.keys())
    event.update(
        tenant_id=UUID(row["tenant_id"]),
        id=UUID(row["source_event_id"]),
        game_id=UUID(row["game_id"]),
        generation=1,
        d1=101,
        d2=101,
        d5=_token(row).d5,
        event_kind="play_input",
        ledger_kind="accepted",
        is_tombstone=False,
        migration_unverified=False,
        payload=_immutable(payload),
    )
    ledger = dict.fromkeys(IdempotencyLedger.__table__.c.keys())
    ledger.update(
        tenant_id=UUID(row["tenant_id"]),
        d5=_token(row).d5,
        kind="accepted",
        source_fingerprint="wire-v1:" + "a" * 64,
    )
    return (
        TenantOperationResult(
            (tuple(event[k] for k in OperationEvent.__table__.c.keys()),)
        ),
        TenantOperationResult(
            (tuple(ledger[k] for k in IdempotencyLedger.__table__.c.keys()),)
        ),
        TenantOperationResult(()),
    )


@pytest.mark.parametrize("operation", _OPERATIONS)
def test_only_finite_runner_nonpitch_uses_exact_mapper_and_actual_source(operation):
    """8種類の構造を検査し、主結果や投球6列を埋めない。数学の独立導出ではない。"""
    row, payload = _fixture(operation)
    _, params = PLAY_PREFIX_PLAY_OPERATIONS[0].prepare(_token(row))
    assert set(row) == set(PlayRow.__table__.c.keys()) and len(row) == 41
    assert params["event_kind"] == "non_pitch"
    assert params["batting_result_key"] is None
    for key in (
        "pitch_type_key",
        "course_x",
        "course_y",
        "pitch_speed",
        "stance",
        "batting_side",
    ):
        assert params[key] is None
    _preflight(row).validate(_results(row, payload))


@pytest.mark.parametrize(
    "mutation",
    (
        "unknown",
        "extra",
        "missing",
        "kind",
        "observation",
        "play-id",
        "d5",
        "tenant",
        "participant",
        "pickoff-detail",
        "balk-for-steal",
    ),
)
def test_source_unknown_or_full_row_mismatch_is_rejected_before_insert(mutation):
    """候補allNULL形を作れても、原イベントの有限操作との照合を省略しない。"""
    row, payload = _fixture("pitcher-pickoff-destination.first")
    if mutation == "unknown":
        for p in (
            payload["observations"]["runnerObservation"]["perPitch"],
            payload["calculation"]["request"]["t1"]["runnerObservation"]["perPitch"],
        ):
            p["runnerEventPayload"]["event_kind"] = "unknown"
    elif mutation == "extra":
        payload["extra"] = True
    elif mutation == "missing":
        payload = None
    elif mutation == "kind":
        payload["observations"]["kind"] = "pitch-event"
    elif mutation == "observation":
        payload["observations"]["runnerObservation"]["perPitch"]["runnerEventPayload"][
            "by_runner"
        ]["first"]["out_kind"] = "running-out"
    elif mutation in ("play-id", "d5"):
        key = "playId" if mutation == "play-id" else "d5"
        payload["calculation"]["request"]["playIdentity"][key] = str(UUID(int=77))
    elif mutation == "tenant":
        payload["calculation"]["request"]["prefixRef"]["tenantId"] = str(UUID(int=77))
    elif mutation == "participant":
        row["batter_id"] = str(UUID(int=77))
    elif mutation == "pickoff-detail":
        row["pickoff_detail"] = "third"
    else:
        row, payload = _fixture("strategy-category.steal")
        row["secondary_batting_result_key"] = "secondary-result.balk"
    with pytest.raises(OrdinaryPlayRowError):
        _preflight(row).validate(_results(row, payload))


@pytest.mark.parametrize(
    "mutation",
    ("ordinary", "fake-pitch", "course", "result", "unknown-detail", "strategy"),
)
def test_runner_shape_never_opens_ordinary_or_unknown_observation(mutation):
    """通常token/投球偽装/未供給付随列はrow段階でも拒否する。"""
    row, _ = _fixture("pitcher-pickoff-destination.first")
    kind = PlayPrefixPlayRowInsertToken
    if mutation == "ordinary":
        kind = OrdinaryPlayRowInsertToken
    elif mutation == "fake-pitch":
        row["event_kind"] = "pitch"
    elif mutation == "course":
        row["course_x"] = 0.5
    elif mutation == "result":
        row["batting_result_key"] = "strategy-category.steal"
    elif mutation == "unknown-detail":
        row["pickoff_detail"] = "home"
    else:
        row["strategy_key"] = "strategy-category.steal"
    with pytest.raises(OrdinaryPlayRowError):
        PLAY_PREFIX_PLAY_OPERATIONS[0].prepare(_token(row, kind))
