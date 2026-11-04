"""単位AのSQL-free Port/値命令。正式issuer/投影保存の成功ではない。"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from pitchlog.repositories.tokens import TenantOperationResult
from pitchlog.sync.first_ball_ports import FirstBallContentValidationPort
from pitchlog.sync.model import SyncEvent
from pitchlog.sync.port_guard import require_registered_port
from pitchlog.sync.ports import PORT_IMPLEMENTATIONS, _issue_port_writer
from pitchlog.sync.tokens import PortValidateFirstBallToken


def test_port_real_guard_and_original_event_command():
    """実import閉包検査を通し、元参照だけを有限命令で渡す。"""
    port = FirstBallContentValidationPort()
    require_registered_port(port)
    assert PORT_IMPLEMENTATIONS == frozenset(
        {
            ("pitchlog.sync.first_ball_ports", "FirstBallContentValidationPort"),
            (
                "pitchlog.sync.ordinary_pitch_ports",
                "OrdinaryPitchContentValidationPort",
            ),
            ("pitchlog.sync.ordinary_pitch_ports", "OrdinaryPitchProjectionPort"),
            ("pitchlog.sync.ordinary_pitch_ports", "PlayPrefixContentValidationPort"),
            ("pitchlog.sync.ordinary_pitch_ports", "PlayPrefixProjectionPort"),
            ("pitchlog.sync.first_ball_projection", "FirstBallProjectionPort"),
            (
                "pitchlog.sync.first_ball_recording_rights",
                "FirstBallRecordingRightsPort",
            ),
        }
    )
    event = SyncEvent(str(uuid4()), str(uuid4()), 1, "d4", "1")
    seen = []

    def run(token):
        seen.append(token)
        return TenantOperationResult(((True, None),))

    writer = _issue_port_writer(run)
    assert port.validate(event, writer) == (True, None)
    assert len(seen) == 1 and type(seen[0]) is PortValidateFirstBallToken
    assert seen[0].writer is writer
    assert (
        seen[0].event is event
        and seen[0].game_id == UUID(event.game_id)
        and seen[0].d5 == UUID(event.d5)
    )
    assert seen[0].capability_id == "CAP:operation_events:read"
    writer._close()
    with pytest.raises(RuntimeError):
        port.validate(event, writer)


@pytest.mark.parametrize(
    "rows",
    [
        (),
        ((True,),),
        ((True, None), (True, None)),
        ((1, None),),
        ((False, None),),
        ((True, "reason"),),
        ((False, ""),),
    ],
)
def test_partial_or_coerced_command_reply_never_becomes_success(rows):
    """bool/件数/理由の不正を正規化しない。"""
    writer = _issue_port_writer(lambda _: TenantOperationResult(rows))
    event = SyncEvent(str(uuid4()), str(uuid4()), 1, "d4", "1")
    with pytest.raises(RuntimeError):
        FirstBallContentValidationPort().validate(event, writer)
    writer._close()
