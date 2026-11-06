"""物理ID/採番と数学提案を分離する保存全値対向。pure資格doubleを明示する。"""

import json
from types import SimpleNamespace
from uuid import UUID

import pytest
from test_nonplay_normal_payload import fixture_values

from pitchlog.repositories.nonplay_prefix_read import (
    ConfirmedNonplayNormalPrefix,
    NonplayCheckpointView,
)
from pitchlog.sync.idempotency import source_fingerprint
from pitchlog.sync.model import SyncEvent
from pitchlog.sync.terminal_pitch_payload import LineupPitchPlayPayload
from pitchlog.sync.terminal_pitch_projection import build_nonplay_normal_preparation


def preparation():
    """数学は承認手例、DB/source資格は本試験専用の明示double。"""
    v7, v8 = fixture_values()
    payload = LineupPitchPlayPayload.model_validate_json(json.dumps(v7))
    from pitchlog.sync.terminal_pitch_payload import NonplayPitchCalculation

    assert type(payload.calculation) is NonplayPitchCalculation
    q = payload.calculation.request
    source = q.source
    event = SyncEvent(
        q.play_identity.d5,
        source.checkpoint.content.scope.game_id,
        int(q.source_position.d1),
        source.checkpoint.content.scope.generation,
        "play_input",
        v6=int(q.source_position.d2),
        v7=v7,
        v8=v8,
    )
    # rosterは保存準備だけの明示double。DB発行の証拠とは扱わない。
    roster = SimpleNamespace(
        model_dump=lambda **kwargs: {"same_saved_roster": "test-double"}
    )
    prefix = object.__new__(ConfirmedNonplayNormalPrefix)
    for key, value in dict(
        checkpoint=NonplayCheckpointView(source.checkpoint, 1, 1),
        source=source,
        next_play_number=int(source.checkpoint.content.next_physical_play_number),
        roster=roster,
        previous_payload=None,
    ).items():
        object.__setattr__(prefix, key, value)
    state = SimpleNamespace(
        prefix=prefix,
        payload=payload,
        frame_id=UUID("00000000-0000-4000-8000-000000000801"),
        projected=event,
        source=SimpleNamespace(
            read=lambda *_: SimpleNamespace(event_fingerprint="wire-v1:" + "a" * 64)
        ),
        handle=object(),
        event=event,
    )
    record = {"id": UUID(q.play_identity.event_id)}
    return state, record, UUID(source.checkpoint.content.scope.tenant_id), v7, v8


def test_physical_id_and_raw_history_preserved_logical_echo_separate():
    """2pop後のD3/depth/物理採番を混同せず、保存CPをserver sealする。"""
    state, record, tenant, v7, v8 = preparation()
    p = build_nonplay_normal_preparation(state, record, tenant)
    before = p["checkpoint"]
    actual = p["next_checkpoint"]["checkpoint"]
    c = actual["content"]
    r = v7["calculation"]["response"]["value"]
    assert actual["ref"]["id"] == before["ref"]["id"]
    assert actual["ref"]["id"] != r["nextPrefixRef"]["id"]
    assert actual["ref"]["digest"] == source_fingerprint(c)
    assert actual["ref"]["digest"] != r["nextPrefixRef"]["digest"]
    assert c["d3"] == str(int(before["content"]["d3"]) + 1)
    assert c["activeDepth"] == "1"
    assert c["historyVersion"] == str(int(before["content"]["historyVersion"]) + 1)
    assert c["storageHistoryEpoch"] == before["content"]["storageHistoryEpoch"]
    assert c["nextPhysicalPlayNumber"] == str(
        int(before["content"]["nextPhysicalPlayNumber"]) + 1
    )
    assert p["play_row"]["play_number"] == int(
        before["content"]["nextPhysicalPlayNumber"]
    )
    assert p["history_entry"] == r["newHistoryEntry"]
    assert p["history_entry"]["difference"] == v8
    assert c["restored"]["current"] == r["t1"]["after"]
    assert c["activeHead"]["d2"] == v7["calculation"]["request"]["sourcePosition"]["d2"]
    assert c["d1Head"]["source"]["fingerprint"] == "wire-v1:" + "a" * 64


@pytest.mark.parametrize("field", ["event", "d5", "d2", "checkpoint", "frame"])
def test_builder_rejects_cross_binding(field):
    """同frame/CP/実event/allocatorの差替えを拒否する。"""
    from pitchlog.sync.ordinary_pitch_execution import OrdinaryPitchExecutionError

    state, record, tenant, _, _ = preparation()
    if field == "event":
        record["id"] = UUID(int=999)
    elif field == "d5":
        state.projected = __import__("dataclasses").replace(
            state.projected, d5=str(UUID(int=998))
        )
    elif field == "d2":
        state.projected = __import__("dataclasses").replace(state.projected, v6=999)
    elif field == "checkpoint":
        object.__setattr__(state.prefix, "next_play_number", 0)
    else:
        state.frame_id = None
    with pytest.raises((OrdinaryPitchExecutionError, ValueError)):
        build_nonplay_normal_preparation(state, record, tenant)


def saved_read_item():
    """保存済み全列を持つpure SQL応答fixture。実印/DB資格は主張しない。"""
    from pitchlog.db.sync_protocol.models import OperationEvent

    state, record, tenant, v7, v8 = preparation()
    p = build_nonplay_normal_preparation(state, record, tenant)
    c = p["next_checkpoint"]["checkpoint"]["content"]
    frame = {
        "play": c["activeHead"],
        "historyEntry": p["history_entry"],
        "beforeContext": p["checkpoint"]["content"]["restored"],
        "afterContext": c["restored"],
    }
    event = dict.fromkeys(OperationEvent.__table__.c.keys())
    event.update(
        id=str(record["id"]),
        game_id=state.event.game_id,
        generation=1,
        d1=state.event.d1,
        d2=state.event.v6,
        d5=state.event.d5,
        ledger_kind="accepted",
        event_kind="play_input",
        payload=v7,
        state_diff=v8,
        is_tombstone=False,
        migration_unverified=False,
        tenant_id=str(tenant),
    )
    item = {
        "kind": "accepted-ordinary-admission-v1",
        "cursor": [1, state.event.d1, str(record["id"])],
        "frame": frame,
        "event": event,
        "fingerprint": "wire-v1:" + "a" * 64,
        "wireD4": state.event.d4,
        "physical": p["next_checkpoint"]["projection_snapshot"],
    }
    return p, item, tenant


def test_new_saved_frame_reads_back_all_context_and_raw_difference():
    """新保存profileを旧Source位置へ偽装せず、次GET/次undoの文脈へ戻す。"""
    from pitchlog.repositories import nonplay_prefix_read as api

    p, item, tenant = saved_read_item()
    frame = api._frame(SimpleNamespace(_bound_tenant_id=tenant), item, lambda: None)
    assert frame["play"] == p["next_checkpoint"]["checkpoint"]["content"]["activeHead"]
    assert frame["historyEntry"] == p["history_entry"]
    assert frame["beforeContext"] == p["checkpoint"]["content"]["restored"]
    assert (
        frame["afterContext"]
        == p["next_checkpoint"]["checkpoint"]["content"]["restored"]
    )
    assert len(item["physical"]["play_row"]) == 41


@pytest.mark.parametrize(
    "mutation",
    [
        "id",
        "fingerprint",
        "d1",
        "d2",
        "number",
        "history",
        "context",
        "physical-extra",
        "physical-missing",
        "tenant",
    ],
)
def test_new_saved_frame_unknown_partial_or_cross_binding_rejected(mutation):
    """原wireを再生成せず、保存全列/意味列とframeの別参照を拒否する。"""
    from pitchlog.repositories import nonplay_prefix_read as api

    p, item, tenant = saved_read_item()
    if mutation == "id":
        item["frame"]["play"]["playId"] = str(UUID(int=999))
    elif mutation == "fingerprint":
        item["frame"]["play"]["source"]["fingerprint"] = "wire-v1:" + "b" * 64
    elif mutation == "d1":
        item["frame"]["play"]["source"]["d1"] = "1"
    elif mutation == "d2":
        item["frame"]["play"]["d2"] = "1"
    elif mutation == "number":
        item["frame"]["play"]["physicalPlayNumber"] = "1"
    elif mutation == "history":
        item["event"]["state_diff"] = {}
    elif mutation == "context":
        item["frame"]["afterContext"]["current"]["stateFields"]["state.count.balls"] = (
            "2"
        )
    elif mutation == "physical-extra":
        item["physical"]["play_row"]["unknown"] = None
    elif mutation == "physical-missing":
        del item["physical"]["play_row"]["stance"]
    else:
        item["event"]["tenant_id"] = str(UUID(int=99))
    from jsonschema import ValidationError

    from pitchlog.repositories.recorded_snapshot import RecordedSnapshotUnavailable

    with pytest.raises(
        (api.NonplaySourceUnavailable, RecordedSnapshotUnavailable, ValidationError)
    ):
        api._frame(SimpleNamespace(_bound_tenant_id=tenant), item, lambda: None)
