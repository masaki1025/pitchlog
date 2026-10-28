"""Port 登録の閉集合と、未登録型・常true object が実 Port にならないことを確認する。"""

from uuid import UUID

import pytest

from pitchlog.repositories.function_operations import (
    FunctionOperationError,
    prepare_function_operation,
)
from pitchlog.repositories.operation_registry import FUNCTION_OPERATION_REGISTRY
from pitchlog.sync.port_guard import require_registered_port
from pitchlog.sync.ports import PORT_IMPLEMENTATIONS, PortRegistrationError

# 監査済みの閉集合。増減は Port 登録の独立レビューを要し、この値を書き換えるだけでは通さない。
_EXPECTED_PORTS = frozenset(
    {
        ("pitchlog.sync.first_ball_ports", "FirstBallContentValidationPort"),
        ("pitchlog.sync.first_ball_projection", "FirstBallProjectionPort"),
        ("pitchlog.sync.first_ball_recording_rights", "FirstBallRecordingRightsPort"),
    }
)


class _AlwaysTrue:
    """任意の問いへ True を返す常true object。"""

    def __getattr__(self, name: str) -> bool:
        """未知の属性にも True を返す。"""
        return True


def test_port_registry_is_the_audited_closed_set() -> None:
    """実 Port の登録集合を過不足なく固定する。"""
    assert PORT_IMPLEMENTATIONS == _EXPECTED_PORTS


def test_unregistered_objects_are_not_ports_or_operations() -> None:
    """未登録型・常true object は実行にも Port 登録にも到達しない。"""
    with pytest.raises(PortRegistrationError):
        require_registered_port(object())
    with pytest.raises(PortRegistrationError):
        require_registered_port(_AlwaysTrue())
    with pytest.raises(FunctionOperationError):
        prepare_function_operation(object(), UUID(int=5), FUNCTION_OPERATION_REGISTRY)
    with pytest.raises(FunctionOperationError):
        prepare_function_operation(_AlwaysTrue(), UUID(int=5), FUNCTION_OPERATION_REGISTRY)
