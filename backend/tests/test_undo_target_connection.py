"""取消対象を同一TXの保存prefixから解決する接続対向。"""

from __future__ import annotations

import copy
import json
from contextlib import contextmanager
from types import MappingProxyType, SimpleNamespace
from uuid import UUID

import pytest
from test_nonplay_prefix import rig as rig
from test_nonplay_prefix import saved_item, wire_event
from test_sync_apply_port_prefix import DenyPrefixRights, PrefixRights

from pitchlog.domainrt.first_ball_projection import _canonical_json
from pitchlog.repositories import nonplay_prefix as reader
from pitchlog.repositories import transaction as tx
from pitchlog.sync import prefix_path, undo_execution
from pitchlog.sync.idempotency import (
    D5Candidate,
    StoredResult,
    _json_value,
    event_source,
)
from pitchlog.sync.model import ABSENT, SyncEvent
from pitchlog.sync.undo_ports import UndoContentValidationPort, UndoProjectionPort
from pitchlog.sync.wire_fingerprint import freeze_wire_event, wire_event_fingerprint


@pytest.fixture(autouse=True)
def _stored_sql_profile(rig):
    """正式SQLが返す保存証拠profileを使い、DTOのみから内部世代を推定しない。"""
    rig.records[:] = [saved_item(record, rig) for record in rig.records]


def _replace_request(rig, raw):
    """同一fixtureの原wire・E1選択指紋を一緒に更新する。"""
    rig.event = wire_event(raw)
    rig.source.event = rig.event
    wire = freeze_wire_event(
        json.loads(_canonical_json(_json_value(event_source(rig.event))))
    )
    rig.view.wire_event = wire
    rig.view.event_fingerprint = wire_event_fingerprint(wire)


def test_saved_event_supplies_internal_generation_and_wire_d4(rig):
    """V10から内部世代を捏造せず、保存eventとactive headを結ぶ。"""
    captured = []

    def validate(target):
        prefix_path._validate_v10(rig.event, "none", target)
        captured.append(target)

    with undo_execution._bind_undo_execution(
        rig.handle,
        rig.writer,
        rig.event,
        rig.source,
        validate_target=validate,
    ):
        assert undo_execution._EXECUTIONS[rig.handle._state_key].phase == "ready"
        token = prefix_path._event_insert_token(
            rig.event,
            UUID(rig.event.game_id),
            1,
            "none",
            "{}",
            captured[0],
            scope=rig.handle,
        )
        assert token.target_generation == rig.records[0]["event"]["generation"]
        assert token.target_d1 == rig.records[0]["cursor"][1]
    assert captured == [
        prefix_path.P1Target(
            UUID(rig.event.game_id),
            rig.records[0]["event"]["generation"],
            rig.records[0]["cursor"][1],
            rig.value["activeStack"][0]["play"]["source"]["generation"],
        )
    ]


@pytest.mark.parametrize("fault", ["wrong-d1", "wrong-d4", "missing-target"])
def test_wrong_or_absent_v10_never_issues_frame(rig, fault):
    """保存対象と異なるwire参照・欠落は同じframeへ昇格しない。"""
    raw = copy.deepcopy(rig.raw)
    if fault == "wrong-d1":
        raw["target_reference"]["d1"] = 1
    elif fault == "wrong-d4":
        raw["target_reference"]["d4"] = "other-generation"
    else:
        raw.pop("target_reference")
    if fault == "missing-target":
        e = rig.event
        rig.event = SyncEvent(e.d5, e.game_id, e.d1, e.d4, v5=e.v5, v7=e.v7, v10=ABSENT)
        rig.source.event = rig.event
    else:
        _replace_request(rig, raw)
    observed = []

    def validate(target):
        observed.append(target)
        prefix_path._validate_v10(rig.event, "none", target)

    if fault == "missing-target":
        with undo_execution._bind_undo_execution(
            rig.handle,
            rig.writer,
            rig.event,
            rig.source,
            validate_target=validate,
        ):
            assert undo_execution._EXECUTIONS[rig.handle._state_key].phase == "rejected"
        assert observed == []
    else:
        with pytest.raises(prefix_path.P1PreconditionError, match="V10"):
            with undo_execution._bind_undo_execution(
                rig.handle,
                rig.writer,
                rig.event,
                rig.source,
                validate_target=validate,
            ):
                pytest.fail("不一致対象がframeを得ました")
        assert len(observed) == 1
    assert not undo_execution._EXECUTIONS


@pytest.mark.parametrize(
    "fault", ["valid", "wrong-target", "stale-cp", "supplied-target"]
)
def test_e1_p1_resolves_target_after_d5_rights_order_before_content(
    rig, monkeypatch, fault
):
    """正式経路の最初のV10判定が保存済みtargetを使用する。"""
    if fault in {"wrong-target", "stale-cp"}:
        raw = copy.deepcopy(rig.raw)
        if fault == "wrong-target":
            raw["target_reference"]["d1"] = 1
        else:
            raw["payload"]["expectedCheckpoint"]["revision"] = "1"
        _replace_request(rig, raw)
    trace = []
    monkeypatch.setattr(
        prefix_path,
        "_lock_game_generation",
        lambda *_: (1, rig.event.d1 - 1),
    )
    monkeypatch.setattr(
        prefix_path,
        "classify_d5",
        lambda *_: trace.append("d5") or D5Candidate("unused"),
    )
    monkeypatch.setattr(
        prefix_path.port_guard, "require_registered_port", lambda *_: None
    )

    @contextmanager
    def phase(_scope, _kind):
        yield

    monkeypatch.setattr(tx, "_port_predecision_phase", phase)

    def stop_content(*_):
        state = undo_execution._EXECUTIONS[rig.handle._state_key]
        trace.append("content:" + state.phase)
        return False, "test-stop"

    monkeypatch.setattr(UndoContentValidationPort, "validate", stop_content)
    rights = PrefixRights()
    original_rights = rights.holds_recording_right

    def check_rights(*args):
        trace.append("rights")
        return original_rights(*args)

    monkeypatch.setattr(rights, "holds_recording_right", check_rights)
    supplied = (
        prefix_path.P1Target(UUID(rig.event.game_id), 1, 2)
        if fault == "supplied-target"
        else None
    )
    pattern = (
        "V10"
        if fault == "wrong-target"
        else "保存原本"
        if fault == "supplied-target"
        else "test-stop"
    )
    with pytest.raises(prefix_path.P1ContentRejection, match=pattern):
        prefix_path._apply_locked_in_scope(
            rig.handle,
            rig.event,
            rights,
            UndoProjectionPort(),
            UndoContentValidationPort(),
            None,
            None,
            supplied,
            source=rig.source,
            writer=rig.writer,
        )
    expected = ["d5", "rights"]
    if fault in {"valid", "stale-cp"}:
        expected.append("content:" + ("ready" if fault == "valid" else "rejected"))
    assert trace == expected
    assert not undo_execution._EXECUTIONS


@pytest.mark.parametrize("before_content", ["stored", "no-right", "gap"])
def test_d5_right_and_order_precede_fresh_target_read(rig, monkeypatch, before_content):
    """既結果再掲・記録権不成立・欠番は真正対象読取を起こさない。"""
    monkeypatch.setattr(
        prefix_path,
        "_lock_game_generation",
        lambda *_: (1, rig.event.d1 - (2 if before_content == "gap" else 1)),
    )
    candidate = (
        D5Candidate(
            "stored_result",
            stored=StoredResult(
                "accepted",
                "same",
                {
                    "state": "受理",
                    "d3": rig.event.d1,
                    "temporary_id_mapping": MappingProxyType({}),
                },
                None,
            ),
        )
        if before_content == "stored"
        else D5Candidate("unused")
    )
    monkeypatch.setattr(prefix_path, "classify_d5", lambda *_: candidate)
    monkeypatch.setattr(
        prefix_path.port_guard, "require_registered_port", lambda *_: None
    )

    @contextmanager
    def phase(_scope, _kind):
        yield

    monkeypatch.setattr(tx, "_port_predecision_phase", phase)
    rights = DenyPrefixRights() if before_content == "no-right" else PrefixRights()
    if before_content == "no-right":
        with pytest.raises(prefix_path.P1PreconditionError, match="記録権"):
            prefix_path._apply_locked_in_scope(
                rig.handle,
                rig.event,
                rights,
                UndoProjectionPort(),
                UndoContentValidationPort(),
                None,
                None,
                None,
                source=rig.source,
                writer=rig.writer,
            )
    else:
        result = prefix_path._apply_locked_in_scope(
            rig.handle,
            rig.event,
            rights,
            UndoProjectionPort(),
            UndoContentValidationPort(),
            None,
            None,
            None,
            source=rig.source,
            writer=rig.writer,
        )
        if before_content == "stored":
            assert result.replayed
        else:
            assert result.boundary == "B2"
    assert rig.calls == []
    assert not undo_execution._EXECUTIONS


def test_opaque_wire_d4_is_distinct_from_internal_generation():
    """正規のwire D4を内部整数へ誤変換せず、両方を照合する。"""
    game = "00000000-0000-4000-8000-000000000002"
    event = SyncEvent(
        "00000000-0000-4000-8000-000000000005",
        game,
        3,
        "d4.own",
        v5="undo",
        v7={"formatVersion": "native-undo-prefix-v1"},
        v10={"game": game, "d4": "d4.previous", "d1": 2},
    )
    prefix_path._validate_v10(
        event,
        "none",
        prefix_path.P1Target(UUID(game), 17, 2, "d4.previous"),
    )
    with pytest.raises(prefix_path.P1PreconditionError, match="V10"):
        prefix_path._validate_v10(
            event,
            "none",
            prefix_path.P1Target(UUID(game), 17, 2, "d4.other"),
        )


def test_head_position_is_same_reader_lease_and_same_top_transaction(rig, monkeypatch):
    """内部位置だけを別prefix/別top TXへ持ち出せない。"""
    with reader.read_confirmed_nonplay_prefix(
        rig.handle,
        rig.event,
        rig.source,
        artifact_sha256=rig.raw["payload"]["artifactSha256"],
    ) as prefix:
        _, _, position = reader._read_prefix(
            prefix, rig.handle, rig.source, rig.event, include_head_position=True
        )
        assert position == (
            rig.records[0]["event"]["generation"],
            rig.records[0]["event"]["d1"],
        )
        with pytest.raises(reader.NonplaySourceUnavailable):
            reader._read_prefix(
                object.__new__(reader.ConfirmedNonplayPrefix),
                rig.handle,
                rig.source,
                rig.event,
                include_head_position=True,
            )
        with monkeypatch.context() as changed:
            changed.setattr(
                rig.runtime[0],
                "get_transaction",
                lambda: SimpleNamespace(is_active=True),
            )
            with pytest.raises(reader.NonplaySourceUnavailable):
                reader._read_prefix(
                    prefix,
                    rig.handle,
                    rig.source,
                    rig.event,
                    include_head_position=True,
                )


def test_issuance_order_is_not_internal_generation(rig):
    """正式SQLの並び順7と保存内部世代1を区別して正しく保存対象へ渡す。"""
    for record in rig.records:
        record["cursor"][0] = 7
    captured = []
    with undo_execution._bind_undo_execution(
        rig.handle,
        rig.writer,
        rig.event,
        rig.source,
        validate_target=captured.append,
    ):
        assert undo_execution._EXECUTIONS[rig.handle._state_key].phase == "ready"
        assert captured[0].generation == rig.records[0]["event"]["generation"] == 1
        assert captured[0].generation != rig.records[0]["cursor"][0]
        token = prefix_path._event_insert_token(
            rig.event,
            UUID(rig.event.game_id),
            1,
            "none",
            "{}",
            captured[0],
            scope=rig.handle,
        )
        assert token.target_generation == 1


def test_forged_saved_event_generation_does_not_become_target(rig):
    """保存eventだけ世代を変えるとslot/admissionとの照合で拒否する。"""
    rig.records[0]["event"]["generation"] += 1
    with pytest.raises(reader.NonplaySourceUnavailable, match="accepted/consumed"):
        with reader.read_confirmed_nonplay_prefix(
            rig.handle,
            rig.event,
            rig.source,
            artifact_sha256=rig.raw["payload"]["artifactSha256"],
        ):
            pytest.fail("偽の内部世代が読取資格になりました")
