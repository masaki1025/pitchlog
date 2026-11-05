"""取消wire全値/未知member/型/EOSをshape境界で検査する。"""

import copy
import json

import pytest
from test_nonplay_prefix import CASES, wire_event

from pitchlog.sync.undo_payload import (
    UndoPayloadError,
    read_undo_event,
    read_undo_payload,
)


@pytest.mark.parametrize("original", CASES["undoEvents"])
def test_original_full_payload_preserved(original):
    """全要求/応答/参照を補完せず往復する。"""
    payload = read_undo_event(wire_event(original))
    assert payload.to_wire() == original["payload"]


@pytest.mark.parametrize(
    "key", ["d2", "state_diff", "replacement_state", "expected_version", "tenantId"]
)
def test_forbidden_even_null(key):
    """Own D2/V8/V9/V11/tenantはnullでも存在できない。"""
    from pitchlog.sync.undo_payload import _read

    raw = copy.deepcopy(CASES["undoEvents"][0])
    raw[key] = None
    with pytest.raises(UndoPayloadError):
        _read(json.dumps(raw), "UndoEvent")


@pytest.mark.parametrize("value", [True, 1.0, "1"])
def test_wire_d1_exact_type(value):
    """JSON Schemaの整数同値を実wireのintへ持ち込まない。"""
    raw = copy.deepcopy(CASES["undoEvents"][0])
    raw["target_reference"]["d1"] = value
    with pytest.raises(UndoPayloadError):
        read_undo_event(wire_event(raw))


@pytest.mark.parametrize(
    "suffix", ["\n", "\r", "\r\n", "\x85", "\u2028", "\u2029", "\v", "\f"]
)
def test_checkpoint_revision_strict_eos(suffix):
    """末尾の全改行を正準数値として受理しない。"""
    raw = copy.deepcopy(CASES["undoEvents"][0]["payload"])
    raw["expectedCheckpoint"]["revision"] += suffix
    with pytest.raises(UndoPayloadError):
        read_undo_payload(json.dumps(raw))


def test_duplicate_unknown_and_nonfinite():
    """decodeで欠落や重複を補修しない。"""
    for raw in [
        '{"formatVersion":"native-undo-prefix-v1","formatVersion":"x"}',
        '{"x":NaN}',
        "{}",
    ]:
        with pytest.raises(UndoPayloadError):
            read_undo_payload(raw)
