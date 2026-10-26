"""初球候補のimportや任意nonceで実登録されないことを確認する。"""

from uuid import UUID

import pytest

from pitchlog.repositories.first_ball import _BindFirstBallDeviceToken
from pitchlog.repositories.function_operations import (
    FunctionOperationError,
    prepare_function_operation,
)
from pitchlog.repositories.operation_registry import FUNCTION_OPERATION_REGISTRY
from pitchlog.sync.port_guard import require_registered_port
from pitchlog.sync.ports import PORT_IMPLEMENTATIONS, PortRegistrationError


def test_no_runtime_registration_or_scalar_proof() -> None:
    """候補tokenや常trueオブジェクトは実Portにならない。"""
    token = _BindFirstBallDeviceToken(
        UUID(int=1), UUID(int=2), bytes(32), UUID(int=3), UUID(int=4), bytes(32)
    )
    with pytest.raises(FunctionOperationError):
        prepare_function_operation(token, UUID(int=5), FUNCTION_OPERATION_REGISTRY)
    assert not PORT_IMPLEMENTATIONS
    with pytest.raises(PortRegistrationError):
        require_registered_port(object())
