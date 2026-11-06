"""交代P2の閉値を保存原本・同TX評価より前に検査する。"""

import copy
import json
from typing import Any, cast

import pytest

from pitchlog.sync.model import SyncEvent
from pitchlog.sync.substitution_payload import (
    SubstitutionPayloadError,
    read_substitution_event,
    read_substitution_payload,
)

GAME = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
D5 = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
OUT = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
IN = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"


def payload():
    """製品wireと同じCP/操作4分岐の基底。"""
    return {
        "formatVersion": "substitution-event-v1",
        "expectedCheckpoint": {
            "id": GAME,
            "revision": "1",
            "digest": "a" * 64,
        },
        "eventId": D5,
        "operation": {
            "kind": "pitcher",
            "side": "home",
            "outgoingId": OUT,
            "incomingId": IN,
            "count": {"strikes": "1", "balls": "2"},
            "dh": "retain",
        },
        "incomingSnapshots": [{"playerId": IN, "uniformNumber": "18"}],
    }


def event(value=None, **changes):
    """S-1済みの凍結eventを作る。"""
    fields = dict(
        d5=D5,
        game_id=GAME,
        d1=2,
        d4="generation",
        v5="substitution",
        v6=4,
        v7=payload() if value is None else value,
    )
    return SyncEvent(**cast(Any, fields | changes))


@pytest.mark.parametrize(
    "operation",
    [
        {
            "kind": "pitcher",
            "side": "home",
            "outgoingId": OUT,
            "incomingId": IN,
            "count": {"strikes": "1", "balls": "2"},
            "dh": "retain",
        },
        {
            "kind": "pinch-hitter",
            "side": "away",
            "outgoingId": OUT,
            "incomingId": IN,
            "battingSlot": "3",
        },
        {
            "kind": "pinch-runner",
            "side": "away",
            "outgoingId": OUT,
            "incomingId": IN,
            "base": "2",
        },
        {
            "kind": "defense",
            "side": "home",
            "changes": [{"position": "1", "outgoingId": OUT, "incomingId": IN}],
        },
    ],
)
def test_four_closed_operations_round_trip(operation):
    """全4種を欠落・補完なく受け取り、値だけでは保存資格を発行しない。"""
    original = payload()
    original["operation"] = operation
    assert read_substitution_event(event(original)).to_wire() == original


@pytest.mark.parametrize(
    "change",
    [
        lambda value: value.update(extra=None),
        lambda value: value["expectedCheckpoint"].update(revision="01"),
        lambda value: value["expectedCheckpoint"].update(digest="A" * 64),
        lambda value: value["operation"].update(side="visitor"),
        lambda value: value["operation"]["count"].update(strikes="3"),
        lambda value: value["operation"].update(extra=None),
        lambda value: value.update(eventId="bad"),
        lambda value: value.update(incomingSnapshots=[]),
        lambda value: value["incomingSnapshots"][0].update(playerId=OUT),
        lambda value: value["incomingSnapshots"][0].update(uniformNumber=18),
    ],
)
def test_unknown_and_invalid_value_rejected(change):
    """閉unionの未知・不正値を同一形へ補修しない。"""
    value = copy.deepcopy(payload())
    change(value)
    with pytest.raises(SubstitutionPayloadError):
        read_substitution_event(event(value))


def test_duplicate_nonfinite_and_newline_rejected():
    """JSON decode段階の重複keyと非有限値、EOSを拒否する。"""
    for raw in (
        '{"formatVersion":"substitution-event-v1","formatVersion":"x"}',
        '{"x":NaN}',
        json.dumps(payload()).replace('"revision": "1"', '"revision": "1\\n"'),
    ):
        with pytest.raises(SubstitutionPayloadError):
            read_substitution_payload(raw)


@pytest.mark.parametrize(
    "change",
    [
        {"v5": "3"},
        {"v6": True},
        {"v8": None},
        {"v10": None},
        {"d1": True},
        {"d1": 0},
    ],
)
def test_event_boundary_rejected(change):
    """番号ID・bool/int混同・禁止slotを通さない。"""
    with pytest.raises(SubstitutionPayloadError):
        read_substitution_event(event(**change))


def test_defense_duplicate_and_unknown_side_rejected():
    """守備同位置の二重更新と未知側は全値を拒否する。"""
    value = payload()
    value["operation"] = {
        "kind": "defense",
        "side": "other",
        "changes": [{"position": "1", "outgoingId": OUT, "incomingId": IN}],
    }
    with pytest.raises(SubstitutionPayloadError):
        read_substitution_event(event(value))
    value["operation"]["side"] = "home"
    value["operation"]["changes"].append(
        {"position": "1", "outgoingId": IN, "incomingId": OUT}
    )
    with pytest.raises(SubstitutionPayloadError):
        read_substitution_event(event(value))
