"""P3内容Portが自由な成功値とphase外呼出を拒否する対向。"""

from __future__ import annotations

from uuid import UUID

import pytest

from pitchlog.repositories import transaction
from pitchlog.repositories.tokens import ImmutableValue, TenantOperationResult
from pitchlog.sync.model import SyncEvent
from pitchlog.sync.past_correction_ports import (
    PastCorrectionContentValidationPort,
    ValidateP3CorrectionToken,
)
from pitchlog.sync.ports import _issue_port_writer


def _event() -> SyncEvent:
    """P3元参照の最小形。"""
    return SyncEvent(str(UUID(int=1)), str(UUID(int=2)), v5="play_change")


@pytest.mark.parametrize(
    "rows",
    [(), ((True, "任意の理由"),), ((False, "任意の理由"),), ((1, None),)],
)
def test_p3_content_port_rejects_unbound_values(
    rows: tuple[tuple[ImmutableValue, ...], ...],
):
    """自由boolや未知理由からP3内容の成功・B14を作らない。"""
    writer = _issue_port_writer(lambda _token: TenantOperationResult(rows))
    try:
        with pytest.raises(RuntimeError, match="P3内容Port"):
            PastCorrectionContentValidationPort().validate(_event(), writer)
    finally:
        writer._close()


def test_p3_content_command_without_actual_phase_is_closed() -> None:
    """同writerらしいtokenでもactual content phaseがなければ実行しない。"""
    writer = _issue_port_writer(lambda _token: TenantOperationResult(((True, None),)))
    event = _event()
    token = ValidateP3CorrectionToken(
        UUID(event.game_id), UUID(event.d5), event, writer
    )

    class Handle:
        _state_key = object()

    try:
        with pytest.raises(transaction.TenantBindingError, match="P3内容Port"):
            transaction._execute_port_command(Handle(), token)
    finally:
        writer._close()
