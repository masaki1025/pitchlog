"""同期入口の経路選択がP2に限定され、P3を成功扱いにしないことを固定する。"""

import pytest

from pitchlog.api.routers.sync import _request_path
from pitchlog.sync.apply import _E1OutOfScope
from pitchlog.sync.model import RequestShapeError


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


@pytest.mark.parametrize("stage", ["apply", "replay"])
def test_database_failure_is_503_without_ack_or_exception_values(monkeypatch, stage):
    """入口の例外写像だけを合成し、実認可・実DB成功とは扱わない。"""
    from contextlib import contextmanager
    from types import SimpleNamespace
    from uuid import UUID

    from fastapi import HTTPException
    from sqlalchemy.exc import ProgrammingError
    from test_authz_tenant_context import make_tenant_context

    from pitchlog.api.routers import sync

    tenant, game, device, attempt = (UUID(int=n) for n in (1, 2, 3, 4))
    config = SimpleNamespace(
        control_instance=UUID(int=5),
        business_instance=UUID(int=6),
        restore_epoch=UUID(int=7),
        broker_endpoint=object(),
    )
    monkeypatch.setattr(sync, "_configuration", lambda request: config)
    monkeypatch.setattr(
        sync,
        "_replay_e1_without_binding",
        lambda *args: failure() if stage == "replay" else None,
    )
    monkeypatch.setattr(sync, "_credential_digest", lambda value: b"a" * 32)
    closed = []

    @contextmanager
    def receipt(**kwargs):
        try:
            yield object()
        finally:
            closed.append(True)

    monkeypatch.setattr(sync, "_e1_receipt_scope", receipt)
    monkeypatch.setattr(sync, "e1_event_source", lambda *args: object())
    monkeypatch.setattr(
        sync, "_issue_device_presentation", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(sync, "_broker_generation", lambda *args: 1)
    monkeypatch.setattr(
        sync, "selected_event_fingerprint", lambda *args: "wire-v1:" + "a" * 64
    )
    monkeypatch.setattr(sync, "BindingControl", lambda endpoint: object())

    def failure(*args, **kwargs):
        raise ProgrammingError("private sql", {}, Exception("private diagnostic"))

    monkeypatch.setattr(sync, "_apply_e1_f1", failure)
    payload = {
        "recording_right_proof": {},
        "events": [
            {
                "d5": str(UUID(int=8)),
                "game_id": str(game),
                "d1": 1,
                "d4": "generation-A",
                "d2": 1,
                "event_kind": "1",
                "payload": {"formatVersion": "ordinary-pitch-play-v1"},
                "state_diff": {},
            }
        ],
    }
    with pytest.raises(HTTPException) as captured:
        sync.sync_events(
            game,
            payload,
            object(),
            make_tenant_context(tenant),
            "test-cookie",
            device,
            "test-credential",
            attempt,
        )
    assert captured.value.status_code == 503
    assert "private" not in str(captured.value.detail)
    assert closed == ([True] if stage == "apply" else [])
