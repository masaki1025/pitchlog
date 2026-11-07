"""P3読取のtransport分離がowner参照と失敗境界を保つか検査する。"""

from pathlib import Path
from typing import cast
from uuid import UUID

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError

from pitchlog.api.routers import sync
from pitchlog.recording_rights.initial_grant_broker import (
    InitialBrokerUnavailable,
    _broker_d4,
)
from pitchlog.repositories import transaction
from pitchlog.repositories.binding import TenantBindingError
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.past_correction_current import (
    PastCorrectionCurrentUnavailable,
)
from pitchlog.repositories.past_correction_source import PastCorrectionSourceUnavailable
from pitchlog.sync.control_provider.binding_client import BindingClientConfiguration
from pitchlog.sync.control_provider.evidence import AttemptBinding, AuthorityBinding
from pitchlog.sync.past_correction_http_service import (
    change_attempt_binding,
    read_change_confirmation_snapshot,
    read_change_target_snapshot,
)

_TENANT = UUID(int=1)
_GAME = UUID(int=2)
_DEVICE = UUID(int=3)
_ATTEMPT = UUID(int=4)
_AUTHORITY = AuthorityBinding(UUID(int=5), UUID(int=6), UUID(int=7))
_CONFIGURATION = BindingClientConfiguration(
    Path("/test-only/public.sock"), UUID(int=5), UUID(int=6), UUID(int=7), 1
)


@pytest.mark.parametrize("position", [1, 2, 2**53, 2**63 - 1])
def test_opaque_owner_reference_builds_the_same_attempt(position):
    """既codecと同じ実位置・全識別値・FPを一切補正せず保持する。"""
    wire = _broker_d4(_TENANT, _GAME, position)
    actual = change_attempt_binding(
        _CONFIGURATION, _TENANT, _DEVICE, _GAME, wire, _ATTEMPT, "a" * 64
    )
    assert actual == AttemptBinding(
        _AUTHORITY,
        _TENANT,
        _DEVICE,
        _GAME,
        wire,
        position,
        _ATTEMPT,
        1,
        "a" * 64,
        1,
    )


@pytest.mark.parametrize("wrong", ["tenant", "game", "wire"])
def test_opaque_reference_cannot_be_rebound_to_another_owner(wrong):
    """別tenant/試合/破損参照を既通信不確定型のまま拒否する。"""
    wire = _broker_d4(_TENANT, _GAME, 1)
    tenant = UUID(int=8) if wrong == "tenant" else _TENANT
    game = UUID(int=9) if wrong == "game" else _GAME
    if wrong == "wire":
        wire += "="
    with pytest.raises(InitialBrokerUnavailable):
        change_attempt_binding(
            _CONFIGURATION, tenant, _DEVICE, game, wire, _ATTEMPT, "a" * 64
        )


@pytest.mark.parametrize(
    "read", [read_change_target_snapshot, read_change_confirmation_snapshot]
)
def test_unissued_context_is_rejected_before_any_database_access(monkeypatch, read):
    """serviceを直呼びしても真正tenant scopeを迂回できない。"""

    def forbidden_engine():
        pytest.fail("未発行contextで業務接続へ到達した")

    monkeypatch.setattr(transaction, "create_database_engine", forbidden_engine)
    with pytest.raises(TenantBindingError):
        read(_GAME, 1, cast(TenantContext, object()))


@pytest.mark.parametrize(
    ("route", "service", "error", "status"),
    [
        (
            sync.read_sync_change_target,
            "read_change_target_snapshot",
            PastCorrectionSourceUnavailable(),
            409,
        ),
        (
            sync.read_sync_change_target,
            "read_change_target_snapshot",
            SQLAlchemyError(),
            503,
        ),
        (
            sync.read_sync_change_confirmation,
            "read_change_confirmation_snapshot",
            PastCorrectionCurrentUnavailable(),
            409,
        ),
        (
            sync.read_sync_change_confirmation,
            "read_change_confirmation_snapshot",
            InitialBrokerUnavailable(),
            409,
        ),
        (
            sync.read_sync_change_confirmation,
            "read_change_confirmation_snapshot",
            SQLAlchemyError(),
            503,
        ),
    ],
)
def test_transport_preserves_the_existing_failure_status(
    monkeypatch, route, service, error, status
):
    """既service例外を別成功や認可結果へ読み替えないtransport単体検査。"""

    def fail(*_args):
        raise error

    monkeypatch.setattr(sync, service, fail)
    with pytest.raises(HTTPException) as failure:
        route(_GAME, 1, cast(TenantContext, object()))
    assert failure.value.status_code == status
