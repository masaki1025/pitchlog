"""同期入口の経路選択がP2に限定され、P3を成功扱いにしないことを固定する。"""

from typing import cast, get_args
from uuid import UUID

import pytest
from pydantic import ValidationError

from pitchlog.api.routers import sync as sync_router
from pitchlog.api.routers.sync import _request_path
from pitchlog.api.schemas.recording_ack import RecordingAckResponse
from pitchlog.recording_rights.initial_grant_broker import (
    InitialBrokerUnavailable,
    _broker_d4,
    _broker_generation,
)
from pitchlog.sync import http_recording_key
from pitchlog.sync.apply import _E1OutOfScope
from pitchlog.sync.model import A5Result, A5State, AckResult, RequestShapeError


def _event(**extra: object) -> dict[str, object]:
    request = {"d5": "x", "d1": 1, "d4": "d4.1.x", "game_id": "g"}
    request.update(extra)
    return request


def test_d1_event_with_d2_is_p2() -> None:
    """D2を持つD1列だけをP2として受ける。"""
    assert _request_path({"events": [_event(d2=1)]}) == "P2"


def test_p3_change_body_is_out_of_scope() -> None:
    """P3は本入口の対象外として閉拒否する（成功ACKを発行しない）。"""
    with pytest.raises(_E1OutOfScope):
        _request_path({"change": {}, "recovery_generation": "x"})


def test_d1_event_without_d2_is_out_of_scope() -> None:
    """初球P2以外のD1列は本入口で受けない。"""
    with pytest.raises(_E1OutOfScope):
        _request_path({"events": [_event()]})


@pytest.mark.parametrize(
    "payload",
    [{}, {"events": []}, {"events": "x"}, {"events": [1]}, "not-object", None],
)
def test_malformed_body_is_rejected(payload: object) -> None:
    """外形不正をP2として扱わない。"""
    with pytest.raises((RequestShapeError, _E1OutOfScope)):
        _request_path(payload)


def _ack_wire() -> dict[str, object]:
    """識別値の物理形式を解釈しない既存ACKの全項目を返す。"""
    return {
        "advancedD3": 3,
        "eventResults": [
            {"d4": "opaque-d4", "d1": 1, "d5": "opaque-d5", "a5Result": "受理"}
        ],
    }


@pytest.mark.parametrize("state", get_args(A5State.__value__))
@pytest.mark.parametrize("with_mapping", (False, True))
def test_ack_projection_keeps_all_wire_values(
    state: A5State, with_mapping: bool
) -> None:
    """既存5状態・全キーを保持し、不在の任意写像を補わない。"""
    mapping = {"temporary": "official"} if with_mapping else None
    result = AckResult(
        "B1",
        3,
        (A5Result("opaque-d4", 1, "opaque-d5", state, reason="internal"),),
        reason="internal",
        temporary_id_mapping=mapping,
    )
    expected: dict[str, object] = {
        "advancedD3": 3,
        "eventResults": [
            {"d4": "opaque-d4", "d1": 1, "d5": "opaque-d5", "a5Result": state}
        ],
    }
    if with_mapping:
        expected["playerIdMappings"] = [
            {"temporaryId": "temporary", "officialId": "official"}
        ]
    assert sync_router._ack_body(result) == expected
    assert (
        RecordingAckResponse.model_validate(expected).model_dump(
            by_alias=True, exclude_unset=True
        )
        == expected
    )


def test_ack_empty_results_zero_position_and_empty_mapping_are_preserved() -> None:
    """位置0・空結果列と、明示した空写像を欠落へ変えない。"""
    wire: dict[str, object] = {
        "advancedD3": 0,
        "eventResults": [],
        "playerIdMappings": [],
    }
    assert (
        RecordingAckResponse.model_validate(wire).model_dump(
            by_alias=True, exclude_unset=True
        )
        == wire
    )
    assert sync_router._ack_body(AckResult("B1", 0, ())) == {
        "advancedD3": 0,
        "eventResults": [],
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("advancedD3", True),
        ("advancedD3", 1.0),
        ("advancedD3", "1"),
        ("advancedD3", -1),
        ("advancedD3", None),
        ("eventResults", None),
        ("eventResults", {}),
        ("playerIdMappings", None),
        ("playerIdMappings", {}),
        ("extra", 1),
    ],
)
def test_ack_envelope_rejects_wrong_types_and_extra_keys(field: str, value: object):
    """封筒の型変換・null・余剰キーを閉拒否する。"""
    wire = _ack_wire()
    wire[field] = value
    with pytest.raises(ValidationError):
        RecordingAckResponse.model_validate(wire)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("a5Result", "unknown"),
        ("a5Result", None),
        ("d1", True),
        ("d1", "1"),
        ("d1", 1.0),
        ("d1", 0),
        ("d4", 1),
        ("d4", None),
        ("d5", 1),
        ("d5", None),
        ("extra", 1),
    ],
)
def test_ack_event_rejects_unknown_state_wrong_types_and_extra(
    field: str, value: object
):
    """イベントの未知状態・bool整数・物理識別値の変換を拒否する。"""
    item: dict[str, object] = {
        "d4": "opaque-d4",
        "d1": 1,
        "d5": "opaque-d5",
        "a5Result": "受理",
    }
    item[field] = value
    wire = _ack_wire()
    wire["eventResults"] = [item]
    with pytest.raises(ValidationError):
        RecordingAckResponse.model_validate(wire)


@pytest.mark.parametrize(
    "mapping",
    [
        {"temporaryId": "temporary"},
        {"officialId": "official"},
        {"temporaryId": 1, "officialId": "official"},
        {"temporaryId": "temporary", "officialId": None},
        {"temporaryId": "temporary", "officialId": "official", "extra": 1},
    ],
)
def test_ack_mapping_is_closed_and_keeps_string_types(mapping: dict[str, object]):
    """写像にも必須キー・文字列型・余剰拒否を適用する。"""
    wire = _ack_wire()
    wire["playerIdMappings"] = [mapping]
    with pytest.raises(ValidationError):
        RecordingAckResponse.model_validate(wire)


@pytest.mark.parametrize("field", ("advancedD3", "eventResults"))
def test_ack_requires_both_envelope_fields(field: str):
    """必須の位置・結果列の欠落を受理しない。"""
    wire = _ack_wire()
    del wire[field]
    with pytest.raises(ValidationError):
        RecordingAckResponse.model_validate(wire)


def test_actual_ack_projection_validates_before_response() -> None:
    """route宣言だけでなく実JSONResponseの前に未知状態を拒否する。"""
    result = AckResult(
        "B1", 1, (A5Result("opaque-d4", 1, "opaque-d5", cast(A5State, "unknown")),)
    )
    with pytest.raises(ValidationError):
        sync_router._ack_body(result)
    invalid_position = AckResult("B1", cast(int, True), ())
    with pytest.raises(ValidationError):
        sync_router._ack_body(invalid_position)


def test_sync_route_declares_the_same_closed_ack_model() -> None:
    """実経路の文書化と応答検証を同じDTOへ結ぶ。"""
    routes = [
        route
        for route in sync_router.router.routes
        if getattr(route, "path", None) == "/games/{game_id}/sync/events"
    ]
    assert len(routes) == 1
    assert getattr(routes[0], "response_model") is RecordingAckResponse


def test_recording_key_bridge_calls_existing_codec_once(monkeypatch) -> None:
    """同じ値・tenant・gameを既codecへ一回だけ渡し、結果を返す。"""
    tenant_id, game_id = UUID(int=1), UUID(int=2)
    calls = []

    def codec(value: str, tenant: UUID, game: UUID) -> int:
        calls.append((value, tenant, game))
        return 42

    monkeypatch.setattr(http_recording_key, "_broker_generation", codec)
    assert (
        http_recording_key._decode_recording_key("opaque-key", tenant_id, game_id) == 42
    )
    assert calls == [("opaque-key", tenant_id, game_id)]


def test_recording_key_bridge_preserves_codec_failure(monkeypatch) -> None:
    """既codecの例外を別エラーや成功値へ変換しない。"""
    failure = ValueError("test codec failure")
    calls = []

    def codec(value: str, tenant: UUID, game: UUID) -> int:
        calls.append((value, tenant, game))
        raise failure

    monkeypatch.setattr(http_recording_key, "_broker_generation", codec)
    tenant_id, game_id = UUID(int=1), UUID(int=2)
    with pytest.raises(ValueError) as caught:
        http_recording_key._decode_recording_key("opaque-key", tenant_id, game_id)
    assert caught.value is failure
    assert calls == [("opaque-key", tenant_id, game_id)]


@pytest.mark.parametrize("number", (1, 2**63 - 1))
def test_recording_key_bridge_matches_real_codec(number: int) -> None:
    """実owner付き識別値は既codecと同じ整数へ復号する。"""
    tenant_id, game_id = UUID(int=1), UUID(int=2)
    value = _broker_d4(tenant_id, game_id, number)
    assert (
        http_recording_key._decode_recording_key(value, tenant_id, game_id)
        == (_broker_generation(value, tenant_id, game_id))
        == number
    )


@pytest.mark.parametrize("change", ("tenant", "game", "invalid"))
def test_recording_key_bridge_keeps_real_codec_rejections(change: str) -> None:
    """別owner・不正識別値で既codecと同じ閉拒否例外を保持する。"""
    tenant_id, game_id = UUID(int=1), UUID(int=2)
    value = _broker_d4(tenant_id, game_id, 1)
    if change == "tenant":
        tenant_id = UUID(int=3)
    elif change == "game":
        game_id = UUID(int=3)
    else:
        value = "invalid"
    with pytest.raises(InitialBrokerUnavailable):
        _broker_generation(value, tenant_id, game_id)
    with pytest.raises(InitialBrokerUnavailable):
        http_recording_key._decode_recording_key(value, tenant_id, game_id)
