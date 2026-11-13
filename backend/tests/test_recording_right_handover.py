"""通常引き継ぎの閉wire・明示確認・SQL境界を固定する。"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from pydantic import SecretStr, ValidationError
from starlette.requests import Request

from pitchlog.api.schemas.handover import (
    HandoverGrantResponse,
    HandoverReleaseRequest,
    HandoverReleaseResponse,
)
from pitchlog.recording_rights import initial_grant_broker as broker
from pitchlog.sync.d4_reference import encode_d4_reference

_TENANT = UUID("11111111-1111-4111-8111-111111111111")
_GAME = UUID("22222222-2222-4222-8222-222222222222")
_FROM_DEVICE = UUID("33333333-3333-4333-8333-333333333333")
_TO_DEVICE = UUID("44444444-4444-4444-8444-444444444444")
_REQUEST = UUID("55555555-5555-4555-8555-555555555555")
_BODY = (
    Path(__file__).resolve().parents[2]
    / "contracts/authz/product/function-bodies/functions"
    / (
        "FUNCTION:initial_right_api:insert_handover_grant("
        "uuid, uuid, uuid, uuid, uuid, uuid, bytea, bigint, bytea, bigint, "
        "bigint, bigint, bytea, text, bytea, bytea).sql"
    )
)


def _identity() -> broker._BrokerIdentity:
    return broker._BrokerIdentity(_TENANT, uuid4(), SecretStr("cookie"))


def _release() -> broker._ReleaseHandoverCommand:
    return broker._ReleaseHandoverCommand(
        _identity(),
        _GAME,
        _REQUEST,
        _FROM_DEVICE,
        _TO_DEVICE,
        7,
        SecretStr("old-credential"),
        SecretStr("A" * 43),
        12,
    )


def _acquire() -> broker._AcquireHandoverCommand:
    return broker._AcquireHandoverCommand(
        _identity(), _GAME, _REQUEST, _TO_DEVICE, SecretStr("new-credential")
    )


def test_handover_commands_roundtrip_without_secret_repr() -> None:
    """解放/取得の閉wireを相互検証し、資格をreprへ出さない。"""
    for command in (_release(), _acquire()):
        frame = broker._encode_initial_command(command)
        decoded = broker._decode_initial_command(frame)
        assert decoded == command
        assert broker._encode_initial_command(decoded) == frame
        assert "old-credential" not in repr(command)
        assert "new-credential" not in repr(command)
        assert "cookie" not in repr(command)


def test_release_request_requires_explicit_confirmation() -> None:
    """confirm_release が true でない解放要求を外形で拒否する。"""
    payload = {
        "handover_request_id": str(_REQUEST),
        "to_device_id": str(_TO_DEVICE),
        "from_d4": "d4.1." + "A" * 55,
        "last_d1": 3,
        "recording_right_proof": "A" * 43,
        "confirm_release": False,
    }
    with pytest.raises(ValidationError):
        HandoverReleaseRequest.model_validate(payload)
    payload["confirm_release"] = True
    assert HandoverReleaseRequest.model_validate(payload).last_d1 == 3


def test_handover_replies_roundtrip_and_expose_new_proof_only_to_acquire() -> None:
    """解放応答に秘密を含めず、取得応答だけが新V12を持つ。"""
    release = HandoverReleaseResponse(
        tenant_id=_TENANT,
        game_id=_GAME,
        handover_request_id=_REQUEST,
        from_device_id=_FROM_DEVICE,
        from_generation="7",
        to_device_id=_TO_DEVICE,
        last_d1=12,
        released_at=datetime.now(UTC),
    )
    command = _release()
    reply = broker._BrokerReply("released", release)
    frame = broker._encode_initial_reply(command, reply)
    assert broker._decode_initial_reply(frame, command) == reply
    assert b"credential" not in frame

    grant = HandoverGrantResponse(
        tenant_id=_TENANT,
        game_id=_GAME,
        handover_request_id=_REQUEST,
        device_id=_TO_DEVICE,
        d4=encode_d4_reference(_TENANT, _GAME, 8),
        recovery_generation="1",
        recording_right_proof=SecretStr("B" * 43),
    )
    acquire = _acquire()
    frame = broker._encode_initial_reply(
        acquire, broker._BrokerReply("acquired", grant)
    )
    assert b"B" * 43 in frame
    assert "B" * 43 not in grant.model_dump_json()
    assert broker._decode_initial_reply(frame, acquire).value == grant


def test_handover_sql_revokes_old_generation_and_checks_d3_before_insert() -> None:
    """旧世代失効・D3照合・新世代0水位・attempt確定を同一本文で固定する。"""
    sql = _BODY.read_text(encoding="utf-8")
    assert "p_last_d1<0" in sql
    assert "v_current.confirmed_watermark < p_last_d1" in sql
    assert "v_current.applied_prefix < p_last_d1" in sql
    assert "v_current.holder_device IS DISTINCT FROM p_from_device_id::text" in sql
    assert "v_current.proof_digest IS DISTINCT FROM p_from_proof_digest" in sql
    assert "UPDATE public.recording_generations AS r" in sql
    assert "SET revoked_at=CURRENT_TIMESTAMP" in sql
    assert "'normal',v_order,p_device_id::text" in sql
    assert "0,0,p_proof_digest,p_recovery_generation" in sql
    assert "outcome='committed'" in sql
    assert "GRANT EXECUTE ON FUNCTION initial_right_api.insert_handover_grant" in sql
    assert "TO pitchlog_initial_actor" in sql
    assert "FROM PUBLIC, pitchlog_app" in sql


def _request(challenge: UUID) -> Request:
    """Route が読む challenge だけを持つ最小の ASGI request を作る。"""
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/games/x/recording-right/handover",
            "headers": [
                (b"x-pitchlog-tenant-challenge", str(challenge).encode("ascii"))
            ],
        }
    )


def test_release_route_uses_broker_and_returns_no_new_proof(monkeypatch) -> None:
    """実API形がbrokerを呼び、解放応答へ新V12を混ぜない。"""
    from test_authz_tenant_context import make_tenant_context

    from pitchlog.api.routers import games
    from pitchlog.api.schemas.handover import HandoverReleaseRequest

    challenge = uuid4()
    response = HandoverReleaseResponse(
        tenant_id=_TENANT,
        game_id=_GAME,
        handover_request_id=_REQUEST,
        from_device_id=_FROM_DEVICE,
        from_generation="7",
        to_device_id=_TO_DEVICE,
        last_d1=12,
        released_at=datetime.now(UTC),
    )

    class FakeClient:
        def call(self, command):
            assert type(command) is broker._ReleaseHandoverCommand
            assert command.from_generation == 7
            assert command.last_d1 == 12
            return broker._BrokerReply("released", response)

    monkeypatch.setattr(games, "_InitialBrokerClient", FakeClient)
    payload = HandoverReleaseRequest(
        handover_request_id=_REQUEST,
        to_device_id=_TO_DEVICE,
        from_d4=encode_d4_reference(_TENANT, _GAME, 7),
        last_d1=12,
        recording_right_proof=SecretStr("A" * 43),
        confirm_release=True,
    )
    result = games.release_recording_right_handover(
        _GAME,
        payload,
        _request(challenge),
        make_tenant_context(_TENANT),
        "cookie",
        _FROM_DEVICE,
        "old-credential",
    )
    body = json.loads(bytes(result.body))
    assert body["from_generation"] == "7"
    assert "recording_right_proof" not in body


def test_acquire_route_returns_raw_proof_and_unresolved_is_409(monkeypatch) -> None:
    """取得成功だけが新V12を返し、未解放は409へ閉じる。"""
    from test_authz_tenant_context import make_tenant_context

    from pitchlog.api.routers import games
    from pitchlog.api.schemas.handover import HandoverAcquireRequest

    challenge = uuid4()
    grant = HandoverGrantResponse(
        tenant_id=_TENANT,
        game_id=_GAME,
        handover_request_id=_REQUEST,
        device_id=_TO_DEVICE,
        d4=encode_d4_reference(_TENANT, _GAME, 8),
        recovery_generation="1",
        recording_right_proof=SecretStr("B" * 43),
    )
    state = {"reply": broker._BrokerReply("acquired", grant)}

    class FakeClient:
        def call(self, command):
            assert type(command) is broker._AcquireHandoverCommand
            return state["reply"]

    monkeypatch.setattr(games, "_InitialBrokerClient", FakeClient)
    payload = HandoverAcquireRequest(handover_request_id=_REQUEST)
    result = games.acquire_recording_right_handover(
        _GAME,
        payload,
        _request(challenge),
        make_tenant_context(_TENANT),
        "cookie",
        _TO_DEVICE,
        "new-credential",
    )
    body = json.loads(bytes(result.body))
    assert body["recording_right_proof"] == "B" * 43
    state["reply"] = broker._BrokerReply("unresolved")
    with pytest.raises(HTTPException) as error:
        games.acquire_recording_right_handover(
            _GAME,
            payload,
            _request(challenge),
            make_tenant_context(_TENANT),
            "cookie",
            _TO_DEVICE,
            "new-credential",
        )
    assert error.value.status_code == 409


def test_initial_handover_operation_is_registered_with_its_own_capability() -> None:
    """新SQLは既初期registryへ別capabilityとして登録され、旧9へ混ぜない。"""
    from pitchlog.repositories.initial_recording_right import (
        INITIAL_FUNCTION_OPERATIONS,
        _InsertHandoverGrantToken,
    )

    spec = next(
        item
        for item in INITIAL_FUNCTION_OPERATIONS
        if item.function_id == "initial_right_api.insert_handover_grant"
    )
    assert spec.capability_id == "CAP:initial_right:insert_handover_grant"
    assert spec.token_type is _InsertHandoverGrantToken
    assert tuple(name for name, _ in spec.input_fields) == (
        "game_id",
        "start_request_id",
        "device_id",
        "attempt_id",
        "from_device_id",
        "from_credential_digest",
        "from_generation",
        "from_proof_digest",
        "last_d1",
        "generation",
        "recovery_generation",
        "proof_digest",
        "key_id",
        "nonce",
        "ciphertext",
    )
    assert spec.min_rows == spec.max_rows == 1
