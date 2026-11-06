"""P3権利Portと実関数宣言の閉入力をDBなしで検査する。"""

from __future__ import annotations

from typing import cast
from uuid import UUID

import pytest

from pitchlog.api.routers import (
    sync as sync_router,  # noqa: F401 - 実Port閉包を読み込む。
)
from pitchlog.repositories.function_operations import (
    FunctionOperationError,
    prepare_function_operation,
)
from pitchlog.repositories.operation_registry import FUNCTION_OPERATION_REGISTRY
from pitchlog.repositories.past_correction_right import _CheckP3RightToken
from pitchlog.repositories.tokens import TenantOperationResult
from pitchlog.sync import port_guard  # noqa: F401 - 実Port verifierを起動する。
from pitchlog.sync.past_correction_rights import PastCorrectionRecordingRightsPort
from pitchlog.sync.ports import _issue_port_writer, require_registered_port
from pitchlog.sync.tokens import (
    PortP3PresentedRightToken,
    PortP3RecoveryCurrentToken,
)

_GAME = UUID("10000000-0000-0000-0000-000000000002")


def test_p3_port_only_forwards_actual_boolean_and_original_v12() -> None:
    """自由Trueを作らずPort命令の元値・型を維持する。"""
    seen: list[object] = []
    writer = _issue_port_writer(
        lambda token: seen.append(token) or TenantOperationResult(((True,),))
    )
    port = PastCorrectionRecordingRightsPort()
    require_registered_port(port)
    proof = "presented-secret"
    assert port.is_recovery_generation_current(str(_GAME), "7", writer)
    assert port.holds_recording_right(str(_GAME), "2", proof, writer)
    assert type(seen[0]) is PortP3RecoveryCurrentToken
    assert seen[0].supplied == "7"
    assert type(seen[1]) is PortP3PresentedRightToken
    assert seen[1].raw_v12 is proof
    assert proof not in repr(seen[1])
    writer._close()


@pytest.mark.parametrize("supplied", ["", 0, None, False])
def test_p3_port_rejects_bad_recovery_without_running_writer(supplied: object) -> None:
    """不正世代を現世代へ既定化しない。"""
    calls: list[object] = []
    writer = _issue_port_writer(
        lambda token: calls.append(token) or TenantOperationResult(((True,),))
    )
    with pytest.raises(ValueError):
        PastCorrectionRecordingRightsPort().is_recovery_generation_current(
            str(_GAME), cast(str, supplied), writer
        )
    assert calls == []
    writer._close()


def test_p3_private_right_registration_preserves_exact_types() -> None:
    """新関数の入力・結果型を有限宣言で固定する。"""
    token = _CheckP3RightToken(
        UUID(int=1), UUID(int=2), bytes(32), UUID(int=3), _GAME, 2, 7, bytes(32)
    )
    registration, params = prepare_function_operation(
        token, UUID(int=4), FUNCTION_OPERATION_REGISTRY
    )
    assert registration.function_id == "sync_right_api.check_p3_right"
    assert params["internal_generation"] == 2
    assert params["recovery_generation"] == 7
    with pytest.raises(FunctionOperationError):
        prepare_function_operation(
            _CheckP3RightToken(
                UUID(int=1),
                UUID(int=2),
                bytes(31),
                UUID(int=3),
                _GAME,
                2,
                7,
                bytes(32),
            ),
            UUID(int=4),
            FUNCTION_OPERATION_REGISTRY,
        )
