"""E-1 のその場登録 wire が閉じた選手作成値へ写ることを確かめる。"""

from __future__ import annotations

from types import MappingProxyType
from uuid import uuid4

import pytest

from pitchlog.sync.idempotency import D5Candidate, StoredResult, operation_fingerprint
from pitchlog.sync.model import RequestShapeError, SyncEvent
from pitchlog.sync.player_registration_wire import read_player_registrations
from pitchlog.sync.prefix_path import PlayerRegistration, _candidate_result


def _event(*, registration: dict[str, object] | None = None) -> dict[str, object]:
    temporary = uuid4()
    if registration is None:
        registration = {
            "temporary_id": str(temporary),
            "team_record_id": str(uuid4()),
            "name": "その場登録選手",
            "roster_status_key": "active",
        }
    return {
        "d5": str(uuid4()),
        "d1": 3,
        "d4": "generation-1",
        "game_id": str(uuid4()),
        "event_kind": "player_registration",
        "payload": {"player_id": registration["temporary_id"]},
        "registration": registration,
    }


def test_reads_registration_and_maps_by_d5() -> None:
    """正しい登録イベントを D5 ごとの選手作成値へ写す。"""
    event = _event()
    d5 = event["d5"]
    payload = event["payload"]
    assert isinstance(d5, str) and isinstance(payload, dict)
    registrations = read_player_registrations((event,))
    registration = registrations[d5]
    assert str(registration.temporary_id) == payload["player_id"]
    assert registration.name == "その場登録選手"
    assert registration.roster_status_key == "active"
    assert registration.throws is None
    assert registration.bats is None
    assert registration.uniform_number is None


def test_reads_optional_player_attributes() -> None:
    """オンライン名簿登録と同じ任意項目を断中登録でも保持する。"""
    event = _event()
    registration = event["registration"]
    d5 = event["d5"]
    assert isinstance(registration, dict) and isinstance(d5, str)
    registration.update({"throws": "left", "bats": "both", "uniform_number": "18"})
    parsed = read_player_registrations((event,))[d5]
    assert (parsed.throws, parsed.bats, parsed.uniform_number) == (
        "left",
        "both",
        "18",
    )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda event: event.pop("registration"),
        lambda event: event["registration"].update({"name": ""}),
        lambda event: event["registration"].update({"name": " 前後空白 "}),
        lambda event: event["registration"].update({"team_record_id": "not-uuid"}),
        lambda event: event["registration"].update({"extra": "x"}),
        lambda event: event["registration"].pop("roster_status_key"),
        lambda event: event["payload"].update({"player_id": str(uuid4())}),
        lambda event: event["payload"].update({"team_record_id": str(uuid4())}),
        lambda event: event["registration"].update({"throws": "switch"}),
        lambda event: event["registration"].update({"bats": "unknown"}),
    ],
)
def test_rejects_shape_and_temporary_id_mismatch(mutate) -> None:
    """欠落・未知キー・一時 ID の食い違いを S-1 で拒否する。"""
    event = _event()
    mutate(event)
    with pytest.raises(RequestShapeError):
        read_player_registrations((event,))


def test_rejects_registration_on_other_event_kind() -> None:
    """登録以外のイベントに registration を混ぜない。"""
    event = _event()
    event["event_kind"] = "substitution"
    with pytest.raises(RequestShapeError, match="その場登録以外"):
        read_player_registrations((event,))


def test_optional_fields_change_fingerprint_only_when_present() -> None:
    """未指定の既存 4 項目は同じ指紋のまま、任意項目は別内容として区別する。"""
    temporary, team = uuid4(), uuid4()
    base = PlayerRegistration(temporary, team, "選手", "active")
    same = PlayerRegistration(temporary, team, "選手", "active")
    extended = PlayerRegistration(
        temporary,
        team,
        "選手",
        "active",
        throws="right",
        bats="left",
        uniform_number="1",
    )
    event = SyncEvent(
        str(uuid4()), str(uuid4()), 1, "d4", v5="player_registration", v7={}
    )
    assert operation_fingerprint(event, "P1", base) == operation_fingerprint(
        event, "P1", same
    )
    assert operation_fingerprint(event, "P1", base) != operation_fingerprint(
        event, "P1", extended
    )


def test_player_registration_rejects_out_of_range_values() -> None:
    """選択値と任意文字列を選手作成 operation と同じ値域へ閉じる。"""
    with pytest.raises(ValueError):
        PlayerRegistration(uuid4(), uuid4(), "選手", "active", throws="switch")
    with pytest.raises(ValueError):
        PlayerRegistration(uuid4(), uuid4(), "選手", "active", bats="unknown")
    with pytest.raises(ValueError):
        PlayerRegistration(uuid4(), uuid4(), "選手", "active", uniform_number="")


def test_saved_registration_replays_same_mapping() -> None:
    """ACK 消失後の再送は保存済みの同じ写像を再掲し、別選手を作らない。"""
    temporary, official = uuid4(), uuid4()
    candidate = D5Candidate(
        kind="stored_result",
        stored=StoredResult(
            "accepted",
            "fingerprint",
            MappingProxyType(
                {
                    "state": "受理",
                    "d3": 4,
                    "temporary_id_mapping": MappingProxyType(
                        {str(temporary): str(official)}
                    ),
                }
            ),
            None,
        ),
    )
    replay = _candidate_result(candidate, 3)
    assert replay is not None
    assert replay.accepted and replay.replayed
    assert replay.d3 == 4
    assert replay.temporary_id_mapping == ((str(temporary), str(official)),)


def test_same_d5_with_different_registration_is_b3b() -> None:
    """同じ D5 の異内容は B3b とし、保存済み写像を上書きしない。"""
    replay = _candidate_result(D5Candidate(kind="conflict"), 3)
    assert replay is not None
    assert (replay.accepted, replay.boundary) == (False, "B3b")
    assert replay.temporary_id_mapping == ()
