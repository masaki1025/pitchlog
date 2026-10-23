"""RG1 clientの閉構造・有限frame・失敗閉鎖を検査する。

実controller/authority/DBの成功検証は専用DB接合へ分ける。本試験のsocketpairや
設定読取の置換はprotocol単体用で、製品のfresh開放成功には数えない。
"""

from __future__ import annotations

import json
import os
import socket
import struct
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest
from test_authz_tenant_context import make_tenant_context

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
    message: dict[str, object] = {"op": "assert-held", "loan_id": 23}
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


@pytest.mark.parametrize(
    "failure", ("none", "body", "held", "commit", "rollback", "close", "release")
)
def test_scope_keeps_control_loan_until_pg_transaction_has_ended(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    """PG境界の順序専用probeで、確定前解放と失敗時commitを拒否する。

    認可やcontroller成功を模擬して製品成功に数える試験ではない。
    実製品scopeの終了を通し、借用を先に解放する実装なら失敗させる。
    """
    from pitchlog.repositories import transaction

    events: list[str] = []

    class SessionProbe:
        """実DB試験と分離したPG境界観測。"""

        def execute(self, *_args: object) -> Iterator[tuple[bool]]:
            """登録済みcommit_checkが呼ばれた事実を記録する。"""
            events.append("commit-check")
            return iter(((True,),))

        def close(self) -> None:
            """PG接続解放時点を記録する。"""
            events.append("session-close")
            if failure == "close":
                raise RuntimeError("close unknown")

    class LoanProbe:
        """scope終了順の単体試験だけに使う借用。"""

        def assert_held(self) -> None:
            """直前照合が失敗したscopeをcommitしない。"""
            events.append("held-check")
            if failure == "held":
                raise lifecycle.RG1ControlUnavailable("held failure")

        def release(self) -> None:
            """PG終了より先の解放を検出する。"""
            assert "session-close" in events
            events.append("release")
            if failure == "release":
                raise lifecycle.RG1ControlUnavailable("release unknown")

        def abandon(self) -> None:
            """PGの不明結果を正常releaseへ補完しない。"""
            assert "session-close" in events
            events.append("abandon")

    @contextmanager
    def pg_boundary(_session: object, _context: object) -> Iterator[None]:
        events.append("begin")
        try:
            yield
        except BaseException:
            events.append("rollback")
            if failure == "rollback":
                raise RuntimeError("rollback unknown")
            raise
        else:
            events.append("commit")
            if failure == "commit":
                raise RuntimeError("commit unknown")

    monkeypatch.setattr(transaction, "create_database_engine", lambda: None)
    monkeypatch.setattr(transaction, "Session", lambda _engine: SessionProbe())
    monkeypatch.setattr(transaction, "_tenant_transaction", pg_boundary)
    context = make_tenant_context(UUID("00000000-0000-0000-0000-000000000777"))

    def exercise() -> None:
        with transaction.tenant_transaction_scope(context) as handle:
            key = handle._state_key
            assert key is not None
            assert key not in transaction._RG1_LOANS
            transaction._RG1_LOANS[key] = cast("Any", LoanProbe())
            if failure in {"body", "rollback"}:
                raise RuntimeError("body failed")
        assert handle._state_key is None

    if failure == "none":
        exercise()
    else:
        with pytest.raises(RuntimeError):
            exercise()
    if failure in {"body", "held", "rollback"}:
        assert "rollback" in events and "commit" not in events
    else:
        assert "commit" in events and "rollback" not in events
    expected = "abandon" if failure in {"commit", "rollback", "close"} else "release"
    assert events[-2:] == ["session-close", expected]
    assert not transaction._RG1_LOANS


def test_unchecked_read_scope_does_not_borrow_control(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET/auth等の通常scopeへ新しいRG1入場条件を前倒ししない。"""
    from pitchlog.repositories import transaction

    @contextmanager
    def pg_boundary(_session: object, _context: object) -> Iterator[None]:
        yield

    class SessionProbe:
        """SQL実行も制御借用もないread scopeの終了用。"""

        def close(self) -> None:
            """closeだけを受け付ける。"""

    def forbidden(*_args: object) -> None:
        pytest.fail("RG1を照合しないscopeでborrowを開始した")

    monkeypatch.setattr(transaction, "create_database_engine", lambda: None)
    monkeypatch.setattr(transaction, "Session", lambda _engine: SessionProbe())
    monkeypatch.setattr(transaction, "_tenant_transaction", pg_boundary)
    monkeypatch.setattr(transaction, "borrow_gate", forbidden)
    context = make_tenant_context(UUID("00000000-0000-0000-0000-000000000778"))
    with transaction.tenant_transaction_scope(context):
        pass
    assert not transaction._RG1_LOANS


def test_abandon_closes_channel_without_sending_normal_release() -> None:
    """結果不明はrelease frame/ACKを持たず、server側でEOFとして観測する。"""
    client, server = socket.socketpair()
    try:
        loan = object.__new__(lifecycle._GateLoan)
        loan._socket = client
        loan.abandon()
        assert server.recv(1) == b""
        with pytest.raises(lifecycle.RG1ControlUnavailable):
            loan.assert_held()
    finally:
        client.close()
        server.close()


def test_machine_manifest_pins_sql_and_limits_application_control_access() -> None:
    """機械供給宣言が実SQLに一致し、appへ制御6関数を与えない。"""
    import hashlib

    source = Path(lifecycle.__file__).parent
    manifest = json.loads((source / "rg1_lifecycle_manifest.json").read_text())
    assert (
        manifest["source_sql_sha256"]
        == hashlib.sha256((source / "rg1_lifecycle.sql").read_bytes()).hexdigest()
    )
    functions = manifest["functions"]
    assert len(functions) == 7
    assert {function["name"] for function in functions} == {
        "rg1_control.try_controller_lease",
        "rg1_control.release_controller_lease",
        "rg1_control.close_gate",
        "rg1_control.open_fresh_gate",
        "rg1_control.controller_lease_alive",
        "rg1_control.read_closed_gate",
        "rg1_control.scope_binding",
    }
    assert [f["name"] for f in functions if "pitchlog_app" in f["execute_roles"]] == [
        "rg1_control.scope_binding"
    ]
    assert manifest["evidence_boundaries"]["pg_completion_unknown"] == (
        "abandon_without_release_ack"
    )


def test_controller_rejects_unprivileged_start_before_reading_configuration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """root保護のbootstrapを、一般callerの設定値だけで開始しない。"""
    monkeypatch.setattr(lifecycle.os, "geteuid", lambda: 20002)
    with pytest.raises(lifecycle.RG1ControlUnavailable):
        lifecycle.serve_fresh_controller(tmp_path / "not-created.json")
