"""閉ABI/終結比較/能力分離。純比較は実DBの証拠と区別する。"""

from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, cast
from uuid import UUID

import pytest

from pitchlog.durable_rights_ledger.adapter import (
    LedgerUnavailable,
    _authorize_operation,
)
from pitchlog.durable_rights_ledger.authority import (
    AuthorityUnavailable,
    _validate_binding_config,
)
from pitchlog.repositories.function_operations import (
    FunctionOperationError,
    build_function_registry,
    decode_function_result,
    prepare_function_operation,
)
from pitchlog.repositories.tokens import TenantOperationResult
from pitchlog.repositories.writer_binding import (
    _UNREGISTERED_DECLARATIONS,
    _AssertWriterBindingToken,
)
from pitchlog.sync.control_provider.binding_control import (
    BindingOutcome,
    _BindingAuthority,
    _classify_observation,
    _writer_from_wire,
)
from pitchlog.sync.control_provider.writer_binding import (
    WriterBindingUnavailable,
    WriterIdentity,
    _issue_live_writer_binding,
    _LiveWriterBinding,
)

# 反映1の21対向候補172c8501を固定。実DB結果ではない。
_CASES = [
    (
        "publish_unasserted_outer_live",
        True,
        True,
        0,
        0,
        "in progress",
        "ENTRY_CLOSED_UNADMITTED",
    ),
    ("top_level_admission_commit", True, True, 1, 1, "committed", "COMMITTED"),
    (
        "committed_admission_status_retention_expired",
        True,
        True,
        1,
        1,
        None,
        "COMMITTED",
    ),
    (
        "top_level_admission_outer_abort",
        True,
        True,
        0,
        0,
        "aborted",
        "ROLLBACK_CONFIRMED",
    ),
    ("assert_reply_lost_then_committed", True, True, 1, 1, "committed", "COMMITTED"),
    (
        "assert_reply_lost_then_aborted",
        True,
        True,
        0,
        0,
        "aborted",
        "ROLLBACK_CONFIRMED",
    ),
    ("assert_reply_lost_no_admission_status_null", True, True, 0, 0, None, "UNKNOWN"),
    (
        "savepoint_rejected_outer_live",
        True,
        True,
        0,
        0,
        "in progress",
        "ENTRY_CLOSED_UNADMITTED",
    ),
    (
        "savepoint_rejected_then_outer_aborted",
        True,
        True,
        0,
        0,
        "aborted",
        "ROLLBACK_CONFIRMED",
    ),
    (
        "unasserted_outer_committed",
        True,
        True,
        0,
        0,
        "committed",
        "ENTRY_CLOSED_UNADMITTED",
    ),
    ("business_close_commit_reply_lost", True, False, 1, 1, "committed", "UNKNOWN"),
    ("drain_timeout_old_writer_live", True, False, 0, 0, "in progress", "UNKNOWN"),
    ("authority_restart_no_recent_status", True, True, 0, 0, None, "UNKNOWN"),
    (
        "authority_restart_same_binding_committed",
        True,
        True,
        1,
        1,
        "committed",
        "COMMITTED",
    ),
    ("authority_restart_other_instance", False, True, 1, 1, "committed", "UNKNOWN"),
    ("caller_claimed_admitted_status_null", True, True, 0, 0, None, "UNKNOWN"),
    ("other_lease_admission", True, True, 1, 0, "committed", "UNKNOWN"),
    ("admission_status_contradiction", True, True, 1, 1, "aborted", "UNKNOWN"),
    ("duplicate_admission", True, True, 2, 2, "committed", "UNKNOWN"),
    (
        "committed_observation_terminal_append_unknown",
        True,
        True,
        1,
        1,
        "committed",
        "COMMITTED",
    ),
    (
        "terminal_durable_lease_close_reply_lost",
        True,
        True,
        1,
        1,
        "committed",
        "COMMITTED",
    ),
]


@pytest.mark.parametrize(
    "name,identity,closed,count,matching,status,expected",
    _CASES,
    ids=[r[0] for r in _CASES],
)
def test_closed_observation(name, identity, closed, count, matching, status, expected):
    """未assert/NULL/close不明をrollbackへ昇格しない。"""
    assert len(_CASES) == 21
    assert _classify_observation(
        closed=closed,
        identity_valid=identity,
        admissions=count,
        matching=matching,
        xid_status=status,
    ) == BindingOutcome(expected)


def _writer():
    """実証でない純型検査値。"""
    now = datetime(2026, 10, 27, tzinfo=timezone.utc)
    return WriterIdentity("123", "16384", now, 23, now, "18446744073709551615")


@pytest.mark.parametrize(
    "xid", ["0", "01", "-1", "18446744073709551616", True, 1, None]
)
def test_xid8_rejects_noncanonical_values(xid):
    """全64bitを文字列のまま扱い、符号/型を補正しない。"""
    with pytest.raises(WriterBindingUnavailable):
        replace(_writer(), transaction_id=xid)


def test_xid8_roundtrip_and_private_issuer():
    """scalarだけでprivate資格を発行しない。"""
    assert _writer_from_wire(_writer().wire()) == _writer()
    with pytest.raises(WriterBindingUnavailable):
        _LiveWriterBinding(None, None, _writer(), cast(Any, None), object())


@pytest.mark.parametrize(
    "change",
    [
        {"backend_pid": True},
        {"extra": "x"},
        {"transaction_id": 1},
        {"postmaster_started_at": "2026-10-27"},
    ],
)
def test_writer_wire_closed(change):
    """任意JSONをwriterの証明にしない。"""
    with pytest.raises(WriterBindingUnavailable):
        _writer_from_wire(_writer().wire() | change)


def test_exact_declarations():
    """新2関数だけ。登録/秘密長/戻りNULLの境界を維持する。"""
    registry = build_function_registry(_UNREGISTERED_DECLARATIONS, frozenset())
    token = _AssertWriterBindingToken(
        UUID(int=1), UUID(int=2), b"n" * 32, UUID(int=3), UUID(int=4)
    )
    assert (
        prepare_function_operation(token, UUID(int=5), registry)[1]["binding_nonce"]
        == b"n" * 32
    )
    assert "nnnn" not in repr(token)
    with pytest.raises(FunctionOperationError):
        prepare_function_operation(token, UUID(int=5), {})
    with pytest.raises(FunctionOperationError):
        prepare_function_operation(
            replace(token, binding_nonce=b"n" * 31), UUID(int=5), registry
        )
    result = TenantOperationResult(((None,),))
    assert decode_function_result(_UNREGISTERED_DECLARATIONS[1], result) == result
    with pytest.raises(FunctionOperationError):
        replace(
            _UNREGISTERED_DECLARATIONS[1], function_id="other.assert_writer_binding"
        )


@pytest.mark.parametrize(
    "op",
    [
        "epoch",
        "reserve",
        "claim",
        "fence_open",
        "fresh_activation_open",
        "binding_close",
    ],
)
def test_binding_peer_denies_other_capabilities(op):
    """専用peerから既能力へ到達させない。"""
    with pytest.raises(LedgerUnavailable):
        _authorize_operation("sync_binding", op)


@pytest.mark.parametrize("role", ["generation", "fresh_controller"])
def test_legacy_peer_cannot_open_binding(role):
    """旧peerのnonce権限を拡張しない。"""
    with pytest.raises(LedgerUnavailable):
        _authorize_operation(role, "binding_open")
    _authorize_operation("sync_binding", "binding_open")


def _config():
    """非秘密の新profile検査値。"""
    return {
        "binding_business_dsn": (
            "host=/owned/business dbname=test user=pitchlog_sync_binding_actor"
        ),
        "binding_control_dsn": (
            "host=/owned/control dbname=test user=pitchlog_sync_binding_actor"
        ),
        "binding_authority": {
            "control_instance": str(UUID(int=1)),
            "business_instance": str(UUID(int=2)),
            "restore_epoch": str(UUID(int=3)),
            "control_version": 1,
        },
    }


@pytest.mark.parametrize(
    "dsn",
    [
        "host=localhost dbname=test user=pitchlog_sync_binding_actor",
        "host=/owned dbname=test user=pitchlog_app",
        "host=/owned dbname=test user=pitchlog_sync_binding_actor password=forbidden",
        "host=/a,/b dbname=test user=pitchlog_sync_binding_actor",
    ],
)
def test_new_config_rejects_general_roles_and_secrets(dsn):
    """専用actor/Unix非秘密接続だけを設定として受理する。"""
    config = _config()
    _validate_binding_config(config)
    config["binding_business_dsn"] = dsn
    with pytest.raises(AuthorityUnavailable):
        _validate_binding_config(config)


def test_close_failure_is_unknown(monkeypatch):
    """closeの応答不明はcaller ACKで補わない。実DB故障結果ではない。"""
    authority = _BindingAuthority({}, UUID(int=1))
    calls = []
    record = {
        n: str(UUID(int=i + 1))
        for i, n in enumerate(
            ("tenant_id", "attempt_id", "phase_id", "lease_id", "close_id")
        )
    }

    def call(which, statement, params, *, write=False):
        calls.append((statement, write))
        raise OSError("comparison only")

    monkeypatch.setattr(authority, "_call", call)
    assert authority.resolve(record) == BindingOutcome.UNKNOWN
    assert len(calls) == 1 and calls[0][1] is True


def test_fake_writer_handle_does_not_issue_capability():
    """構造が似たhandleやscalar leaseから実資格を作らない。"""
    with pytest.raises(WriterBindingUnavailable):
        _issue_live_writer_binding(object(), cast(Any, object()))


@pytest.mark.parametrize("value", [True, False, 0, "", ()])
def test_assert_void_response_cannot_be_synthetic_success(value):
    """固定assertのvoidをbool等の代替成功応答へ拡張しない。"""
    with pytest.raises(FunctionOperationError):
        decode_function_result(
            _UNREGISTERED_DECLARATIONS[1], TenantOperationResult(((value,),))
        )


def _control_sql() -> str:
    """制御PGの実供給SQLを読み、DB実行の代替としない。"""
    from pathlib import Path

    return (
        Path(__file__).resolve().parents[1]
        / "src/pitchlog/sync/control_provider/sql/writer-binding-control.sql"
    ).read_text()


def _assert_closed_control_role_guard(source: str) -> None:
    """GRANT前のexact2role/属性/双方向edge検査を静的に凍結する。"""
    import re

    prefix, suffix = source.split("GRANT USAGE", 1)
    guard = re.sub(r"\s+", " ", prefix)
    assert (
        "FOREACH role_name IN ARRAY ARRAY['pitchlog_sync_binding_fn_owner',"
        "'pitchlog_sync_binding_actor'] LOOP" in guard
    )
    assert "actor:=role_name='pitchlog_sync_binding_actor';" in guard
    assert "SELECT * INTO r FROM pg_roles WHERE rolname=role_name;" in guard
    assert "IF NOT FOUND THEN" in guard
    for role, login in (
        ("pitchlog_sync_binding_actor", "LOGIN"),
        ("pitchlog_sync_binding_fn_owner", "NOLOGIN"),
    ):
        assert (
            f"CREATE ROLE {role} {login} NOSUPERUSER NOINHERIT NOBYPASSRLS "
            "NOCREATEROLE NOCREATEDB NOREPLICATION;" in guard
        )
    expected = (
        "ELSIF r.rolcanlogin IS DISTINCT FROM actor OR r.rolsuper OR r.rolinherit "
        "OR r.rolbypassrls OR r.rolcreaterole OR r.rolcreatedb OR r.rolreplication "
        "OR r.rolconnlimit<>-1 OR r.rolvaliduntil IS NOT NULL "
        "OR EXISTS(SELECT FROM pg_auth_members m WHERE m.member=r.oid "
        "OR m.roleid=r.oid) THEN RAISE EXCEPTION "
        "'binding control role configuration rejected' USING ERRCODE='42501'; END IF;"
    )
    assert expected in guard
    assert "END LOOP; END;$roles$;" in guard
    assert re.search(r"\bALTER\s+ROLE\b", source, re.IGNORECASE) is None
    assert "TO pitchlog_sync_binding_actor,pitchlog_sync_binding_fn_owner;" in suffix


def test_control_existing_roles_are_exactly_guarded_before_grant():
    """未存在CREATE/正常既roleの経路を保ち、危険な既roleは先に拒否する構造。"""
    _assert_closed_control_role_guard(_control_sql())


@pytest.mark.parametrize(
    "fragment",
    [
        "r.rolcanlogin IS DISTINCT FROM actor",
        "r.rolsuper",
        "r.rolinherit",
        "r.rolbypassrls",
        "r.rolcreaterole",
        "r.rolcreatedb",
        "r.rolreplication",
        "r.rolconnlimit<>-1",
        "r.rolvaliduntil IS NOT NULL",
        "m.member=r.oid",
        "m.roleid=r.oid",
    ],
)
def test_control_role_guard_static_counterexamples_are_detected(fragment):
    """属性・edge片側を削った旧反例を静的検査が拒否する。実PG結果ではない。"""
    source = _control_sql()
    assert fragment in source
    with pytest.raises(AssertionError):
        _assert_closed_control_role_guard(source.replace(fragment, "false", 1))


@pytest.mark.parametrize(
    "old,new",
    [
        (
            "'pitchlog_sync_binding_fn_owner','pitchlog_sync_binding_actor'",
            "'pitchlog_sync_binding_actor'",
        ),
        (
            "actor:=role_name='pitchlog_sync_binding_actor'",
            "actor:=role_name='pitchlog_sync_binding_fn_owner'",
        ),
        (
            "IF NOT FOUND THEN",
            "IF NOT FOUND THEN ALTER ROLE pitchlog_sync_binding_actor LOGIN;",
        ),
    ],
)
def test_control_guard_rejects_owner_omission_login_inversion_and_repair(old, new):
    """owner未検査/LOGIN逆転/勝手なALTER修復を対向で保持する。"""
    source = _control_sql()
    assert old in source
    with pytest.raises(AssertionError):
        _assert_closed_control_role_guard(source.replace(old, new, 1))
