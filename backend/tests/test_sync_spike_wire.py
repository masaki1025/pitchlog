"""spike wire 変換の S-1 境界を DB なしで検査する。"""

from __future__ import annotations

import pytest

from pitchlog.sync.model import ABSENT, RequestShapeError, SyncRequest
from pitchlog.sync.spike_wire import to_sync_request

GAME = "123e4567-e89b-12d3-a456-426614174000"
D5 = "123e4567-e89b-12d3-a456-426614174002"
_CHANGE_LITERALS = frozenset({"play_change", "play_delete", "substitution_change"})


def _payload(
    event_kind: object = "1",
    *,
    path: str = "P1",
    game_id: str = GAME,
    **overrides: object,
) -> dict[str, object]:
    """最小の 1 球本文を作る。"""
    event: dict[str, object] = {
        "d5": D5,
        "d1": 1,
        "d4": "1",
        "game_id": game_id,
        "event_kind": event_kind,
        "d2": 0,
        "payload": {},
        "state_diff": {},
    }
    event.update(overrides)
    if path == "P3":
        return {
            "recovery_generation": "opaque",
            "recording_right_proof": "spike-proof",
            "change": event,
        }
    return {"recording_right_proof": "spike-proof", "events": [event]}


@pytest.mark.parametrize(
    ("wire_kind", "literal"),
    [
        ("1", "play_input"),
        ("2", "undo"),
        ("3", "substitution"),
        ("4", "tiebreak_start"),
        ("5", "game_end_declaration"),
        ("6", "player_registration"),
        ("7", "state_correction"),
        ("10", "play_change"),
        ("11", "play_delete"),
        ("12", "substitution_change"),
        ("play_input", "play_input"),
        ("play_delete", "play_delete"),
    ],
)
def test_event_kind_maps_numbers_and_literals(
    wire_kind: str, literal: str
) -> None:
    """種別番号の数字文字列も literal も同じ literal へ写る。"""
    request = to_sync_request("P1", GAME, _payload(wire_kind))
    assert type(request) is SyncRequest
    assert request.path == "P1"
    assert request.game_id == GAME
    assert request.events[0].v5 == literal


@pytest.mark.parametrize("kind", ["8", "9", "0", "13", "unknown_kind", "01", "١"])
def test_event_kind_rejects_unmappable_values(kind: str) -> None:
    """墓標・改訂の番号と未知の形は S-1 違反で候補分類の前に止める。"""
    with pytest.raises(RequestShapeError, match="S-1"):
        to_sync_request("P1", GAME, _payload(kind))


@pytest.mark.parametrize("kind", [1, None, ["play_input"], {"kind": "1"}])
def test_event_kind_rejects_non_string_values(kind: object) -> None:
    """文字列でない種別は S-1 違反。"""
    with pytest.raises(RequestShapeError, match="S-1"):
        to_sync_request("P1", GAME, _payload(kind))


def test_wire_keeps_d1_path_stages_from_body_fields() -> None:
    """D1 付き経路の段差は V6〜V10 の位置にそのまま固定される。"""
    request = to_sync_request(
        "P1",
        GAME,
        _payload(
            payload={"count": 2},
            state_diff={"d5_of_change": True},
        ),
    )
    event = request.events[0]
    assert event.d1 == 1
    assert event.d4 == "1"
    assert event.game_id == GAME
    assert event.d5 == D5
    assert event.v6 == 0
    assert event.v7 == {"count": 2}
    assert event.v8 == {"d5_of_change": True}
    assert event.v9 is ABSENT
    assert event.v10 is ABSENT
    assert event.v11 is ABSENT
    assert request.d4 == "1"
    assert request.v12 == "spike-proof"


def test_wire_passes_design_literal_sample_intact() -> None:
    """計画の最小本文がそのまま S-1 型になる。"""
    payload = {
        "recording_right_proof": "spike-proof",
        "events": [
            {
                "d5": "11111111-1111-4111-8111-111111111111",
                "d1": 1,
                "d4": "1",
                "game_id": "22222222-2222-4222-8222-222222222222",
                "event_kind": "play_input",
                "d2": 0,
                "payload": {},
                "state_diff": {},
            }
        ],
    }
    request = to_sync_request(
        "P1", "22222222-2222-4222-8222-222222222222", payload
    )
    assert request.v12 == "spike-proof"
    assert request.events[0].v5 == "play_input"


@pytest.mark.parametrize(
    "payload",
    [
        [],
        "play_input",
        {"recording_right_proof": "p"},
        {"events": [], "recording_right_proof": "p"},
        {"events": {}, "recording_right_proof": "p"},
        {
            "events": [_payload()["events"][0] | {"unknown": 1}],
            "recording_right_proof": "p",
        },
        {
            "events": [
                {
                    "d5": D5,
                    "game_id": GAME,
                    "d1": 1,
                    "d4": "1",
                    "event_kind": "1",
                    "d2": 0,
                    "payload": {},
                    "state_diff": {},
                    "d2_pick": 3,
                }
            ],
            "recording_right_proof": "p",
        },
    ],
)
def test_shape_violations_are_reported_as_s1(payload: object) -> None:
    """不明キー・空列・非 object は S-1 違反。"""
    with pytest.raises(RequestShapeError, match="S-1"):
        to_sync_request("P1", GAME, payload)


def test_game_id_mismatch_is_reported_as_s1() -> None:
    """URL の試合と本文の試合が一致しない要求は S-1 違反。"""
    with pytest.raises(RequestShapeError, match="S-1"):
        to_sync_request(
            "P1",
            GAME,
            _payload(game_id="123e4567-e89b-12d3-a456-426614174001"),
        )


def _p3_payload(event_kind: object = "10") -> dict[str, object]:
    """P3 の最小本文を作る。"""
    return {
        "recovery_generation": "opaque",
        "recording_right_proof": "spike-proof",
        "change": {
            "d5": D5,
            "game_id": GAME,
            "event_kind": event_kind,
            "payload": {},
            "target_reference": {"試合": GAME, "対象の D4": "1", "対象の D1": 1},
            "expected_version": 1,
        },
    }


def test_p3_change_kind_is_mapped_too() -> None:
    """P3 の変更イベントの種別番号も literal へ写る。"""
    request = to_sync_request("P3", GAME, _p3_payload("10"))
    assert request.events[0].v5 == "play_change"
    assert request.recovery_generation == "opaque"


@pytest.mark.parametrize("kind", ["11", "12", "play_delete", "substitution_change"])
def test_p3_accepts_change_kinds(kind: str) -> None:
    """変更種別の番号と literal の両方が P3 の変換を通る。"""
    request = to_sync_request("P3", GAME, _p3_payload(kind))
    assert request.events[0].v5 in _CHANGE_LITERALS


def test_p3_teardowned_numbers_are_reported_as_s1() -> None:
    """P3 でも墓標・改訂の番号は literal へ写らない。"""
    with pytest.raises(RequestShapeError, match="S-1"):
        to_sync_request("P3", GAME, _p3_payload("9"))
