"""その場登録の内容確認・投影ポートが閉じた参照だけを受けることを確かめる。"""

from __future__ import annotations

from uuid import uuid4

import pytest

from pitchlog.repositories.tokens import TenantOperationResult
from pitchlog.sync.model import SyncEvent
from pitchlog.sync.player_registration_ports import (
    PlayerRegistrationContentValidationPort,
    PlayerRegistrationProjectionPort,
)
from pitchlog.sync.ports import PortWriter, _issue_port_writer


def _writer() -> PortWriter:
    return _issue_port_writer(lambda _: TenantOperationResult(()))


def _event(*, kind: str = "player_registration", v7: object | None = None) -> SyncEvent:
    return SyncEvent(
        str(uuid4()),
        str(uuid4()),
        2,
        "generation-1",
        v5=kind,
        v7={"player_id": str(uuid4())} if v7 is None else v7,
    )


def test_content_port_accepts_closed_temporary_reference() -> None:
    """V5 と一時 ID 1 件だけの V7 を内容段で受理する。"""
    assert PlayerRegistrationContentValidationPort().validate(_event(), _writer()) == (
        True,
        None,
    )


@pytest.mark.parametrize(
    ("event", "reason"),
    [
        (_event(kind="substitution"), "イベント種別"),
        (_event(v7={}), "V7"),
        (_event(v7={"player_id": "not-uuid"}), "V7"),
        (_event(v7={"player_id": str(uuid4()), "extra": 1}), "V7"),
        (
            SyncEvent(
                str(uuid4()),
                str(uuid4()),
                2,
                "generation-1",
                v5="player_registration",
                v6=1,
                v7={"player_id": str(uuid4())},
            ),
            "論理位置",
        ),
        (
            SyncEvent(
                str(uuid4()),
                str(uuid4()),
                2,
                "generation-1",
                v5="player_registration",
                v8={},
                v7={"player_id": str(uuid4())},
            ),
            "状態差分",
        ),
    ],
)
def test_content_port_rejects_open_or_other_event(
    event: SyncEvent, reason: str
) -> None:
    """種別・V7 の閉鎖・一時 ID の型が崩れた入力を拒否する。"""
    accepted, actual = PlayerRegistrationContentValidationPort().validate(
        event, _writer()
    )
    assert accepted is False
    assert reason in (actual or "")


def test_projection_port_accepts_resolved_official_reference() -> None:
    """投影後は正式 ID 1 件でも同じ閉じた V7 として通す。"""
    PlayerRegistrationProjectionPort().apply(_event(), _writer())


@pytest.mark.parametrize(
    "event",
    [
        _event(kind="substitution"),
        _event(v7={}),
        _event(v7={"player_id": "not-uuid"}),
    ],
)
def test_projection_port_rejects_unresolved_shape(event: SyncEvent) -> None:
    """解決済みでない投影結果を保存成功にしない。"""
    with pytest.raises(RuntimeError):
        PlayerRegistrationProjectionPort().apply(event, _writer())
