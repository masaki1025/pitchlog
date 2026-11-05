"""取消のHTTP選択・失敗応答を検査する。実認可/DB成功を代用しない。"""

from contextlib import contextmanager
from types import SimpleNamespace
from typing import cast
from uuid import UUID

import pytest
from fastapi import HTTPException, Request

from pitchlog.api.routers import sync
from pitchlog.repositories.nonplay_prefix import NonplaySourceUnavailable
from pitchlog.sync.apply import _E1OutOfScope
from pitchlog.sync.model import A5Result, AckResult
from pitchlog.sync.port_guard import require_registered_port
from pitchlog.sync.undo_execution import UndoExecutionError
from pitchlog.sync.undo_ports import UndoContentValidationPort, UndoProjectionPort


@pytest.mark.parametrize("payload", [{}, None, {"formatVersion": "unknown"}])
@pytest.mark.parametrize("d2", [None, 123])
def test_undo_shape_selection_does_not_validate_v7_before_d5(payload, d2):
    """既D5異内容の検査より前に、V7や余計なV6でmodeを変えない。"""
    event = {"event_kind": "undo", "payload": payload}
    if d2 is not None:
        event["d2"] = d2
    assert sync._request_path({"events": [event]}) == "P1"


def test_mixed_or_multiple_undo_requests_are_not_newly_enabled():
    """初回接続を全操作batch対応の成功としない。"""
    with pytest.raises(_E1OutOfScope):
        sync._request_path({"events": [{"event_kind": "undo"}, {"d2": 1}]})


def test_only_actual_undo_port_classes_are_registered():
    """静的閉包検査を通り、派生/同名の代替Portは拒否する。"""
    require_registered_port(UndoContentValidationPort())
    require_registered_port(UndoProjectionPort())
    from pitchlog.sync.ports import PortRegistrationError

    class Other:
        pass

    with pytest.raises(PortRegistrationError):
        require_registered_port(Other())


@pytest.fixture
def route_setup(monkeypatch):
    """外部境界を明示doubleとし、実handlerの選択と例外伝播だけを見る。"""
    from test_authz_tenant_context import make_tenant_context

    tenant, game, device, attempt = (UUID(int=n) for n in (1, 2, 3, 4))
    monkeypatch.setattr(
        sync,
        "_configuration",
        lambda request: SimpleNamespace(
            control_instance=UUID(int=5),
            business_instance=UUID(int=6),
            restore_epoch=UUID(int=7),
            broker_endpoint=object(),
        ),
    )
    monkeypatch.setattr(sync, "_replay_e1_without_binding", lambda *args: None)
    monkeypatch.setattr(sync, "_credential_digest", lambda value: b"a" * 32)

    @contextmanager
    def receipt(**kwargs):
        yield object()

    monkeypatch.setattr(sync, "_e1_receipt_scope", receipt)
    monkeypatch.setattr(sync, "e1_event_source", lambda *args: object())
    monkeypatch.setattr(
        sync, "_issue_device_presentation", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(
        sync, "selected_event_fingerprint", lambda *args: "wire-v1:" + "a" * 64
    )
    monkeypatch.setattr(sync, "BindingControl", lambda endpoint: object())
    monkeypatch.setattr(
        "pitchlog.sync.http_recording_key._broker_generation", lambda *args: 1
    )
    payload = {
        "recording_right_proof": {},
        "events": [
            {
                "d5": str(UUID(int=8)),
                "game_id": str(game),
                "d1": 3,
                "d4": "generation-A",
                "event_kind": "undo",
                "payload": {},
            }
        ],
    }

    def call():
        return sync.sync_events(
            game,
            payload,
            cast(Request, object()),
            make_tenant_context(tenant),
            "test-cookie",
            device,
            "test-credential",
            attempt,
        )

    return call


@pytest.mark.parametrize("error", [UndoExecutionError, NonplaySourceUnavailable])
def test_real_handler_selects_undo_and_returns_no_ack_on_unavailable(
    monkeypatch, route_setup, error
):
    """原本/host不明は503へ閉じ、偽の受理ACKを作らない。"""
    called = []

    def unavailable(*args, **kwargs):
        assert type(kwargs["projection"]) is UndoProjectionPort
        assert type(kwargs["validator"]) is UndoContentValidationPort
        assert args[2].path == "P1"
        called.append(True)
        raise error("private source diagnostic")

    monkeypatch.setattr(sync, "_apply_e1_f1", unavailable)
    with pytest.raises(HTTPException) as caught:
        route_setup()
    assert called == [True]
    assert caught.value.status_code == 503
    assert "private" not in str(caught.value.detail)


def test_stored_replay_does_not_require_fresh_credentials_or_undo_ports(
    monkeypatch, route_setup
):
    """既handlerのDI2経路を保持し、新しい原本やhostを要求しない。"""
    stored = AckResult(
        "B1", 3, (A5Result("generation-A", 3, str(UUID(int=8)), "重複"),)
    )
    monkeypatch.setattr(sync, "_replay_e1_without_binding", lambda *args: stored)
    monkeypatch.setattr(
        sync, "_credential_digest", lambda value: pytest.fail("fresh credential")
    )
    monkeypatch.setattr(
        sync, "_apply_e1_f1", lambda *args, **kwargs: pytest.fail("fresh kernel")
    )
    response = route_setup()
    assert response.status_code == 200
    assert b'"advancedD3":3' in response.body
