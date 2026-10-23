"""RG1 clientの閉構造・有限frame・失敗閉鎖を検査する。

実controller/authority/DBの成功検証は専用DB接合へ分ける。本試験のsocketpairや
設定読取の置換はprotocol単体用で、製品のfresh開放成功には数えない。
"""

from __future__ import annotations

import json
import os
import socket
import struct
from pathlib import Path

import pytest

from pitchlog.recording_rights import rg1_lifecycle as lifecycle


def _binding(**overrides: object) -> dict[str, object]:
    """DB観測の閉構造試験にだけ使う非秘密値。"""
    return {
        "system_identifier": "18446744073709551615",
        "database_oid": 16384,
        "database_name": "専用試験DB",
        "postmaster_started_at": "2026-10-24T00:00:00+00:00",
        "backend_pid": 1234,
        **overrides,
    }


def test_business_binding_distinguishes_same_cluster_other_database_and_restart() -> (
    None
):
    """clusterだけの一致で別DB/再起動を同じscopeへ結ばない。"""
    original = lifecycle.BusinessBinding.from_text(json.dumps(_binding()))
    for change in (
        {"system_identifier": "18446744073709551614"},
        {"database_oid": 16385},
        {"database_name": "別DB"},
        {"postmaster_started_at": "2026-10-24T00:00:01+00:00"},
    ):
        other = lifecycle.BusinessBinding.from_text(json.dumps(_binding(**change)))
        assert not original.same_database(other)
    other_connection = lifecycle.BusinessBinding.from_text(
        json.dumps(
            _binding(
                backend_pid=1235,
                postmaster_started_at="2026-10-24T09:00:00+09:00",
            )
        )
    )
    assert original.same_database(other_connection)
    assert original.backend_pid != other_connection.backend_pid


@pytest.mark.parametrize(
    "change",
    (
        {"system_identifier": "0"},
        {"system_identifier": "01"},
        {"system_identifier": "１"},
        {"system_identifier": "18446744073709551616"},
        {"system_identifier": "1" * 5000},
        {"system_identifier": True},
        {"database_oid": True},
        {"database_oid": 0},
        {"database_oid": 2**32},
        {"database_name": ""},
        {"database_name": "bad\0name"},
        {"postmaster_started_at": "2026-10-24T00:00:00"},
        {"postmaster_started_at": "not-a-time"},
        {"postmaster_started_at": None},
        {"backend_pid": False},
        {"backend_pid": -1},
        {"unexpected": "proof"},
    ),
)
def test_binding_rejects_invalid_values_without_defaulting(
    change: dict[str, object],
) -> None:
    """欠落相当/悪型/範囲外/余剰を正常識別へ補完しない。"""
    with pytest.raises(lifecycle.RG1ControlUnavailable):
        lifecycle.BusinessBinding.from_text(json.dumps(_binding(**change)))


@pytest.mark.parametrize(
    "body",
    (
        b"",
        b"[]",
        b"true",
        b'{"x":1,"x":2}',
        b'{"x":NaN}',
        b"\xff",
        b" " * 8193,
    ),
)
def test_peer_json_is_a_bounded_unambiguous_object(body: bytes) -> None:
    """曖昧なJSONをpeerの正常応答へ扱わない。"""
    with pytest.raises(lifecycle.RG1ControlUnavailable):
        lifecycle._decode_object(body)


@pytest.mark.parametrize(
    "frame",
    (
        b"",
        b"\0",
        struct.pack("!I", 0),
        struct.pack("!I", 8193),
        struct.pack("!I", 7) + b"{}",
        struct.pack("!I", 2) + b"[]",
    ),
)
def test_truncated_or_oversized_peer_frame_is_not_a_success(frame: bytes) -> None:
    """実socketのEOF/部分frameを保持・解放成功に数えない。"""
    client, server = socket.socketpair()
    try:
        server.sendall(frame)
        server.close()
        with pytest.raises(lifecycle.RG1ControlUnavailable):
            lifecycle._receive(client)
    finally:
        client.close()
        server.close()


def test_frame_round_trip_does_not_reinterpret_control_payload() -> None:
    """transportは状態の意味を追加せず同じ有限objectを返す。"""
    client, server = socket.socketpair()
    message = {"op": "assert-held", "loan_id": 23}
    try:
        lifecycle._send(client, message)
        assert lifecycle._receive(server) == message
    finally:
        client.close()
        server.close()


def test_user_owned_configuration_is_rejected_before_connect(tmp_path: Path) -> None:
    """書換可能な利用者設定をauthorityの資格にしない。"""
    if os.geteuid() == 0:
        pytest.fail("非rootで実施するclient単体試験")
    path = tmp_path / "controller.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "socket_path": "/run/pitchlog/rg1.sock",
                "controller_uid": 20002,
                "application_uid": os.geteuid(),
            }
        )
    )
    with pytest.raises(lifecycle.RG1ControlUnavailable):
        lifecycle.configure_runtime(path)


def test_missing_configuration_keeps_write_closed() -> None:
    """未提供controllerの代わりを起動・成功させない。"""
    lifecycle.configure_runtime(None)
    binding = lifecycle.BusinessBinding.from_text(json.dumps(_binding()))
    with pytest.raises(lifecycle.RG1ControlUnavailable):
        lifecycle.borrow_gate(binding)


@pytest.mark.parametrize(
    "mutation", ("loan-bool", "ordinal-bool", "epoch-bool", "epoch", "extra")
)
def test_live_loan_rejects_false_primitive_equivalence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    """PythonのTrue==1でpeerの悪型を保持済みへ変えない。"""
    # filesystem/発行は検査対象外。ここは実frameの応答型だけの単体試験。
    fingerprint = (1, 2, "unit-transport")
    config = lifecycle._Configuration(
        tmp_path / "unit", fingerprint, tmp_path / "s", 1, 2
    )
    monkeypatch.setattr(lifecycle, "_configuration_bytes", lambda _: (b"", fingerprint))
    activation = lifecycle._Activation.parse(
        {
            "authority_id": "00000000-0000-4000-8000-000000000001",
            "ordinal": 1,
            "epoch": 1,
        }
    )
    reply: dict[str, object] = {
        "status": "held",
        "loan_id": 1,
        "activation": {
            "authority_id": str(activation.authority_id),
            "ordinal": 1,
            "epoch": 1,
        },
    }
    context = reply["activation"]
    assert isinstance(context, dict)
    if mutation == "loan-bool":
        reply["loan_id"] = True
    elif mutation == "ordinal-bool":
        context["ordinal"] = True
    elif mutation == "epoch-bool":
        context["epoch"] = True
    elif mutation == "epoch":
        context["epoch"] = 2
    else:
        reply["extra"] = "untrusted"
    client, server = socket.socketpair()
    binding = lifecycle.BusinessBinding.from_text(json.dumps(_binding()))
    loan = lifecycle._GateLoan(
        client, config, 1, activation, binding, key=lifecycle._LOAN_KEY
    )
    try:
        lifecycle._send(server, reply)
        with pytest.raises(lifecycle.RG1ControlUnavailable):
            loan.assert_held()
        assert client.fileno() == -1
    finally:
        client.close()
        server.close()
