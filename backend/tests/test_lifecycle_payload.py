"""終了再開の閉wireを認可なしの純codecとして検査する。"""

import copy

import pytest

from pitchlog.sync.lifecycle_payload import (
    LifecyclePayload,
    LifecyclePayloadError,
    read_lifecycle_event,
)
from pitchlog.sync.model import ABSENT, SyncEvent

ID = "10000000-0000-0000-0000-000000000001"
RECEIPT = "20000000-0000-0000-0000-000000000001"


def payload():
    """製品出力から期待を作らない最小wire。"""
    return {
        "formatVersion": "native-game-lifecycle-v1",
        "action": "end",
        "checkpointRef": {
            "kind": "confirmed",
            "id": ID,
            "revision": "1",
            "digest": "a" * 64,
        },
        "target": None,
        "event": {"eventId": ID, "receiptId": RECEIPT},
    }


def event(value, **changes):
    """同一D5の値だけを作り、実source資格を発行しない。"""
    return SyncEvent(
        ID,
        ID,
        d1=changes.get("d1", 1),
        d4=changes.get("d4", "opaque"),
        v5=changes.get("v5", "game_end_declaration"),
        v6=changes.get("v6", 0),
        v7=value,
        v8=changes.get("v8", ABSENT),
        v9=changes.get("v9", ABSENT),
        v10=changes.get("v10", ABSENT),
        v11=changes.get("v11", ABSENT),
    )


def test_end_and_reopen_preserve_reserved_identity_and_zero_d2():
    """D2=0も既正本の非負域として保つ。"""
    value = payload()
    result = read_lifecycle_event(event(value))
    assert result.to_wire() == value
    result.to_wire()["event"]["eventId"] = RECEIPT
    assert result.to_wire() == value
    value.update(
        action="reopen",
        target={
            "kind": "confirmed",
            "version": "1",
            "eventId": RECEIPT,
            "receiptId": ID,
        },
    )
    assert read_lifecycle_event(event(value, v5="game_reopen")).to_wire() == value


@pytest.mark.parametrize("field", ["v8", "v9", "v10", "v11"])
def test_dependent_values_including_explicit_null_are_rejected(field):
    """閉じた型と同値条件を検査する。"""
    with pytest.raises(LifecyclePayloadError):
        read_lifecycle_event(event(payload(), **{field: None}))


@pytest.mark.parametrize(
    "changes",
    [
        {"d1": True},
        {"d1": 0},
        {"v6": True},
        {"v6": -1},
        {"v5": "game_reopen"},
        {"v5": "state_correction"},
    ],
)
def test_position_and_operation_cannot_be_coerced(changes):
    """閉じた型と同値条件を検査する。"""
    with pytest.raises(LifecyclePayloadError):
        read_lifecycle_event(event(payload(), **changes))


@pytest.mark.parametrize(
    "mutation", ["extra", "target", "revision", "digest", "event", "action", "null"]
)
def test_payload_is_closed(mutation):
    """閉じた型と同値条件を検査する。"""
    value = copy.deepcopy(payload())
    if mutation == "extra":
        value["extra"] = False
    if mutation == "target":
        value["target"] = {"version": "1", "eventId": ID, "receiptId": RECEIPT}
    if mutation == "revision":
        value["checkpointRef"]["revision"] = "01"
    if mutation == "digest":
        value["checkpointRef"]["digest"] = "a" * 63 + "\n"
    if mutation == "event":
        value["event"]["eventId"] = "bad"
    if mutation == "action":
        value["action"] = "undo"
    if mutation == "null":
        value = None
    with pytest.raises(LifecyclePayloadError):
        read_lifecycle_event(event(value))


@pytest.mark.parametrize("raw", ["{", '{"action":"end","action":"reopen"}', "NaN"])
def test_invalid_json_is_content_failure(raw):
    """閉じた型と同値条件を検査する。"""
    with pytest.raises(LifecyclePayloadError):
        LifecyclePayload(raw)


@pytest.mark.parametrize(
    "ref_kind", ["confirmed", "confirmed_prefix", "queued_predecessor"]
)
@pytest.mark.parametrize("target_kind", ["confirmed", "queued_end"])
def test_reopen_closed_unions_keep_observed_and_reserved_values(ref_kind, target_kind):
    """各閉variantは原値を返し、予約値から確定版を補わない。"""
    value = payload()
    position = {"d4": "owned-wire-reference", "d1": 1, "d5": ID}
    cp = {"id": ID, "revision": "1", "digest": "a" * 64}
    ref = {"kind": ref_kind}
    if ref_kind != "queued_predecessor":
        ref.update(cp)
    if ref_kind != "confirmed":
        ref.update(position)
    target = {"kind": target_kind, "eventId": ID, "receiptId": RECEIPT}
    if target_kind == "confirmed":
        target["version"] = "1"
    else:
        target.update(position)
    value.update(action="reopen", checkpointRef=ref, target=target)
    result = read_lifecycle_event(event(value, v5="game_reopen"))
    assert result.to_wire() == value
    if target_kind == "queued_end":
        assert "version" not in result.to_wire()["target"]


@pytest.mark.parametrize("kind", ["confirmed_prefix", "queued_predecessor"])
@pytest.mark.parametrize(
    "member,bad",
    [
        ("d1", "01"),
        ("d1", "1"),
        ("d1", 0),
        ("d1", True),
        ("d4", ""),
        ("d4", 1),
        ("d5", "bad"),
    ],
)
def test_queued_and_confirmed_prefix_positions_reject_noncanonical_values(
    kind, member, bad
):
    """未送信依存でも型を補修しない。"""
    value = payload()
    ref = {"kind": kind, "d4": "owned-wire-reference", "d1": 1, "d5": ID}
    if kind == "confirmed_prefix":
        ref.update(id=ID, revision="1", digest="a" * 64)
    ref[member] = bad
    value["checkpointRef"] = ref
    with pytest.raises(LifecyclePayloadError):
        read_lifecycle_event(event(value))


@pytest.mark.parametrize(
    "ref",
    [
        {"id": ID, "revision": "1", "digest": "a" * 64},
        {"kind": "other"},
        {
            "kind": "queued_predecessor",
            "d4": "d4",
            "d1": "1",
            "d5": ID,
            "digest": "a" * 64,
        },
    ],
)
def test_legacy_flat_or_unknown_reference_is_not_silently_upgraded(ref):
    """旧flat参照と余剰memberを新unionとして推測受理しない。"""
    value = payload()
    value["checkpointRef"] = ref
    with pytest.raises(LifecyclePayloadError):
        read_lifecycle_event(event(value))


@pytest.mark.parametrize("action", [[], {}, True, None, 1])
def test_nonstring_action_is_closed_content_error(action):
    """JSON値の型違いを集合照合のTypeErrorへ漏らさない。"""
    value = payload()
    value["action"] = action
    with pytest.raises(LifecyclePayloadError):
        read_lifecycle_event(event(value))


@pytest.mark.parametrize(
    "value", [ABSENT, {"bad": float("nan")}, {"bad": float("inf")}]
)
def test_non_json_or_nonfinite_v7_is_closed_content_error(value):
    """欠落/非有限値を未分類例外のまま上位へ漏らさない。"""
    with pytest.raises(LifecyclePayloadError):
        read_lifecycle_event(event(value))


@pytest.mark.parametrize(
    "changes", [{"d1": 2**53}, {"v6": 2**63}, {"d4": None}, {"d4": ""}]
)
def test_existing_outer_wire_bounds_are_preserved(changes):
    """既SyncRequest/orderingの上限をcodecでも省略しない。"""
    with pytest.raises(LifecyclePayloadError):
        read_lifecycle_event(event(payload(), **changes))


def test_existing_maximum_wire_positions_remain_valid():
    """上限を狭めず既値域の端点を受理する。"""
    value = payload()
    assert (
        read_lifecycle_event(event(value, d1=2**53 - 1, v6=2**63 - 1)).to_wire()
        == value
    )
