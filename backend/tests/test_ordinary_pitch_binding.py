"""通常D1の単球lease閉形と不整合拒否。実RPC/DB資格の証拠ではない。"""

import json
from datetime import datetime, timedelta, timezone
from typing import cast
from uuid import UUID

import pytest

from pitchlog.repositories.transaction import _TenantTransaction
from pitchlog.sync.control_provider.binding_control import (
    _LEASE_CREATION,
    BindingControl,
    _BindingLease,
    _phase_snapshot_value,
    _phase_wire,
)
from pitchlog.sync.control_provider.evidence import (
    AttemptBinding,
    AuthorityBinding,
    EventPhaseBinding,
)
from pitchlog.sync.control_provider.writer_binding import (
    WriterBindingUnavailable,
    WriterIdentity,
)
from pitchlog.sync.wire_source import freeze_wire_source


def _phase(d1):
    """元D1を既指紋器へ渡し、既wire形式を再定義しない。"""
    wire = freeze_wire_source(
        game_id=str(UUID(int=6)),
        d4="generation-A",
        raw_events=(
            {
                "game_id": str(UUID(int=6)),
                "d4": "generation-A",
                "d5": str(UUID(int=9)),
                "d1": d1,
                "d2": 1001,
                "v5": "1",
                "v7": {},
                "v8": {},
            },
        ),
    )
    return EventPhaseBinding(
        AttemptBinding(
            AuthorityBinding(UUID(int=1), UUID(int=2), UUID(int=3)),
            UUID(int=4),
            UUID(int=5),
            UUID(int=6),
            "generation-A",
            1,
            UUID(int=7),
            1,
            wire.request_fingerprint,
            1,
        ),
        UUID(int=8),
        1,
        d1,
        UUID(int=9),
        wire.event_fingerprints[0],
    )


@pytest.mark.parametrize("d1", [1, 2, 3, 100001])
def test_single_event_wire_supports_positive_d1_without_wire_shape_change(d1):
    """一要求一件のままD1原値を既指紋へ束縛する。"""
    phase = _phase(d1)
    value = _phase_wire(phase, UUID(int=10), 1)
    expected = {
        "authority_id": str(UUID(int=10)),
        "control_instance": str(UUID(int=1)),
        "business_instance": str(UUID(int=2)),
        "restore_epoch": str(UUID(int=3)),
        "control_version": 1,
        "attempt_id": str(UUID(int=7)),
        "device_id": str(UUID(int=5)),
        "game_id": str(UUID(int=6)),
        "wire_d4": "generation-A",
        "internal_generation": 1,
        "codec_version": 1,
        "request_fingerprint": phase.attempt.request_fingerprint,
        "phase_id": str(UUID(int=8)),
        "d5": str(UUID(int=9)),
        "event_fingerprint": phase.event_fingerprint,
    }
    assert value == expected
    snapshot = _phase_snapshot_value(phase, UUID(int=4), value)
    assert snapshot == (
        {"tenant_id": str(UUID(int=4)), "phase": value}
        if d1 == 1
        else {"tenant_id": str(UUID(int=4)), "phase": value, "source_d1": d1}
    )


@pytest.mark.parametrize("value", [True, False, 0, -1, "2"])
def test_forced_d1_mutation_rejects_nonpositive_or_noninteger(value):
    """frozen後の強制変更にもbool/int同値を許さない。"""
    phase = _phase(2)
    object.__setattr__(phase, "d1", value)
    with pytest.raises(WriterBindingUnavailable):
        _phase_wire(phase, UUID(int=10), 1)


def test_request_and_event_fingerprint_include_actual_d1():
    """D1が変われば既両指紋も変わり、同要求と読み替えられない。"""
    first, second = _phase(2), _phase(3)
    assert first.attempt.request_fingerprint != second.attempt.request_fingerprint
    assert first.event_fingerprint != second.event_fingerprint


def test_ordinary_phase_cannot_reuse_snapshot_from_another_d1():
    """RPC前snapshotを固定し、応答後のD1だけ差替えを拒否する比較例。"""
    phase = _phase(2)
    snapshot = json.dumps(
        _phase_snapshot_value(phase, UUID(int=4), _phase_wire(phase, UUID(int=10), 1)),
        sort_keys=True,
        separators=(",", ":"),
    )
    now = datetime.now(timezone.utc)
    identity = WriterIdentity("1", "1", now, 1, now, "1")
    reply = {
        "nonce": "01" * 32,
        "lease_id": str(UUID(int=11)),
        "expires_at": (now + timedelta(seconds=30)).isoformat(),
    }
    control = object.__new__(BindingControl)
    lease = _BindingLease(
        control,
        None,
        None,
        phase,
        identity,
        reply,
        _LEASE_CREATION,
        phase_snapshot=snapshot,
    )
    assert lease._phase_snapshot == snapshot
    # 指紋をそのままに正D1だけ変更してもprivate captureが拒否する。
    object.__setattr__(phase, "d1", 3)
    with pytest.raises(WriterBindingUnavailable):
        _BindingLease(
            control,
            None,
            None,
            phase,
            identity,
            reply,
            _LEASE_CREATION,
            phase_snapshot=snapshot,
        )


def test_multi_event_attempt_and_nonfirst_position_remain_closed():
    """この単球供給を混在batch対応済みに拡張しない。"""
    phase = _phase(2)
    object.__setattr__(phase.attempt, "event_count", 2)
    with pytest.raises(WriterBindingUnavailable):
        _phase_wire(phase, UUID(int=10), 1)
    phase = _phase(2)
    object.__setattr__(phase, "position", 2)
    with pytest.raises(WriterBindingUnavailable):
        _phase_wire(phase, UUID(int=10), 1)


def test_existing_first_ball_bridge_still_rejects_d1_above_one():
    """writer供給拡張を初球frameの着手条件へ広げない。"""
    from pitchlog.sync.first_ball_bridge import _LEGACY_BRIDGE_SOURCE, _fingerprint
    from pitchlog.sync.first_ball_frame import FirstBallFrameError
    from pitchlog.sync.model import SyncEvent

    event = SyncEvent(str(UUID(int=9)), str(UUID(int=6)), 2, "generation-A", "1")
    with pytest.raises(FirstBallFrameError):
        _fingerprint(event, _LEGACY_BRIDGE_SOURCE, cast(_TenantTransaction, None))
